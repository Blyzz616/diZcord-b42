#!/usr/bin/env python3
"""
diZcord 2 — Project Zomboid (Build 42) -> Discord integration.

Single-file, stdlib-only rewrite of the original bash toolkit.
Watches the PZ server console log (and the per-user action log) and posts
rich embeds to a Discord webhook for: server up / server down, player
join / leave, deaths, rage-quits and respawns.

Requires Python 3.9+. No third-party packages. Linux + Windows.

Usage:
    python3 dizcord.py -c dizcord.ini              # run the watcher
    python3 dizcord.py -c dizcord.ini --test-webhook
    python3 dizcord.py -c dizcord.ini --verify some-log-file.txt

IMPORTANT — parser status:
    The default regexes below are carried over from the Build 41 bash
    version (reader.sh). Build 42 log formats have NOT yet been verified
    against a live 42.20 server. Every pattern marked UNVERIFIED-B42 must
    be checked with `--verify` against real logs before trusting it.
    Patterns can be overridden in the [patterns] section of the ini —
    no code change needed.
"""

import argparse
import configparser
import datetime
import json
import logging
import random
import re
import signal
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

__version__ = "2.1.0"

log = logging.getLogger("dizcord")

# --------------------------------------------------------------------------
# Discord embed colours (decimal), ported from colours.dec
# --------------------------------------------------------------------------
COLOURS = {
    "RED": 16711680,
    "ORANGE": 16753920,
    "LIME": 65280,
    "PURPLE": 8388736,
    "DARKVIOLET": 9699539,
    "DISCORDBLUE": 45015,
    "LAVENDER": 15132410,
    "CHARTREUSE": 8388352,
}

# --------------------------------------------------------------------------
# Default log patterns — carried over from B41 reader.sh.
# ALL of these are UNVERIFIED-B42 until checked against real 42.20 logs.
# Override any of them in the [patterns] ini section.
# --------------------------------------------------------------------------
DEFAULT_PATTERNS = {
    # Player joined. VERIFIED against 42.20 Logs/*_connections.txt:
    # event="fully-connected" ... ip="..." steam-id="..." ... username="..."
    "join": r"event=\"fully-connected\".*?ip=\"(?P<ip>[^\"]*)\".*?steam-id=\"(?P<steamid>\d+)\".*?username=\"(?P<username>[^\"]*)\"",
    # Player disconnected. VERIFIED against 42.20 Logs/*_connections.txt.
    "disconnect": r"event=\"disconnect\".*?ip=\"(?P<ip>[^\"]*)\".*?steam-id=\"(?P<steamid>\d+)\".*?username=\"(?P<username>[^\"]*)\"",
    # A player died. VERIFIED against 42.20 Logs/*_user.txt:
    # [dd-mm-yy hh:mm:ss.mmm] user Misty died at (x,y,z) (non pvp).
    "death": r"user (?P<name>.+?) died at \((?P<x>\d+),(?P<y>\d+),(?P<z>\d+)\)",
    # Server accepts connections. VERIFIED against 42.20 server-console.txt.
    "server_up": r"SERVER STARTED",
    # Graceful shutdown via console 'quit'. UNVERIFIED-B42: no shutdown in
    # the sample logs yet — B41 regex kept as default.
    "server_down": r"command\s+entered\s+via\s+server\s+console\s+\(System\.in\):\s+\"quit\"",
    # Wrong password / auth failure. UNVERIFIED-B42 (B41 wording).
    "denied": r"Client sent invalid server password",
}

# --------------------------------------------------------------------------
# Flavour messages, ported from reader.sh (typos fixed, flavour kept)
# --------------------------------------------------------------------------
DEATH_MESSAGES = [
    "**{name}** just died.",
    "**{name}** has now made their contribution to the horde.",
    "**{name}** swapped sides.",
    "**{name}** has now completed their playthrough.",
    "**{name}** used the wrong hole.",
    "**{name}** kicked the bucket.",
    "**{name}** decided to try something else (it did not work).",
    "**{name}** forgot to pay their tribute to the R-N-Geezus.",
    "**{name}** bought the farm.",
    "**{name}** is still walking... breathing... not so much.",
    "**{name}**'s survival story just hit a dead end.",
    "**{name}**'s journey through the apocalypse has come to an abrupt halt.",
    "RIP **{name}** — may your next respawn be more successful.",
    "The zombies threw a party, and **{name}** was the main course.",
    "**{name}** was measured. **{name}** was weighed. **{name}** was found wanting.",
    "Looks like **{name}** just rolled a nat **1**.",
    "Rest in pieces, **{name}**.",
]

