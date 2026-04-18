"""Unified launcher for all telegram farming services.

Runs as a single Railway worker. Spawns:
  - farmclickers   (Yescoin/DotCoin/Cats, WebApp init_data tokens in data.txt)
  - majorbot       (Major, Pyrogram session-based)
  - notpixel       (NotPixel, WebApp init_data tokens in data.txt)
  - tomarketod     (Tomarket, WebApp init_data tokens in data.txt)

Responsibilities:
  1. Validate required env vars (API_ID, API_HASH).
  2. Materialize farmclickers/.env from env vars (the upstream project reads a .env file, not the OS environment).
  3. Link data files from a persistent /data volume (Railway) into each service dir, if /data exists.
  4. Spawn each enabled service as a subprocess with prefixed, line-buffered logs.
  5. Auto-restart any crashed subprocess after a backoff.
  6. Forward SIGTERM/SIGINT to children for clean Railway shutdowns.

Enable/disable a service with env flags:
  ENABLE_FARMCLICKERS=1   (default 1)
  ENABLE_MAJORBOT=1       (default 1)
  ENABLE_NOTPIXEL=1       (default 1)
  ENABLE_TOMARKETOD=1     (default 1)
"""

from __future__ import annotations

import base64
import collections
import gzip
import os
import platform
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SERVICES = ROOT / "services"
DATA_VOLUME = Path(os.environ.get("DATA_VOLUME", "/data"))
START_TIME = time.time()
HEARTBEAT_INTERVAL_SEC = int(os.environ.get("HEARTBEAT_INTERVAL_SEC", "600"))

COLORS = {
    "farmclickers": "\033[36m",  # cyan
    "majorbot": "\033[34m",      # blue
    "notpixel": "\033[35m",      # magenta
    "tomarketod": "\033[33m",    # yellow
    "launcher": "\033[32m",      # green
    "reset": "\033[0m",
}


def log(tag: str, msg: str) -> None:
    color = COLORS.get(tag, "")
    reset = COLORS["reset"]
    sys.stdout.write(f"{color}[{tag}]{reset} {msg}\n")
    sys.stdout.flush()


def fmt_uptime(seconds: float) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h{m:02d}m{s:02d}s"
    if m:
        return f"{m}m{s:02d}s"
    return f"{s}s"


# ---------------------------------------------------------------------------
# Startup self-diagnostic
# ---------------------------------------------------------------------------

_ENV_KEYS_SHOW_VALUE = {"ENABLE_FARMCLICKERS", "ENABLE_MAJORBOT", "ENABLE_NOTPIXEL", "ENABLE_TOMARKETOD",
                        "HEARTBEAT_INTERVAL_SEC", "DATA_VOLUME",
                        "FARMCLICKERS_SESSION_NAME", "MAJORBOT_SESSION_NAME", "NOTPIXEL_SESSION_NAME"}
_ENV_KEYS_WATCH = [
    "API_ID", "API_HASH",
    "FARMCLICKERS_DATA",
    "FARMCLICKERS_SESSION_NAME", "FARMCLICKERS_SESSION_B64",
    "MAJORBOT_SESSION_NAME", "MAJORBOT_SESSION_B64",
    "ENABLE_MAJORBOT",
    "NOTPIXEL_DATA",
    "NOTPIXEL_SESSION_NAME", "NOTPIXEL_SESSION_B64",
    "TOMARKET_DATA",
    "ENABLE_FARMCLICKERS", "ENABLE_NOTPIXEL", "ENABLE_TOMARKETOD",
    "HEARTBEAT_INTERVAL_SEC", "DATA_VOLUME",
]


def describe_env_var(key: str, value: str) -> str:
    if not value:
        return "unset"
    if key in _ENV_KEYS_SHOW_VALUE:
        return f"SET = {value}"
    if key in ("FARMCLICKERS_DATA", "NOTPIXEL_DATA", "TOMARKET_DATA"):
        nlines = len([l for l in value.splitlines() if l.strip()])
        return f"SET ({nlines} non-empty line(s), {len(value)} chars total)"
    if key == "API_ID":
        return f"SET = {value}"
    return f"SET ({len(value)} chars)"


