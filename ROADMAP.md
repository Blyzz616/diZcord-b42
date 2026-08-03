# Roadmap

Rough order of attack. Unchecked items are open; nothing here is promised.

## Near term — reliability of the core

- [ ] Verify `server_down` against a real B42.20 graceful shutdown
      (capture the console/DebugLog tail when running `quit`)
- [ ] Verify `denied` (wrong password) against a real failed join
- [ ] Handle joins that never reach `fully-connected` (login queue
      abandoned) without leaving stale state
- [ ] Death coordinates in embeds (parser already captures x,y,z) —
      optional, off by default (base-location privacy)
- [ ] Unit tests from the verified real log lines; run in CI

## Features returning from the B41 version

- [ ] Timed restart warnings (`restart.sh` replacement): in-game
      broadcast via RCON + Discord countdown embeds
- [ ] Server-up announcements distinguishing restart vs. crash recovery
- [ ] Steam profile enrichment on join: avatar thumbnail, hours in PZ —
      via Steam Web API this time, not HTML scraping
- [ ] Geo-IP country flag on join (opt-in only)
- [ ] Playtime records: per-user totals surfaced on demand
      (B41's users.log / access.log equivalents live in state.json)
- [ ] Helicopter / Expanded Helicopter Events announcements
- [ ] Discord bot control (boidbot successor) — server commands from a
      Discord channel, carefully permission-gated

## New for diZcord 2

- [ ] Windows support: test the watcher on a Windows PZ server
- [ ] Multiple PZ servers on one box (multiple configs / one process)
- [ ] Guided first-run setup (wizard.sh successor): interactive
      `--setup` that finds the Zomboid dir and writes dizcord.ini
- [ ] Mod-update detection → scheduled restart (modcheck.sh successor)
- [ ] Per-event enable/disable and per-event webhook overrides in the ini
- [ ] Localised / user-customisable message packs (drop-in JSON)
- [ ] Release packaging: versioned GitHub releases + self-update check

## Ideas parked from the old README

- [ ] Steam Workshop presence for discoverability
- [ ] Death/PVP statistics summaries (weekly digest embed)