RAGE_MESSAGES = [
    "Looks like **{name}**'s exit was more dramatic than their survival skills.",
    "Quitting is easy, surviving is hard. **{name}**, the zombies miss you.",
    "**{name}** decided to take a break from survival.",
    "Rage-quitting won't make the zombies go away, **{name}**. Come back and show them who's boss!",
    "Surviving the apocalypse takes grit, **{name}**. Quitting only delays the inevitable. Ready for redemption?",
    "Even the best stumble. **{name}**, the server needs your resilience. Rise from the ashes!",
    "Zombies: 1, **{name}**: 0. Are you going to let them have the last laugh?",
    "Nobody said surviving the apocalypse was easy. **{name}**, dust off those setbacks and rejoin the fight!",
    "Rage-quitting won't erase the past, **{name}**. Redemption is just a login away.",
    "The zombies might have won this round, but **{name}** isn't out for the count.",
    "Apocalypse got you down, **{name}**? Rise from the ashes and show the zombies what you're made of!",
    "Survival isn't for the faint-hearted. **{name}**, the server misses your resilience.",
    "Shame! :bell: Shame! :bell: Shame! :bell:",
]

RESPAWN_MESSAGES = [
    "Well, well, well, if it isn't **{name}**. _Back_ from the dead.",
    "Player **{name}** has rejoined the fight.",
    "**{name}** decided to play for _Team Living_ once more.",
    "If life knocks **{name}** down, they just get right back up.",
    "There's no keeping **{name}** down for long.",
    "When life hands **{name}** lemons, they do tequila shots.",
    "**{name}** returns like a phoenix from the ashes of the apocalypse.",
    "Undead beware, **{name}** is on a respawn rampage!",
    "Zombies, meet your worst nightmare: **{name}**, resurrected and ready for more.",
    "Death is just a pit-stop for **{name}** on the road of survival.",
    "Did someone say zombie buffet? **{name}** is back for seconds.",
    "New day, new character, same old **{name}** kicking zombie ass.",
    "They tried to bury **{name}**. Little did they know, it's just a respawn point.",
    "Back in the land of the living: **{name}**, the unstoppable survivor.",
]


def last_played_str(epoch):
    """'Today' / 'Yesterday' / '18 Sep 2026' from a unix timestamp."""
    if not epoch:
        return None
    d = datetime.date.fromtimestamp(epoch)
    today = datetime.date.today()
    if d == today:
        return "Today"
    if d == today - datetime.timedelta(days=1):
        return "Yesterday"
    return d.strftime("%d %b %Y")


def human_duration(secs: int) -> str:
    secs = max(0, int(secs))
    parts = []
    for unit, size in (("w", 604800), ("d", 86400), ("h", 3600), ("m", 60)):
        if secs >= size:
            parts.append(f"{secs // size}{unit}")
            secs %= size
    parts.append(f"{secs}s")
    return " ".join(parts)


# --------------------------------------------------------------------------
# Discord webhook client (urllib only, honours 429 rate limits)
# --------------------------------------------------------------------------
class Discord:
    def __init__(self, webhook_url: str, dry_run: bool = False):
        self.url = webhook_url
        self.dry_run = dry_run

    def embed(self, colour, title=None, description=None, thumbnail=None, fields=None):
        e = {"color": colour}
        if title:
            e["title"] = title
        if description:
            e["description"] = description
        if thumbnail:
            e["thumbnail"] = {"url": thumbnail}
        if fields:
            e["fields"] = fields
        self._post({"embeds": [e]})

    def _post(self, payload: dict, attempt: int = 0):
        if self.dry_run:
            log.info("[dry-run] would post: %s", json.dumps(payload))
            return
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            self.url, data=data,
            headers={"Content-Type": "application/json",
                     "User-Agent": "diZcord/2.0"})
        try:
            urllib.request.urlopen(req, timeout=15)
        except urllib.error.HTTPError as err:
            if err.code == 429 and attempt < 3:
                try:
                    wait = float(json.loads(err.read()).get("retry_after", 2))
                except Exception:
                    wait = 2.0
                log.warning("Discord rate limit, retrying in %.1fs", wait)
                time.sleep(wait + 0.2)
                self._post(payload, attempt + 1)
            elif err.code >= 500 and attempt < 3:
                time.sleep(2 * (attempt + 1))
                self._post(payload, attempt + 1)
            else:
                log.error("Discord webhook failed (%s): %s", err.code, err.reason)
        except Exception as err:  # network blips must never kill the watcher
            log.error("Discord webhook error: %s", err)


