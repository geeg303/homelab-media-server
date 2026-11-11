# Second enclosure: read-only check (Nov 11, 2026)

Plugged in 08:30. Nothing mounted, written or formatted.

## USB
- Second JMicron JMS567 bridge on USB bus 2 port 3, 5 Gb/s (first enclosure: port 4; Wi-Fi adapter: port 8). All on the 20 Gb/s Intel controller.
- **Both bridges report the same USB serial (20170331000C3)**, so the `usb-External_USB3.0_DISKnn_…` by-id links collide between enclosures. Always address disks by `ata-…_<serial>` or `wwn-…`, never `usb-…`.

## The five WD80EMAZ drives (all 8.00 TB, HGST He10 helium, CMR)
| Bay (LUN) | Dev now | Serial | Power-on h | Load cycles | Realloc/Pending/Uncorr | CRC | Helium | Long test est. |
|---|---|---|---|---|---|---|---|---|
| 0 | sdf | SERIAL-WD1 (user's "1") | 39,218 | 58,871 | 0/0/0 | 0 | 100 | 18.2 h |
| 1 | sdg | 7SJ8JDXW | 40,970 | 68,725 | 0/0/0 | 0 | 100 | 20.4 h |
| 2 | sdh | 7HJY59ZF | 41,663 | 69,837 | 0/0/0 | 3 | 100 | 15.1 h |
| 3 | sdi | 7HJY82BF | 41,658 | 57,090 | 0/0/0 | 0 | 100 | 17.2 h |
| 4 | sdj | 7HK2YR2H | 20,579 | 3,732 | 0/0/0 | 0 | 100 | 18.6 h |

All SMART overall PASSED, no self-tests ever logged. Load cycles are far below the 600k rating. sdh's 3 CRC errors are old cable/bridge events, not media errors.

## Old RAID metadata
All five carry **LSI DDF RAID metadata** (a RAID 5 across 20 drives from a former server). Ubuntu's mdadm auto-assembled them as inactive `md126`/`md127` (0 B, nothing readable). user doesn't need their data. Before formatting, stop the arrays and erase the DDF metadata (`mdadm --stop`, `mdadm --zero-superblock`, `wipefs -a`). ⚠️ DESTRUCTIVE: needs her per-disk OK, like sda.

## Existing disks (for reference)
- disk1 (sdc, BarraCuda SMR SERIAL-DISK1): 61,407 h (about 7 years), 0 bad sectors.
- sdd: 60,934 h.
- sde: 55,707 h.
- IronWolfs: sda 16,152 h; sdb 28,287 h.

## Next (needs user's go)
1. Stop the inactive md126/md127 arrays (doesn't write to the disks) and start SMART long self-tests on all five (non-destructive, run inside the drives, about 15–20 h). Homepage tile first.
2. Review the results, then her per-disk format OKs → rounds 3–5 copy sdd/sde/sdb straight onto WDs.
