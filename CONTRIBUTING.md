# Contributing to diZcord 2

Thanks for helping improve diZcord! Issues and pull requests are welcome.

## Ground rules

- Keep `dizcord.py` a **single file** using **only the Python standard
  library** (3.9+). No pip dependencies — server admins should be able to
  install with nothing but `apt install python3`.
- One change per pull request.

## Before opening a pull request

1. **Syntax check:** `python3 -m py_compile dizcord.py`
2. **Dry run:** run your change against a real or copied log setup
   without spamming Discord:

   ```bash
   python3 dizcord.py -c dizcord.ini --dry-run -v
   ```

3. **If you changed or added a parser regex**, verify it against your
   server's actual log files:

   ```bash
   python3 dizcord.py -c dizcord.ini --verify ~/Zomboid/server-console.txt
   python3 dizcord.py -c dizcord.ini --verify ~/Zomboid/Logs/<file>.txt
   ```

   Your event should show matches with the correct named groups
   (`steamid`, `username`, `name`, etc.).

## Parser PRs: include evidence

Project Zomboid log formats change between builds, so every parser change
must come with proof. In the PR description, paste:

- The **real log line(s)** the pattern matches (redact your IP/Steam ID
  if you like — keep the line shape intact)
- The PZ **build number** it came from (e.g. 42.20.0)
- The `--verify` output showing the match

## Reporting bugs

Open an issue with: your PZ build, your OS, the relevant log lines from
`journalctl -u dizcord` (or the console), and what you expected vs. what
happened. If an event isn't being announced, `--verify` output for the
relevant log file is the fastest path to a fix.

## Feature ideas

Check `ROADMAP.md` first — if it's listed, comment on or open an issue to
claim it. If it's not listed, open an issue to discuss before writing
code, so nobody wastes effort.