# --------------------------------------------------------------------------
# Steam profile lookup (optional enrichment for join/leave embeds)
# --------------------------------------------------------------------------
class Steam:
    """With [steam] api_key: persona name, avatar, PZ hours, other games
    (Steam Web API — get a free key at https://steamcommunity.com/dev/apikey).
    Without a key: persona name + avatar only, via the public profile XML.
    Results are cached in the state file for cache_hours."""

    PZ_APPID = 108600
    API = "https://api.steampowered.com"

    def __init__(self, cfg, state):
        s = cfg.get("steam", {})
        self.enabled = s.get("enabled", "true").strip().lower() != "false"
        self.api_key = s.get("api_key", "").strip()
        self.cache_secs = float(s.get("cache_hours", "24") or 24) * 3600
        self.state = state

    def profile(self, steamid: str) -> dict:
        if not self.enabled or not steamid:
            return {}
        cache = self.state.data.setdefault("steam_cache", {})
        hit = cache.get(steamid)
        if hit and time.time() - hit.get("at", 0) < self.cache_secs:
            return hit
        info = {"at": time.time()}
        try:
            if self.api_key:
                self._fill_from_api(steamid, info)
            else:
                self._fill_from_xml(steamid, info)
        except Exception as err:   # enrichment must never break announcements
            log.warning("Steam lookup failed for %s: %s", steamid, err)
            if hit:                # keep serving stale data over nothing
                return hit
        cache[steamid] = info
        self.state.save()
        return info

    def _fetch(self, url: str) -> bytes:
        req = urllib.request.Request(
            url, headers={"User-Agent": f"diZcord/{__version__}"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.read()

    def _fill_from_api(self, steamid, info):
        q = urllib.parse.urlencode({"key": self.api_key, "steamids": steamid})
        data = json.loads(self._fetch(
            f"{self.API}/ISteamUser/GetPlayerSummaries/v2/?{q}"))
        players = data.get("response", {}).get("players", [])
        if players:
            info["persona"] = players[0].get("personaname")
            info["avatar"] = players[0].get("avatarfull")

        q = urllib.parse.urlencode({
            "key": self.api_key, "steamid": steamid,
            "include_appinfo": 1, "include_played_free_games": 1})
        data = json.loads(self._fetch(
            f"{self.API}/IPlayerService/GetOwnedGames/v1/?{q}"))
        others = []
        for g in data.get("response", {}).get("games", []):
            if g.get("appid") == self.PZ_APPID:
                info["pz_hours"] = g.get("playtime_forever", 0) // 60
            elif g.get("playtime_forever", 0) >= 60:   # >= 1h played
                others.append(g)
        others.sort(key=lambda g: g.get("rtime_last_played", 0), reverse=True)
        info["games"] = [{"name": g.get("name", "?"),
                          "hours": g.get("playtime_forever", 0) // 60,
                          "last": g.get("rtime_last_played")}
                         for g in others[:2]]

    def _fill_from_xml(self, steamid, info):
        xml = self._fetch(
            f"https://steamcommunity.com/profiles/{steamid}?xml=1"
        ).decode("utf-8", "replace")
        m = re.search(r"<steamID><!\[CDATA\[(.*?)\]\]></steamID>", xml, re.S)
        if m:
            info["persona"] = m.group(1)
        m = re.search(r"<avatarFull><!\[CDATA\[(.*?)\]\]></avatarFull>", xml, re.S)
        if m:
            info["avatar"] = m.group(1)


# --------------------------------------------------------------------------
# Rotation/truncation-safe polling tailer (cross-platform, no inotify)
# --------------------------------------------------------------------------
class Tail:
    """Follows a file whose path is produced by path_fn (re-evaluated each
    poll so rotating files like Logs/*_user.txt are picked up)."""

    def __init__(self, path_fn, from_start=False):
        self.path_fn = path_fn
        self.fh = None
        self.path = None
        self.sig = None          # (st_dev, st_ino) where supported
        self.from_start = from_start
        self.buf = ""

    def _signature(self, path: Path):
        try:
            st = path.stat()
            return (st.st_dev, st.st_ino, )
        except OSError:
            return None

    def _open(self, path: Path, seek_end: bool):
        try:
            self.fh = open(path, "r", encoding="utf-8", errors="replace")
        except OSError:
            self.fh = None
            return
        self.path = path
        self.sig = self._signature(path)
        self.buf = ""
        if seek_end:
            self.fh.seek(0, 2)

    def poll(self):
        """Return a list of new complete lines since last poll."""
        target = self.path_fn()
        if target is None:
            return []
        target = Path(target)

        if self.fh is None:
            self._open(target, seek_end=not self.from_start)
            if self.fh is None:
                return []
        elif target != self.path or self._signature(target) != self.sig:
            # rotated / replaced: read new file from the beginning
            self.fh.close()
            self._open(target, seek_end=False)
            if self.fh is None:
                return []
        else:
            try:
                if target.stat().st_size < self.fh.tell():
                    self.fh.seek(0)  # truncated in place
            except OSError:
                pass

        chunk = self.fh.read()
        if not chunk:
            return []
        self.buf += chunk
        lines = self.buf.split("\n")
        self.buf = lines.pop()  # keep incomplete tail
        return [ln.rstrip("\r") for ln in lines if ln.strip()]

    def close(self):
        if self.fh:
            self.fh.close()
            self.fh = None


# --------------------------------------------------------------------------
# Persistent state (single JSON file instead of B41's scattered flag files)
# --------------------------------------------------------------------------
class State:
    def __init__(self, path: Path):
        self.path = path
        self.data = {
            "server_up_since": None,      # epoch when SERVER STARTED seen
            "watcher_started": None,      # epoch when this process started
            "sessions": {},               # steamid -> session start epoch
            "totals": {},                 # steamid -> lifetime seconds
            "players": {},                # steamid -> {"login": name}
            "logins": {},                 # login name -> steamid
            "dead": {},                   # steamid -> epoch of death
        }
        if path.exists():
            try:
                self.data.update(json.loads(path.read_text(encoding="utf-8")))
            except Exception as err:
                log.warning("Could not read state file (%s), starting fresh", err)

    def save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, indent=1), encoding="utf-8")
            tmp.replace(self.path)
        except OSError as err:
            log.error("Could not save state: %s", err)


