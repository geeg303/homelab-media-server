#!/usr/bin/env python3
"""Build the public, scrubbed mirror of the private media-server repo and (optionally) commit + push it.

  python tools/publish-public.py [--push]

Private repo (exact values, for recovery):  C:/Users/user/media-server-repo   -> github.com/example-owner/media-server (private)
Public mirror (scrubbed, shareable):        C:/Users/user/media-server-public -> github.com/example-owner/homelab-media-server (public)
Sanitize map (private, never committed):   C:/Users/user/media-server-stack/sanitize-map.json

Show 62: IPs (LAN, Tailscale), MAC addresses, Wi-Fi SSID, disk serials, filesystem/partition UUIDs and other UUIDs
(Notion IDs etc.), tailnet name, usernames/real name/e-mail/GitHub handle, Discord IDs, Notion links, personal folder
names, and every TV show / movie / episode title. Placeholders are stable between runs (stored in the map).
Then VERIFIES: no real value from the map and none of the guard regexes may remain anywhere, or nothing is published."""
import json, os, re, shutil, subprocess, sys, hashlib

PRIV = r"C:/Users/user/media-server-repo"
PUB = r"C:/Users/user/media-server-public"
MAP = r"C:/Users/user/media-server-stack/sanitize-map.json"
GH = r"C:/Program Files/GitHub CLI/gh.exe"
TEXT_EXT = (".md", ".xml", ".yml", ".yaml", ".json", ".sh", ".py", ".conf", ".service", ".timer", ".txt", ".tsv", ".example", ".js", ".css",
            ".pending", ".gitignore", ".gitattributes")
TEXT_NAMES = ("fstab",)

M = json.load(open(MAP, encoding="utf-8"))
dirty = False

def stable(kind, real, fmt):
    """Placeholder for `real`, stored in the map so it never changes between runs."""
    global dirty
    tbl = M.setdefault("assigned", {}).setdefault(kind, {})
    if real not in tbl:
        tbl[real] = fmt(len(tbl) + 1, real); dirty = True
    return tbl[real]

def h(s, n): return hashlib.sha256(("salt:" + M["salt"] + s).encode()).hexdigest()[:n]

# ---------- rules ----------
lits = sorted(M["literals"].items(), key=lambda kv: -len(kv[0]))          # exact strings (case-sensitive)
ci_words = M["ci_words"]                                                   # whole words, case-insensitive

def names_regex(names):
    alts = sorted({n for n in names if n}, key=len, reverse=True)
    return re.compile(r"(?<![\w])(" + "|".join(re.escape(a) for a in alts) + r")(?![\w])")

tv = M["tv"]; mv = M["movies"]
tv_re = names_regex(list(tv)); mv_re = names_regex(list(mv))
# lowercase pass for long titles only (scripts use lowercased names in regexes; short ones like 'echo' are shell words)
low = {k.lower(): v.lower().replace(" ", "-") for k, v in list(tv.items()) + list(mv.items()) if len(k) >= 8}
low_re = re.compile(r"(?<![\w])(" + "|".join(re.escape(a) for a in sorted(low, key=len, reverse=True)) + r")(?![\w])")

RX = [
    (re.compile(r"\b192\.168\.(\d{1,3})\.(\d{1,3})\b"), lambda m: f"192.0.2.{m.group(2)}" if m.group(1) == "1" else f"198.51.100.{m.group(2)}"),
    (re.compile(r"\b100\.(6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.(\d{1,3})\.(\d{1,3})\b"),
     lambda m: m.group(0) if m.group(0) in ("100.64.0.0", "100.64.0.10") else stable("tsip", m.group(0), lambda i, r: f"100.64.0.{10 + i}")),
    (re.compile(r"\bfd7a:115c:a1e0:[0-9a-f:]+\b", re.I), lambda m: "fd7a:115c:a1e0::1"),
    (re.compile(r"\b(?:[0-9a-f]{2}:){5}[0-9a-f]{2}\b", re.I), lambda m: stable("mac", m.group(0).lower(), lambda i, r: f"02:00:00:00:00:{i:02x}")),
    (re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I),
     lambda m: (lambda x: f"{x[:8]}-{x[8:12]}-4{x[13:16]}-8{x[17:20]}-{x[20:32]}")(h(m.group(0).lower(), 32))),
    (re.compile(r"\b[0-9A-F]{16}\b"), lambda m: h(m.group(0), 16).upper()),                       # NTFS volume serials
    (re.compile(r"\b[0-9A-F]{4}-[0-9A-F]{4}\b"), lambda m: (lambda x: f"{x[:4]}-{x[4:]}")(h(m.group(0), 8).upper())),  # vfat UUIDs
    (re.compile(r"(?<!\d)\d{17,20}(?!\d)"), lambda m: stable("snowflake", m.group(0), lambda i, r: f"1{i:017d}")),   # Discord IDs
    (re.compile(r"https?://(?:app\.|www\.)?notion\.(?:so|com)/\S+"), lambda m: "https://www.notion.so/<private-board>
    (re.compile(r"…[0-9A-F]{4}\b"), lambda m: "…XXXX"),                                            # partial serials "…XXXX"
    (re.compile(r"\b(S\d{1,2}[Ee]\d{1,3}) - [^|\n\"/\\]+?(?= (?:Bluray|WEBDL|WEB-DL|WEBRip|HDTV|SDTV|DVD|Remux)[-\w]*)"), lambda m: f"{m.group(1)} - Episode"),
    (re.compile(r"\b(S\d{1,2}[Ee]\d{1,3}) - (?!Episode\b)[^|\n\"/\\.]{2,60}\.(mkv|mp4|avi|m4v)"), lambda m: f"{m.group(1)} - Episode.{m.group(2)}"),
    (re.compile(r"(?<![\w])Show 53(?![\w])(?![ _-]?(?:save|saving|on|off|supply|management|Shell|state|scheme|cycle|draw|loss|button))", re.I if False else 0),
     lambda m: M.get("power_placeholder", "Show")),
    (re.compile(r"lib4k_[A-Za-z0-9]+"), lambda m: stable("lib4k", m.group(0), lambda i, r: f"lib4k_show08{i:02d}")),
]

