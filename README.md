# diZcord 2

Project Zomboid (Build 42) → Discord integration.

Watches your PZ server's log files and posts rich embeds to a Discord
webhook: server up/down, player joins and disconnects, deaths, rage-quits
and respawns — with the flavour messages diZcord is known for.

Successor to [Blyzz616/diZcord](https://github.com/Blyzz616/diZcord)
(Build 41, bash). Rewritten from scratch in Python for Build 42.

## Features (working, verified against a live 42.20 server)

| Event | Source | Discord output |
|---|---|---|
| Server online | `server-console.txt` (`SERVER STARTED`) | "ONLINE" embed with startup duration |
| Player join | `Logs/*_connections.txt` (`event="fully-connected"`) | Username + Steam profile link |
| Player disconnect | `Logs/*_connections.txt` (`event="disconnect"`) | Session time + lifetime playtime |
| Death | `Logs/*_user.txt` (`user X died at (x,y,z)`) | Random obituary message |
| Rage-quit | death followed by disconnect | Shaming message + playtimes |
| Respawn | death followed by re-join | Respawn message |

Also included:

- Rotation-safe log tailing (server restarts and log archiving handled)
- Discord rate-limit handling with retry
- Persistent state (`state.json`): per-player session and lifetime playtime
- `--verify` mode: replay any log file through the parsers and see what matches
- `--dry-run` and `--test-webhook` for safe testing
- All parser regexes overridable in the config file — a PZ update that
  changes a log line means an ini edit, not a code change

Known gaps: the server-shutdown and wrong-password parsers still carry
B41-era patterns and are unverified on B42 (see ROADMAP.md).

## Requirements

- The machine running the Project Zomboid dedicated server
- Python 3.9+ — the **only** dependency; no pip packages needed
- A Discord webhook URL for the target channel
  (Discord: channel → Edit Channel → Integrations → Webhooks → New Webhook)

Developed and tested on Linux; written to be Windows-compatible
(polling-based tailing, no OS-specific calls) but not yet tested there.

## Installation (fresh server, nothing pre-installed)

Run as a user that can read the Zomboid folder (e.g. `pzserver`).

```bash
# 1. Install Python (Debian/Ubuntu — most distros already ship it)
sudo apt update && sudo apt install -y python3 git

# 2. Get diZcord
sudo mkdir -p /opt/dizcord
sudo chown "$USER":"$USER" /opt/dizcord
git clone https://github.com/Blyzz616/diZcord-b42.git /opt/dizcord
cd /opt/dizcord

# 3. Configure
cp dizcord.ini.example dizcord.ini
nano dizcord.ini        # set webhook_url, server name, zomboid_dir

# 4. Test the webhook (posts a test embed to your channel)
python3 dizcord.py -c dizcord.ini --test-webhook

# 5. Verify the parsers against YOUR logs before going live
python3 dizcord.py -c dizcord.ini --verify ~/Zomboid/server-console.txt
python3 dizcord.py -c dizcord.ini --verify ~/Zomboid/Logs/*_connections.txt
python3 dizcord.py -c dizcord.ini --verify ~/Zomboid/Logs/*_user.txt
# Any "NO MATCHES" for an event you know is in that log => override the
# regex in the [patterns] section of dizcord.ini.
```

### Run it (recommended: systemd)

```bash
sudo cp dizcord.service /etc/systemd/system/
sudo nano /etc/systemd/system/dizcord.service   # check User= and paths
sudo systemctl daemon-reload
sudo systemctl enable --now dizcord
systemctl status dizcord          # check it's running
journalctl -u dizcord -f          # follow its logs
```

diZcord only reads log files, so start/stop order relative to the PZ
server doesn't matter — it picks up a restarting server automatically.

### Run it (quick and dirty: screen)

```bash
sudo apt install -y screen
screen -dmS dizcord python3 /opt/dizcord/dizcord.py -c /opt/dizcord/dizcord.ini
screen -r dizcord                 # attach; Ctrl+A then D to detach
```

## Configuration

Everything lives in `dizcord.ini` — see `dizcord.ini.example` for all
options with comments. The essentials:

```ini
[server]
name = My PZ Server
zomboid_dir = ~/Zomboid

[discord]
webhook_url = https://discord.com/api/webhooks/XXXX/YYYY
```

## Updating

```bash
cd /opt/dizcord && git pull && sudo systemctl restart dizcord
```

Your `dizcord.ini` and state file are untouched by updates.

## Troubleshooting

- Nothing posts: run with `--dry-run -v` to see what the watcher parses
  without spamming Discord.
- Events missing: run `--verify` on the relevant log file — B42 splits
  events across `server-console.txt`, `Logs/*_connections.txt` and
  `Logs/*_user.txt`.
- Server can't write its own config (`Permission denied` on
  `Zomboid/Server/*.ini` in the console log): fix ownership with
  `sudo chown -R pzserver:pzserver ~pzserver/Zomboid`.

## Contributing

Improvements welcome — please open issues and pull requests against this
repo so everyone benefits.

## License

MIT — see `LICENSE`. Use it, ship it, modify it; no credit required.