# --------------------------------------------------------------------------
# The watcher: wires patterns -> events -> Discord
# --------------------------------------------------------------------------
class Watcher:
    def __init__(self, cfg, discord: Discord, state: State):
        self.cfg = cfg
        self.discord = discord
        self.state = state
        self.patterns = {name: re.compile(rx) for name, rx in cfg["patterns"].items()}
        self.steam = Steam(cfg, state)
        self.server_name = cfg["server"]["name"]
        self.respawn_window = int(cfg["dizcord"].get("respawn_window", "600"))

        zdir = Path(cfg["server"]["zomboid_dir"]).expanduser()
        console = cfg["server"].get("console_log") or str(zdir / "server-console.txt")
        self.console_tail = Tail(lambda: Path(console))
        logs_dir = Path(cfg["server"].get("logs_dir") or (zdir / "Logs"))
        self.user_tail = Tail(lambda: self._latest_log(logs_dir, "*_user.txt"))
        self.conn_tail = Tail(lambda: self._latest_log(logs_dir, "*_connections.txt"))

    @staticmethod
    def _latest_log(logs_dir: Path, pattern: str):
        """Newest matching log in Logs/ root (archived sessions live in
        dated subfolders, which glob() deliberately does not descend into)."""
        try:
            candidates = sorted(logs_dir.glob(pattern),
                                key=lambda p: p.stat().st_mtime)
            return candidates[-1] if candidates else None
        except OSError:
            return None

    # ---------------- event handlers ----------------
    def handle_line(self, line: str):
        for name, rx in self.patterns.items():
            m = rx.search(line)
            if m:
                getattr(self, f"on_{name}", self.on_unknown)(m, line)

    def on_unknown(self, m, line):
        pass

    def on_server_up(self, m, line):
        now = time.time()
        started = self.state.data.get("watcher_started")
        self.state.data["server_up_since"] = now
        self.state.save()
        desc = None
        if started and now - started < 3600:
            desc = f"Server took {human_duration(now - started)} to come online."
        self.discord.embed(COLOURS["LIME"],
                           title=f"{self.server_name} is now **ONLINE**",
                           description=desc)

    def on_server_down(self, m, line):
        up_since = self.state.data.get("server_up_since")
        desc = (f"The server was up for {human_duration(time.time() - up_since)}"
                if up_since else "Server shutting down.")
        self.state.data["server_up_since"] = None
        self.state.save()
        self.discord.embed(COLOURS["ORANGE"],
                           title=f"{self.server_name} is going **DOWN**",
                           description=desc)

    def on_join(self, m, line):
        d = m.groupdict()
        steamid = d.get("steamid", "")
        # B42 console gives no username; fall back to last known login or id
        username = (d.get("username")
                    or self.state.data["players"].get(steamid, {}).get("login")
                    or steamid)
        now = time.time()
        st = self.state.data
        st["sessions"].setdefault(steamid, now)  # respawn keeps session start
        st["players"].setdefault(steamid, {})["login"] = username
        st["logins"][username] = steamid

        sp = self.steam.profile(steamid)
        persona = sp.get("persona") or username
        avatar = sp.get("avatar")

        death_at = st["dead"].get(steamid)
        if death_at and now - death_at <= self.respawn_window:
            del st["dead"][steamid]
            self.state.save()
            self.discord.embed(
                COLOURS["DARKVIOLET"], title="Respawn notice:",
                description=random.choice(RESPAWN_MESSAGES).format(name=username),
                thumbnail=avatar)
            return
        st["dead"].pop(steamid, None)
        self.state.save()

        profile = f"https://steamcommunity.com/profiles/{steamid}"
        fields = []
        if sp.get("pz_hours") is not None:
            fields.append({"name": "Hours on Record:",
                           "value": f"{sp['pz_hours']:,}", "inline": False})
        if sp.get("games"):
            fields.append({"name": f"{persona} has also played:",
                           "value": "​", "inline": False})
            for g in sp["games"]:
                value = f"{g['hours']:,} hrs on record"
                last = last_played_str(g.get("last"))
                if last:
                    value += f"\nLast played: {last}"
                fields.append({"name": g["name"], "value": value, "inline": True})
        self.discord.embed(
            COLOURS["PURPLE"], title="New connection:",
            description=(f"Steam Profile: [{persona}]({profile})\n"
                         f"Logging in as **{username}**"),
            thumbnail=avatar, fields=fields or None)

    def on_disconnect(self, m, line):
        d = m.groupdict()
        steamid = d.get("steamid", "")
        st = self.state.data
        name = (d.get("username")
                or st["players"].get(steamid, {}).get("login")
                or steamid or "Unknown")
        now = time.time()

        session = None
        if steamid in st["sessions"]:
            session = now - st["sessions"].pop(steamid)
            st["totals"][steamid] = st["totals"].get(steamid, 0) + session

        avatar = st.get("steam_cache", {}).get(steamid, {}).get("avatar")
        lines = []
        if session is not None:
            total = st["totals"][steamid]
            lines.append(f"{name} was online for {human_duration(session)}")
            lines.append(f"Total time on server:\n{human_duration(total)}")
            if total >= 3600:
                lines.append(f"({int(total // 3600)} Hours)")

        if steamid in st["dead"]:
            del st["dead"][steamid]
            self.state.save()
            msg = random.choice(RAGE_MESSAGES).format(name=name)
            self.discord.embed(COLOURS["RED"], title=f"{name} rage-quit",
                               description="\n".join([msg, ""] + lines),
                               thumbnail=avatar)
        else:
            self.state.save()
            self.discord.embed(COLOURS["RED"], title=f"{name} has disconnected",
                               description="\n".join(lines) or None,
                               thumbnail=avatar)

    def on_death(self, m, line):
        name = m.groupdict().get("name", "?")
        steamid = self.state.data["logins"].get(name)
        if steamid:
            self.state.data["dead"][steamid] = time.time()
            self.state.save()
        self.discord.embed(COLOURS["RED"],
                           description=random.choice(DEATH_MESSAGES).format(name=name))

    def on_denied(self, m, line):
        self.discord.embed(COLOURS["RED"],
                           title="Access denied — check your credentials.")

    # ---------------- main loop ----------------
    def run(self):
        self.state.data["watcher_started"] = time.time()
        self.state.save()
        poll = float(self.cfg["dizcord"].get("poll_interval", "0.5"))
        log.info("diZcord watching %s", self.server_name)
        running = True

        def stop(*_):
            nonlocal running
            running = False
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, stop)
            except (ValueError, OSError):
                pass

        while running:
            for tail in (self.console_tail, self.user_tail, self.conn_tail):
                for line in tail.poll():
                    self.handle_line(line)
            time.sleep(poll)

        self.console_tail.close()
        self.user_tail.close()
        self.conn_tail.close()
        log.info("diZcord stopped.")