def scrub(t):
    for a, b in lits: t = t.replace(a, b)
    for w, b in ci_words.items(): t = re.sub(r"(?<![\w])" + re.escape(w) + r"(?![\w])", b, t, flags=re.I)
    t = tv_re.sub(lambda m: tv[m.group(1)], t)
    t = mv_re.sub(lambda m: mv[m.group(1)], t)
    t = low_re.sub(lambda m: low[m.group(1)], t)
    for rx, fn in RX: t = rx.sub(fn, t)
    return t

# ---------- guards: must find nothing after scrubbing ----------
GUARDS = [re.compile(re.escape(k)) for k in M["literals"] if len(k) >= 4] + \
         [re.compile(r"(?<![\w])" + re.escape(w) + r"(?![\w])", re.I) for w in ci_words] + \
         [tv_re, mv_re, low_re,
          re.compile(r"\b192\.168\.\d+\.\d+\b"), re.compile(r"\btail[0-9a-f]{6}\b"),
          re.compile(r"\b(?!02:00:00:00:00:)(?:[0-9a-f]{2}:){5}[0-9a-f]{2}\b", re.I)]
GUARD_EXTRA = [s for s in M.get("must_not_appear", [])]

def is_text(p):
    b = os.path.basename(p)
    return b.endswith(TEXT_EXT) or b in TEXT_NAMES or "." not in b

def build():
    # fresh copy of the private tree (minus .git and private-only files)
    for root, dirs, files in os.walk(PUB):
        if ".git" in root.split(os.sep): continue
    for entry in os.listdir(PUB):
        if entry == ".git": continue
        p = os.path.join(PUB, entry)
        shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
    skipped = []
    for root, dirs, files in os.walk(PRIV):
        dirs[:] = [d for d in dirs if d != ".git"]
        rel_root = os.path.relpath(root, PRIV)
        for f in files:
            src = os.path.join(root, f)
            rel = os.path.normpath(os.path.join(rel_root, f))
            if not is_text(src): skipped.append(rel); continue
            rel_out = scrub(rel.replace("\\", "/"))
            dst = os.path.join(PUB, rel_out)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            txt = open(src, encoding="utf-8", errors="replace").read()
            open(dst, "w", encoding="utf-8", newline="\n").write(scrub(txt))
    # public README banner
    rd = os.path.join(PUB, "README.md")
    if os.path.exists(rd):
        t = open(rd, encoding="utf-8").read()
        banner = ("> **Public, scrubbed copy.** IP addresses, MAC addresses, Wi-Fi name, disk serials, UUIDs, Tailscale names, "
                  "usernames, IDs and all media titles are replaced with placeholders (e.g. `192.0.2.10`, `Show 07`, `Movie 042`). "
                  "Secrets were never in the repo. Generated automatically from a private repo after every change.\n\n")
        open(rd, "w", encoding="utf-8", newline="\n").write(banner + t)
    return skipped

def verify():
    hits = []
    for root, dirs, files in os.walk(PUB):
        dirs[:] = [d for d in dirs if d != ".git"]
        for f in files:
            p = os.path.join(root, f); rel = os.path.relpath(p, PUB)
            t = open(p, encoding="utf-8", errors="replace").read() + "\n" + rel
            for g in GUARDS:
                m = g.search(t)
                if m: hits.append(f"{rel}: pattern {g.pattern[:40]!r} -> {m.group(0)[:3]}…")
            for s in GUARD_EXTRA:
                if s.lower() in t.lower(): hits.append(f"{rel}: must_not_appear item #{GUARD_EXTRA.index(s)}")
    return hits

def git(*a, check=True):
    return subprocess.run(["git", "-C", PUB, *a], capture_output=True, text=True, check=check).stdout.strip()

if __name__ == "__main__":
    skipped = build()
    if dirty:
        json.dump(M, open(MAP, "w", encoding="utf-8"), indent=1, ensure_ascii=False, sort_keys=True)
    hits = verify()
    print(f"public tree built; non-text files skipped: {skipped or 'none'}")
    if hits:
        print(f"ABORT: {len(hits)} identifying value(s) survived scrubbing:"); [print("  ", x) for x in hits[:40]]
        sys.exit(1)
    print("verify: clean (0 real values, 0 guard hits)")
    if "--push" in sys.argv:
        git("add", "-A")
        if subprocess.run(["git", "-C", PUB, "diff", "--cached", "--quiet"]).returncode == 0:
            print("public: already in sync"); sys.exit(0)
        msg = sys.argv[sys.argv.index("--push") + 1] if len(sys.argv) > sys.argv.index("--push") + 1 else "Sync"
        git("commit", "-q", "-m", scrub(msg))
        git("push", "-q", "origin", "HEAD:main")
        print("public pushed", git("log", "-1", "--format=%h"))
