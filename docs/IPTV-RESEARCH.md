# Live TV in Plex: IPTV research (Nov 10, 2026)

Goal (user): IPTV channels in Plex Live TV & DVR (Plex Pass active), a software "tuner", and providers with free trials to test.

## How Plex fits in
- Plex Live TV & DVR only ingests **HDHomeRun-style network tuners**. It does not read M3U playlists itself (checked: Plex support docs + current guides; a 2024 forum post claiming a native "IPTV" option is unverified and contradicted by everything else).
- So the chain is: **source playlist (M3U + XMLTV guide) → tuner emulator → Plex** (Settings → Live TV & DVR → enter the emulator's address manually; Docker networks don't pass the HDHomeRun discovery broadcast).
- Plex's own free "Live TV" channels already work in every Plex app with no setup, but they can't be recorded. Bringing channels in through a tuner adds guide + DVR.
- Keep lineups curated (a few hundred channels): Plex has a known bug where very large lineups break channel setup (URI length limit).

## Tuner software (all Docker, light on CPU/RAM)
| Option | Status (checked Nov 10) | Notes |
|---|---|---|
| **Dispatcharr** (recommended) | v0.33.0, Oct 24 2026; 4.5k stars; AGPL-3.0; commits this week | HDHomeRun emulation for Plex, M3U/Xtream import, EPG auto-matching (XMLTV, Schedules Direct), failover between sources, built-in DVR + Comskip, FFmpeg output profiles, per-user access. The community's current pick over Threadfin/xTeVe. |
| Threadfin | 1.2.37, Sep 2025; repo idle since Oct 2025 | xTeVe fork, simpler; users report daily "device not found" in Plex; effectively unmaintained. |
| xTeVe | abandoned | Don't use. |
| **FastChannels** (source aggregator, pairs with Dispatcharr) | very active (pushed Nov 11 2026) | Builds M3U + XMLTV from legal free services: Roku Channel, Samsung TV Plus, Plex, Xumo, LG, Vizio, TCL, Pluto, Tubi (account), PBS (local station by ZIP), C-SPAN, ~40 free network feeds (CBS News, NHK, DW, Bloomberg…). Resolves fresh stream URLs on every tune, Stream Audit drops dead/DRM channels. Also has subscription + TV Everywhere sources, but those are DRM and need an extra "bridge" (headless Chrome via PrismCast, or a Fire TV/Android TV box). Plex is "unsupported" by its author: it needs a tuner emulator in front, i.e. Dispatcharr. |
| Static FAST playlists (i.mjh.nz, BuddyChewChew/app-m3u-generator) | live | Simpler than FastChannels (just URLs), Pluto/Samsung/Plex/Roku/Tubi with guide. Good for a 10-minute first test in Dispatcharr. |

## Providers
### Unlicensed "IPTV subscriptions" (the "20,000 channels, 24-hour free trial" sites)
Not recommended, and not evaluated provider by provider:
- They resell cable channels without rights. Enforcement in 2026 is active: ACE won an $18.75M judgment against a US operator (Mar 2026) and $9M against Outer Limits IPTV (Jun 2026); a UK operator was jailed (Jun 2026). Viewers are rarely prosecuted, but services vanish overnight (prepaid money lost), payments go to anonymous resellers, and the "apps" they push are a malware risk.
- The free trial is a sales funnel; reliability during big games (when they're used most) is the usual failure.

### Legal options, cheapest effort first
| Option | Cost / trial | Into Plex? |
|---|---|---|
| Free ad-supported channels via FastChannels / FAST playlists (Pluto, Samsung TV Plus, Roku, Xumo, Tubi, PBS…) | free | ✅ via Dispatcharr, with guide + DVR. Hundreds of usable channels (news, classic TV, movies, reality, some sports). |
| **Over-the-air locals** with an **HDHomeRun** (Flex Quatro ~$150, Flex 4K $199.99 for ATSC 3.0) + antenna | one-time | ✅ native Plex tuner (best quality, records ABC/CBS/NBC/FOX/PBS etc.). Needs an Ethernet cable to the router (not to the box), and decent signal at the house. |
| Philo | $25/mo, **7-day free trial** | ⚠️ only through FastChannels' DRM bridge (experimental) |
| Frndly TV | from $8.99/mo, **7-day free trial** | ⚠️ DRM bridge |
| Fubo | **free trial** (plans from ~$30/mo) | ⚠️ DRM bridge |
| DirecTV Stream | **5-day free trial** | ⚠️ DRM bridge |
| Sling (Freestream is free) | free tier / paid | ⚠️ DRM bridge |
| YouTube TV | free trial (offer ends Nov 16 2026), $82.99/mo | ❌ no bridge exists; use its own app |

The paid services are all encrypted (Widevine), so they can't be piped straight into Plex. The DRM bridge works by playing the channel in a real player (headless Chrome, or a cheap Fire TV/Android TV box) and capturing the output. It works, but it's the fiddly, experimental part: one channel per player at a time, CPU heavy for the Chrome path.

## Recommended plan
1. **Test (free, ~1 h):** Dispatcharr + FastChannels in a new `livetv` stack on the box (read-only of nothing, no /data needed). Free sources only, Stream Audit, pick a lineup of ~100–300 channels, add Dispatcharr to Plex as a tuner, guide from FastChannels' XMLTV. Plex Pass DVR recordings go to `/scratch/livetv-recordings` until `/data` exists.
2. **Locals:** if wanted, buy an HDHomeRun Flex Quatro/4K + antenna; Plex adds it natively (it can also feed FastChannels/Dispatcharr to sit in the same guide).
3. **Paid channels:** only if 1–2 aren't enough. Start a Philo or Frndly 7-day trial and test the DRM bridge on one channel before paying. Cancel inside the trial if it's flaky.

Box impact: both containers are small (no transcoding unless an output profile is enabled); streams are ~3–8 Mbps each over Wi-Fi. Tdarr isn't affected (no GPU use).

## YouTube TV (user has the Family plan) — Nov 10
- No official way: YouTube TV has no M3U/tuner output and its streams are DRM-encrypted.
- **PrismCast** (github hjdhjd/prismcast, active) has **YouTube TV built in** (plus Hulu, Sling, Fox, HBO Max, DirecTV Stream, Spectrum, Xfinity) and **HDHomeRun emulation for Plex**. It logs in once in its own Chrome, plays the channel, captures it with FFmpeg and serves it to Plex as a tuner, so Plex gets live TV + DVR. Docker image includes Chrome.
- Costs/limits: one Chrome capture per channel being watched/recorded (CPU encode; the box can likely do 2–3 at once next to Tdarr); up to 1080p capture quality; each tuner uses one of the plan's simultaneous streams (Family plan: 3, shared with the household); a few channels reported missing by users; guide mapping in Plex to be tested. Automated capture is against YouTube TV's terms of service (personal use; the realistic risk is account trouble, not legal).
- Alternative path: YouTube TV as a TV Everywhere login for network sources in FastChannels (ESPN, FOX, NBCU, Discovery…). Not in FastChannels' verified provider list; still DRM → bridge needed. PrismCast is the direct route.