def startup_diagnostic() -> None:
    log("launcher", "=" * 60)
    log("launcher", f"farmtgbot launcher starting at {time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    log("launcher", f"Python:   {sys.version.split()[0]}")
    log("launcher", f"Platform: {platform.platform()}")
    log("launcher", f"CWD:      {os.getcwd()}")
    log("launcher", f"ROOT:     {ROOT}")
    log("launcher", "Env vars (presence only; values hidden for secrets):")
    for key in _ENV_KEYS_WATCH:
        value = os.environ.get(key, "")
        log("launcher", f"  {key}: {describe_env_var(key, value)}")
    log("launcher", "=" * 60)


def session_inventory() -> None:
    """Print the state of each service's on-disk data files."""
    log("launcher", "Data file inventory:")

    for svc_name, data_path in [
        ("farmclickers", SERVICES / "farmclickers" / "data.txt"),
        ("notpixel", SERVICES / "notpixel" / "data.txt"),
        ("tomarketod", SERVICES / "tomarketod" / "data.txt"),
    ]:
        if data_path.exists():
            try:
                lines = [l for l in data_path.read_text().splitlines() if l.strip()]
                log("launcher", f"  {svc_name}: data.txt has {len(lines)} non-empty line(s)")
            except OSError as e:
                log("launcher", f"  {svc_name}: data.txt read error: {e}")
        else:
            log("launcher", f"  {svc_name}: data.txt MISSING")

    tokens_json = SERVICES / "tomarketod" / "tokens.json"
    if tokens_json.exists():
        log("launcher", f"  tomarketod: tokens.json present ({tokens_json.stat().st_size} bytes)")
    else:
        log("launcher", "  tomarketod: tokens.json MISSING (will be created on first run)")

    for svc_name, sessions_dir in [
        ("farmclickers", SERVICES / "farmclickers" / "sessions"),
        ("notpixel", SERVICES / "notpixel" / "sessions"),
        ("majorbot", SERVICES / "majorbot" / "sessions"),
    ]:
        if sessions_dir.exists():
            session_files = list(sessions_dir.glob("*.session"))
            if session_files:
                for sf in session_files:
                    log("launcher", f"  {svc_name}: session {sf.name} ({sf.stat().st_size} bytes)")
            else:
                log("launcher", f"  {svc_name}: sessions/ dir exists but no .session files")


# ---------------------------------------------------------------------------
# Env validation
# ---------------------------------------------------------------------------

def require_env() -> tuple[str, str]:
    api_id = os.environ.get("API_ID", "").strip()
    api_hash = os.environ.get("API_HASH", "").strip()
    if not api_id or not api_id.isdigit():
        log("launcher", "FATAL: API_ID env var missing or not numeric. Set it in Railway > Variables.")
        sys.exit(1)
    if not api_hash:
        log("launcher", "FATAL: API_HASH env var missing. Set it in Railway > Variables.")
        sys.exit(1)
    return api_id, api_hash


# ---------------------------------------------------------------------------
# farmclickers needs a .env file materialized from the OS environment, because
# pydantic-settings in that project reads from .env only.
# ---------------------------------------------------------------------------

FARMCLICKERS_ENV_TEMPLATE = """\
API_ID = {api_id}
API_HASH = '{api_hash}'

USE_PROXY = False
PROXY_TYPE = "socks5"

SOFT_BOTS_DELAY = [600, 900]
SOFT_CIRCLES_NUM = 9999
SOFT_CIRCLES_DELAY = [21000, 25000]

ACC_DELAY = [0, 200]
MINI_SLEEP = [20, 80]
USE_TAPS = True

USE_TG_BOT = False
CHAT_ID = ''
BOT_TOKEN = ''

BOTS_DATA= '{{
    "blum" : {{
        "is_connected": false,
        "ref_code": "ref_qIFL0xYd8i",
        "errors_before_stop": 2,
        "spend_diamonds": true,
        "max_games_count": [10, 20],
        "points": [120, 190],
        "sleep_game_time": [60, 180],
        "do_tasks": true
    }},
    "major" : {{
        "is_connected": false,
        "ref_code": "6046075760",
        "errors_before_stop": 2,
        "play_hold_coin": true,
        "play_roulette": true,
        "play_swipe_coin": true,
        "join_squad": true,
        "task_sleep": [30, 120],
        "game_sleep": [60, 180]
    }},
    "yescoin" : {{
        "is_connected": false,
        "ref_code": "KWWehI",
        "errors_before_stop": 2,
        "do_tasks": true,
        "upgrade": true,
        "max_upgrade_lvl": 7,
        "min_energy": 50,
        "use_chests": true,
        "use_energy_recover": true,
        "clicks_sleep": [60, 180],
        "tasks_sleep": [10, 40]
    }},
    "dotcoin" : {{
        "is_connected": false,
        "ref_code": "r_6046075760",
        "errors_before_stop": 2,
        "auto_upgrade_tap": true,
        "max_tap_level": 5,
        "auto_upgrade_attempts": true,
        "max_attempts_level": 5,
        "random_taps_count": [50, 200],
        "taps_sleep": [10, 25]
    }},
    "cats" : {{
        "is_connected": false,
        "ref_code": "18awB6nNqqe8928y1u4vp",
        "errors_before_stop": 2,
        "do_photos": true,
        "task_sleep": [40, 120]
    }}
}}'
"""


def materialize_farmclickers_env(api_id: str, api_hash: str) -> None:
    target = SERVICES / "farmclickers" / ".env"
    target.write_text(FARMCLICKERS_ENV_TEMPLATE.format(api_id=api_id, api_hash=api_hash))
    log("launcher", f"Wrote {target.relative_to(ROOT)}")


MAJORBOT_ENV_TEMPLATE = """\
API_ID={api_id}
API_HASH={api_hash}

REF_ID=339631649
SQUAD_ID=2237841784
TASKS_WITH_JOIN_CHANNEL=False
HOLD_COIN=[585, 600]
SWIPE_COIN=[2000, 3000]
USE_RANDOM_DELAY_IN_RUN=True
RANDOM_DELAY_IN_RUN=[0, 15]
FAKE_USERAGENT=True
SLEEP_TIME=[1800, 3600]
USE_PROXY_FROM_FILE=False
"""


def materialize_majorbot_env(api_id: str, api_hash: str) -> None:
    target = SERVICES / "majorbot" / ".env"
    target.write_text(MAJORBOT_ENV_TEMPLATE.format(api_id=api_id, api_hash=api_hash))
    log("launcher", f"Wrote {target.relative_to(ROOT)}")


# ---------------------------------------------------------------------------
# Materialize data files from env vars.
#
# All three services now use plain-text init_data tokens in data.txt files.
# Env vars contain init_data lines (one per account, newline-separated).
#
# Expected env vars (all optional - missing ones just skip that service):
#   FARMCLICKERS_DATA          raw init_data tokens (one line per account)
#   NOTPIXEL_DATA              raw init_data tokens (one line per account)
#   TOMARKET_DATA              raw init_data tokens (one line per account)
#
# Fallback: if a /data volume is mounted, we symlink from there instead
# (kept for users who prefer volumes over env vars).
# ---------------------------------------------------------------------------

def materialize_data_from_env() -> None:
    entries = [
        ("FARMCLICKERS_DATA", SERVICES / "farmclickers" / "data.txt"),
        ("NOTPIXEL_DATA",     SERVICES / "notpixel"     / "data.txt"),
        ("TOMARKET_DATA",     SERVICES / "tomarketod"   / "data.txt"),
    ]
    for env_key, target in entries:
        data = os.environ.get(env_key, "").strip()
        if not data:
            continue
        if target.exists() and target.read_text().strip():
            log("launcher", f"  {target.relative_to(ROOT)} already populated - not overwriting from {env_key}")
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(data + "\n")
            nlines = len([l for l in data.splitlines() if l.strip()])
            log("launcher", f"  wrote {target.relative_to(ROOT)} from {env_key} ({nlines} line(s))")


def materialize_sessions_from_env() -> None:
    """Decode and write Pyrogram session files from *_SESSION_NAME + *_SESSION_B64 env vars."""
    session_mappings = [
        ("FARMCLICKERS", SERVICES / "farmclickers" / "sessions"),
        ("NOTPIXEL",     SERVICES / "notpixel"     / "sessions"),
        ("MAJORBOT",     SERVICES / "majorbot"     / "sessions"),
    ]
    for prefix, sessions_dir in session_mappings:
        name = os.environ.get(f"{prefix}_SESSION_NAME", "").strip()
        b64_data = os.environ.get(f"{prefix}_SESSION_B64", "").strip()
        if not name or not b64_data:
            continue
        try:
            raw = base64.b64decode(b64_data)
            session_bytes = gzip.decompress(raw)
            sessions_dir.mkdir(parents=True, exist_ok=True)
            target = sessions_dir / f"{name}.session"
            target.write_bytes(session_bytes)
            log("launcher", f"  wrote {target.relative_to(ROOT)} from {prefix}_SESSION_B64 ({len(session_bytes)} bytes)")
        except Exception as e:
            log("launcher", f"  WARNING: failed to materialize {prefix} session: {e}")


def link_persistent_data() -> None:
    materialize_data_from_env()
    materialize_sessions_from_env()

    if not DATA_VOLUME.exists():
        return
    log("launcher", f"Persistent volume found at {DATA_VOLUME}")

    mappings = [
        (DATA_VOLUME / "farmclickers" / "data.txt", SERVICES / "farmclickers" / "data.txt"),
        (DATA_VOLUME / "notpixel" / "data.txt",     SERVICES / "notpixel" / "data.txt"),
        (DATA_VOLUME / "tomarketod" / "data.txt",   SERVICES / "tomarketod" / "data.txt"),
        (DATA_VOLUME / "tomarketod" / "proxies.txt", SERVICES / "tomarketod" / "proxies.txt"),
        (DATA_VOLUME / "tomarketod" / "tokens.json", SERVICES / "tomarketod" / "tokens.json"),
    ]
    for src, dst in mappings:
        if not src.exists():
            continue
        if dst.exists() or dst.is_symlink():
            if dst.is_symlink():
                dst.unlink()
            elif dst.is_dir():
                import shutil
                shutil.rmtree(dst)
            else:
                dst.unlink()
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.symlink_to(src)
        log("launcher", f"  linked {dst.relative_to(ROOT)} -> {src}")


# ---------------------------------------------------------------------------
# Subprocess supervisor
# ---------------------------------------------------------------------------

class Service:
    CRASH_TAIL_LINES = 15

    def __init__(self, tag: str, cwd: Path, cmd: list[str], extra_env: dict[str, str] | None = None):
        self.tag = tag
        self.cwd = cwd
        self.cmd = cmd
        self.extra_env = extra_env or {}
        self.proc: subprocess.Popen | None = None
        self.stop_requested = False
        self.run_started_at: float | None = None
        self.last_exit_at: float | None = None
        self.last_exit_rc: int | None = None
        self.restart_count = 0
        self.recent_lines: collections.deque[str] = collections.deque(maxlen=self.CRASH_TAIL_LINES)

    def _stream(self, stream) -> None:
        for raw in iter(stream.readline, b""):
            try:
                line = raw.decode("utf-8", errors="replace").rstrip()
            except Exception:
                line = repr(raw)
            self.recent_lines.append(line)
            log(self.tag, line)
        stream.close()

    def run_forever(self) -> None:
        backoff = 5
        while not self.stop_requested:
            env = os.environ.copy()
            env.update(self.extra_env)
            env.setdefault("PYTHONUNBUFFERED", "1")
            attempt_label = "starting" if self.restart_count == 0 else f"restart #{self.restart_count}"
            log(self.tag, f"{attempt_label}: {' '.join(self.cmd)} (cwd={self.cwd.relative_to(ROOT)})")
            try:
                self.proc = subprocess.Popen(
                    self.cmd,
                    cwd=str(self.cwd),
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                )
            except FileNotFoundError as e:
                log(self.tag, f"FATAL: {e}. Sleeping 60s before retry.")
                time.sleep(60)
                continue

            self.run_started_at = time.time()
            self.recent_lines.clear()
            log(self.tag, f"pid={self.proc.pid} started at {time.strftime('%H:%M:%S')}")

            assert self.proc.stdout is not None
            self._stream(self.proc.stdout)
            rc = self.proc.wait()

            self.last_exit_at = time.time()
            self.last_exit_rc = rc
            uptime = self.last_exit_at - (self.run_started_at or self.last_exit_at)

            if self.stop_requested:
                log(self.tag, f"exited (rc={rc}) after stop requested, ran for {fmt_uptime(uptime)}")
                return

            self.restart_count += 1
            log(self.tag, f"exited (rc={rc}) after {fmt_uptime(uptime)} - restart #{self.restart_count} in {backoff}s")
            if self.recent_lines:
                log(self.tag, f"--- last {len(self.recent_lines)} line(s) before exit ---")
                for line in list(self.recent_lines):
                    log(self.tag, f"    | {line}")
                log(self.tag, "--- end tail ---")

            time.sleep(backoff)
            backoff = min(backoff * 2, 300)
        self.run_started_at = None

    def terminate(self) -> None:
        self.stop_requested = True
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
            except ProcessLookupError:
                pass

    def status_line(self) -> str:
        now = time.time()
        if self.run_started_at and self.proc and self.proc.poll() is None:
            return f"{self.tag}: RUNNING pid={self.proc.pid} uptime={fmt_uptime(now - self.run_started_at)} restarts={self.restart_count}"
        if self.last_exit_at:
            return f"{self.tag}: DOWN last_rc={self.last_exit_rc} {fmt_uptime(now - self.last_exit_at)} ago, restarts={self.restart_count}"
        return f"{self.tag}: pending start (restarts={self.restart_count})"


def _data_nonempty(path: Path) -> bool:
    try:
        return path.exists() and any(l.strip() for l in path.read_text().splitlines())
    except OSError:
        return False


def build_services() -> list[Service]:
    services: list[Service] = []

    if os.environ.get("ENABLE_FARMCLICKERS", "1") == "1":
        data_path = SERVICES / "farmclickers" / "data.txt"
        if _data_nonempty(data_path):
            services.append(Service(
                tag="farmclickers",
                cwd=SERVICES / "farmclickers",
                cmd=["python3.11", "main.py", "-a", "2"],
            ))
        else:
            log("launcher", "farmclickers: SKIPPED - data.txt empty/missing. Set FARMCLICKERS_DATA env var with init_data tokens (one per line) and redeploy.")

    if os.environ.get("ENABLE_MAJORBOT", "1") == "1":
        sessions_dir = SERVICES / "majorbot" / "sessions"
        session_files = list(sessions_dir.glob("*.session")) if sessions_dir.exists() else []
        if session_files:
            services.append(Service(
                tag="majorbot",
                cwd=SERVICES / "majorbot",
                cmd=["python3.11", "main.py", "-a", "1"],
            ))
        else:
            log("launcher", "majorbot: SKIPPED - no .session files found. Set MAJORBOT_SESSION_NAME and MAJORBOT_SESSION_B64 env vars and redeploy.")

    if os.environ.get("ENABLE_NOTPIXEL", "1") == "1":
        data_path = SERVICES / "notpixel" / "data.txt"
        if _data_nonempty(data_path):
            services.append(Service(
                tag="notpixel",
                cwd=SERVICES / "notpixel",
                cmd=["python3.11", "main.py"],
                extra_env={"NOTPIXEL_AUTOSTART": "1"},
            ))
        else:
            log("launcher", "notpixel: SKIPPED - data.txt empty/missing. Set NOTPIXEL_DATA env var with init_data tokens (one per line) and redeploy.")

    if os.environ.get("ENABLE_TOMARKETOD", "1") == "1":
        data_path = SERVICES / "tomarketod" / "data.txt"
        if _data_nonempty(data_path):
            services.append(Service(
                tag="tomarketod",
                cwd=SERVICES / "tomarketod",
                cmd=["python3.11", "bot.py", "--marinkitagawa"],
            ))
        else:
            log("launcher", "tomarketod: SKIPPED - data.txt empty/missing. Set TOMARKET_DATA env var with init_data tokens (one per line) and redeploy.")

    return services


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def heartbeat_loop(services: list[Service], stop_event: threading.Event) -> None:
    if HEARTBEAT_INTERVAL_SEC <= 0:
        return
    while not stop_event.wait(HEARTBEAT_INTERVAL_SEC):
        launcher_uptime = fmt_uptime(time.time() - START_TIME)
        log("launcher", f"heartbeat: launcher_uptime={launcher_uptime}")
        for svc in services:
            log("launcher", f"  {svc.status_line()}")


def main() -> int:
    startup_diagnostic()
    log("launcher", "farmtgbot: unified multi-bot Railway worker starting")
    api_id, api_hash = require_env()
    materialize_farmclickers_env(api_id, api_hash)
    materialize_majorbot_env(api_id, api_hash)
    link_persistent_data()
    session_inventory()

    services = build_services()
    if not services:
        log("launcher", "FATAL: no services to run. Either all ENABLE_* flags are 0, or every enabled service has an empty data file/session. Set at least one of FARMCLICKERS_DATA / MAJORBOT_SESSION_B64 / NOTPIXEL_DATA / TOMARKET_DATA and redeploy.")
        return 1
    log("launcher", f"enabled services: {[s.tag for s in services]}")
    log("launcher", f"heartbeat interval: {HEARTBEAT_INTERVAL_SEC}s (set HEARTBEAT_INTERVAL_SEC=0 to disable)")

    threads: list[threading.Thread] = []
    for svc in services:
        t = threading.Thread(target=svc.run_forever, name=svc.tag, daemon=True)
        t.start()
        threads.append(t)

    shutting_down = threading.Event()

    hb_thread = threading.Thread(
        target=heartbeat_loop, args=(services, shutting_down),
        name="heartbeat", daemon=True,
    )
    hb_thread.start()

    def handle_signal(signum, _frame):
        log("launcher", f"received signal {signum}, terminating services")
        shutting_down.set()
        for svc in services:
            svc.terminate()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    try:
        while not shutting_down.is_set():
            time.sleep(1)
    except KeyboardInterrupt:
        handle_signal(signal.SIGINT, None)

    for t in threads:
        t.join(timeout=15)
    log("launcher", "all services stopped, exiting")
    return 0


if __name__ == "__main__":
    sys.exit(main())
