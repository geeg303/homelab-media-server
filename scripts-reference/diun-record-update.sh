#!/bin/sh
# DIUN script notifier: one line per changed image; update-digest sends them once a day and clears the file.
[ "${DIUN_ENTRY_STATUS:-}" = "update" ] || [ "${DIUN_ENTRY_STATUS:-}" = "new" ] || exit 0
echo "$(date '+%a %H:%M') ${DIUN_ENTRY_IMAGE:-?}" >> /data/pending-updates.txt
