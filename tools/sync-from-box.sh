#!/usr/bin/env bash
# Sync this repo with the live box + the local project docs, scan for secrets, commit and push.
# Usage (Hermes bash on user's PC):  tools/sync-from-box.sh "commit message"
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
DOCS=/c/Users/user/media-server-stack
SSH=(ssh -i "$HOME/.ssh/hermes_mss" -o BatchMode=yes -o IdentitiesOnly=yes user@192.0.2.242)
SCP=(scp -q -i "$HOME/.ssh/hermes_mss" -o BatchMode=yes -o IdentitiesOnly=yes)
MSG="${1:-Sync with box}"
GH="/c/Program Files/GitHub CLI/gh.exe"
cd "$REPO"

git pull -q --ff-only

# 1. collect on the box (whitelist + redaction + secret-value scan happen there)
"${SCP[@]}" tools/box-export.py user@192.0.2.242:box-export.py
"${SSH[@]}" 'sudo -n bash -s' < tools/box-collect.sh
TMP="${TMPDIR:-$LOCALAPPDATA/Temp}/reposync.$$"; mkdir -p "$TMP"; trap 'rm -rf "$TMP"' EXIT
"${SCP[@]}" user@192.0.2.242:reposync.tgz "$TMP/r.tgz"
"${SSH[@]}" 'rm -f ~/reposync.tgz'

# 2. replace the mirrored trees (deletions on the box show up as deletions here)
for d in stacks dockge scripts-reference systemd host config exports; do rm -rf "$REPO/$d"; done
tar -C "$REPO" -xzf "$TMP/r.tgz"

# 3. local project docs
mkdir -p "$REPO/docs"
for f in "$DOCS"/*.md "$DOCS"/*.tsv; do [ -f "$f" ] && cp "$f" "$REPO/docs/"; done

# 4. pattern scan of everything that would be committed (second line of defense)
git add -A
PAT='(tapi_[A-Za-z0-9]{6,}|gh[pousr]_[A-Za-z0-9]{20,}|xox[bp]-|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY|ntfy[.]sh/[A-Za-z0-9_-]{8,}|X-Plex-Token=[A-Za-z0-9]|[?&]apikey=[A-Za-z0-9]{8,}|password: *[^ <$"{]|[0-9a-f]{32})'
# scan added lines outside tools/; TRaSH trash_ids (bare 32-hex list items, often "# name"-commented) are public ids, not secrets
ADDED=$(git diff --cached -U0 -- . ':(exclude)tools/' | grep -E '^(\+\+\+ |\+)' | grep -vE '^\+[[:space:]#]*(- *)?(trash_ids?: *)?[0-9a-f]{32}[[:space:]]*(#.*)?$' || true)
if printf '%s\n' "$ADDED" | grep -v '^+++' | grep -qE "$PAT"; then
  echo "ABORT: possible secret in staged changes in:"
  printf '%s\n' "$ADDED" | awk -v pat="$PAT" '/^\+\+\+ /{f=substr($0,7)} !/^\+\+\+ / && $0 ~ pat {print f}' | sort -u
  git reset -q; exit 1
fi

publish_public() {   # scrubbed public mirror (example-owner/homelab-media-server); refuses to push if any identifying value survives
  [ "${DRYRUN:-0}" = 1 ] && return 0
  python "$(dirname "$0")/publish-public.py" --push "$MSG" | grep -E "ABORT|verify|public" || { echo "PUBLIC MIRROR NOT UPDATED (see above)"; return 1; }
}
if git diff --cached --quiet; then echo "already in sync, nothing to commit"; publish_public; exit 0; fi
git diff --cached --stat | tail -n 25
if [ "${DRYRUN:-0}" = 1 ]; then echo "DRYRUN: not committing"; exit 0; fi
git commit -q -m "$MSG"
git push -q origin HEAD:main
git log -1 --format='pushed %h %s'
"$GH" api repos/example-owner/media-server/commits/main -q '.sha[0:7]+" on GitHub"'
publish_public
