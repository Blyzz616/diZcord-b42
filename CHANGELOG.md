# Changelog

All notable changes to diZcord 2 are documented here.
Versioning: X.Y.Z — X breaking, Y feature, Z fix.

## [Unreleased]

- Server-shutdown (`server_down`) and wrong-password (`denied`) parsers
  still carry B41 patterns; awaiting real B42.20 captures to verify.

## [2.0.0] - 2026-08-03

First Build 42 release. Complete rewrite of the Build 41 bash toolkit
(reader.sh and friends) as a single-file, stdlib-only Python watcher.

### Added

- `dizcord.py`: one process tails `server-console.txt`,
  `Logs/*_connections.txt` and `Logs/*_user.txt` and posts Discord embeds.
- Events verified against a live 42.20 server: server online, player join
  (username, Steam profile link), player disconnect (session + lifetime
  playtime), death (random obituaries), rage-quit detection, respawn
  detection.
- INI configuration with parser regexes overridable per event — log format
  changes need no code edits.
- `--verify` mode to replay log files through the parsers and report
  matches per event.
- `--dry-run` and `--test-webhook` modes.
- Rotation/truncation-safe polling tailer (works across server restarts
  and log archiving; no inotify dependency, Windows-compatible).
- Discord webhook client with 429 rate-limit retry and 5xx backoff.
- Single JSON state file replacing B41's scattered flag files
  (sessions, lifetime playtime, death flags, login↔steamid mapping).
- `dizcord.service` systemd unit.

### Changed

- Log sources updated for Build 42: the B41 console `[fully-connected]` /
  `[disconnect]` lines no longer exist; joins and disconnects are now read
  from `Logs/*_connections.txt`, deaths from `Logs/*_user.txt`.
- Flavour messages ported from B41 reader.sh with typo fixes.

### Removed (vs. the B41 bash version — see ROADMAP.md for what returns)

- Whiptail install wizard, timed restart warnings, helicopter/EHE events,
  Steam profile scraping (avatars/hours), geo-IP lookup, boidbot Discord
  bot, player database text logs.