# --------------------------------------------------------------------------
# Config / CLI
# --------------------------------------------------------------------------
def load_config(path: Path) -> dict:
    ini = configparser.ConfigParser()
    if not ini.read(path, encoding="utf-8"):
        sys.exit(f"Config file not found: {path}")
    cfg = {s: dict(ini[s]) for s in ini.sections()}
    cfg.setdefault("dizcord", {})
    cfg.setdefault("server", {})
    if "name" not in cfg["server"]:
        cfg["server"]["name"] = "Project Zomboid"
    if "zomboid_dir" not in cfg["server"]:
        cfg["server"]["zomboid_dir"] = "~/Zomboid"
    patterns = dict(DEFAULT_PATTERNS)
    patterns.update(cfg.get("patterns", {}))
    cfg["patterns"] = patterns
    if not cfg.get("discord", {}).get("webhook_url"):
        sys.exit("Missing [discord] webhook_url in config.")
    return cfg


def cmd_verify(cfg: dict, log_path: Path):
    """Replay an existing log file through the parsers and report matches."""
    patterns = {name: re.compile(rx) for name, rx in cfg["patterns"].items()}
    counts = {name: 0 for name in patterns}
    samples = {name: [] for name in patterns}
    total = 0
    with open(log_path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            total += 1
            for name, rx in patterns.items():
                m = rx.search(line)
                if m:
                    counts[name] += 1
                    if len(samples[name]) < 3:
                        samples[name].append((line.strip()[:160], m.groupdict()))
    print(f"\nScanned {total} lines of {log_path}\n")
    for name in patterns:
        status = f"{counts[name]} match(es)" if counts[name] else "NO MATCHES"
        print(f"  {name:<12} {status}")
        for text, groups in samples[name]:
            print(f"      | {text}")
            if groups:
                print(f"      -> {groups}")
    print("\nPatterns with NO MATCHES either didn't occur in this log, or the "
          "B42 format differs\nfrom the B41 default regex — override them in "
          "the [patterns] section of your ini.\n")


def main():
    ap = argparse.ArgumentParser(description="diZcord 2 — PZ B42 Discord integration")
    ap.add_argument("-c", "--config", default="dizcord.ini", type=Path)
    ap.add_argument("--test-webhook", action="store_true",
                    help="send a test embed to the webhook and exit")
    ap.add_argument("--verify", metavar="LOGFILE", type=Path,
                    help="replay a log file through the parsers and report matches")
    ap.add_argument("--dry-run", action="store_true",
                    help="log embeds instead of posting them")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s")

    cfg = load_config(args.config)

    if args.verify:
        cmd_verify(cfg, args.verify)
        return

    discord = Discord(cfg["discord"]["webhook_url"], dry_run=args.dry_run)

    if args.test_webhook:
        discord.embed(COLOURS["DISCORDBLUE"], title="diZcord test",
                      description="If you can read this, the webhook works.")
        print("Test embed sent.")
        return

    state_path = Path(cfg["dizcord"].get(
        "state_file", "~/.dizcord/state.json")).expanduser()
    watcher = Watcher(cfg, discord, State(state_path))
    watcher.run()


if __name__ == "__main__":
    main()
