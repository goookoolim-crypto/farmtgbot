"""Unified launcher for all 3 telegram farming services.

Runs as a single Railway worker. Spawns:
  - farmclickers   (Blum + Major via faxw3b/main-telegram-autoclickers, pyrogram sessions)
  - notpixel       (aDarkDev/NotPixel, telethon sessions)
  - tomarketod     (akasakaid/tomarketod, WebApp init_data tokens in data.txt)

Responsibilities:
  1. Validate required env vars (API_ID, API_HASH).
  2. Materialize farmclickers/.env from env vars (the upstream project reads a .env file, not the OS environment).
  3. Link session/data files from a persistent /data volume (Railway) into each service dir, if /data exists.
  4. Spawn each enabled service as a subprocess with prefixed, line-buffered logs.
  5. Auto-restart any crashed subprocess after a backoff.
  6. Forward SIGTERM/SIGINT to children for clean Railway shutdowns.

Enable/disable a service with env flags:
  ENABLE_FARMCLICKERS=1   (default 1)
  ENABLE_NOTPIXEL=1       (default 1)
  ENABLE_TOMARKETOD=1     (default 1)
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SERVICES = ROOT / "services"
DATA_VOLUME = Path(os.environ.get("DATA_VOLUME", "/data"))

COLORS = {
    "farmclickers": "\033[36m",  # cyan
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
        "is_connected": true,
        "ref_code": "ref_qIFL0xYd8i",
        "errors_before_stop": 2,
        "spend_diamonds": true,
        "max_games_count": [10, 20],
        "points": [120, 190],
        "sleep_game_time": [60, 180],
        "do_tasks": true
    }},
    "major" : {{
        "is_connected": true,
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


# ---------------------------------------------------------------------------
# Link persistent data from the Railway volume into each service dir.
# Expected volume layout (user uploads manually after first deploy):
#   /data/farmclickers/sessions/*.session   -> pyrogram sessions (blum/major)
#   /data/notpixel/sessions/*.session       -> telethon sessions (notpixel)
#   /data/tomarketod/data.txt               -> one WebApp init_data per line
#   /data/tomarketod/proxies.txt            -> optional
# ---------------------------------------------------------------------------

def link_persistent_data() -> None:
    if not DATA_VOLUME.exists():
        log("launcher", f"No persistent volume at {DATA_VOLUME} - using in-container files. Sessions will be lost on redeploy!")
        return
    log("launcher", f"Persistent volume found at {DATA_VOLUME}")

    mappings = [
        (DATA_VOLUME / "farmclickers" / "sessions", SERVICES / "farmclickers" / "sessions"),
        (DATA_VOLUME / "notpixel" / "sessions", SERVICES / "notpixel" / "sessions"),
        (DATA_VOLUME / "tomarketod" / "data.txt", SERVICES / "tomarketod" / "data.txt"),
        (DATA_VOLUME / "tomarketod" / "proxies.txt", SERVICES / "tomarketod" / "proxies.txt"),
        (DATA_VOLUME / "tomarketod" / "tokens.json", SERVICES / "tomarketod" / "tokens.json"),
    ]
    for src, dst in mappings:
        if not src.exists():
            log("launcher", f"  skip: {src} not present")
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
    def __init__(self, tag: str, cwd: Path, cmd: list[str], extra_env: dict[str, str] | None = None):
        self.tag = tag
        self.cwd = cwd
        self.cmd = cmd
        self.extra_env = extra_env or {}
        self.proc: subprocess.Popen | None = None
        self.stop_requested = False

    def _stream(self, stream) -> None:
        for raw in iter(stream.readline, b""):
            try:
                line = raw.decode("utf-8", errors="replace").rstrip()
            except Exception:
                line = repr(raw)
            log(self.tag, line)
        stream.close()

    def run_forever(self) -> None:
        backoff = 5
        while not self.stop_requested:
            env = os.environ.copy()
            env.update(self.extra_env)
            # Disable python output buffering so logs stream line-by-line.
            env.setdefault("PYTHONUNBUFFERED", "1")
            log(self.tag, f"starting: {' '.join(self.cmd)} (cwd={self.cwd.relative_to(ROOT)})")
            try:
                self.proc = subprocess.Popen(
                    self.cmd,
                    cwd=str(self.cwd),
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    bufsize=1,
                )
            except FileNotFoundError as e:
                log(self.tag, f"FATAL: {e}. Sleeping 60s before retry.")
                time.sleep(60)
                continue

            assert self.proc.stdout is not None
            self._stream(self.proc.stdout)
            rc = self.proc.wait()
            if self.stop_requested:
                log(self.tag, f"exited (rc={rc}) after stop requested")
                return
            log(self.tag, f"exited (rc={rc}) - restarting in {backoff}s")
            time.sleep(backoff)
            backoff = min(backoff * 2, 300)

    def terminate(self) -> None:
        self.stop_requested = True
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
            except ProcessLookupError:
                pass


def build_services() -> list[Service]:
    services: list[Service] = []

    if os.environ.get("ENABLE_FARMCLICKERS", "1") == "1":
        services.append(Service(
            tag="farmclickers",
            cwd=SERVICES / "farmclickers",
            # action 2 = launch software (non-interactive via -a flag)
            cmd=["python3.11", "main.py", "-a", "2"],
        ))

    if os.environ.get("ENABLE_NOTPIXEL", "1") == "1":
        services.append(Service(
            tag="notpixel",
            cwd=SERVICES / "notpixel",
            cmd=["python3.11", "main.py"],
            extra_env={"NOTPIXEL_AUTOSTART": "1"},
        ))

    if os.environ.get("ENABLE_TOMARKETOD", "1") == "1":
        services.append(Service(
            tag="tomarketod",
            cwd=SERVICES / "tomarketod",
            # --marinkitagawa suppresses the clear-screen on start (safe for non-tty)
            cmd=["python3.11", "bot.py", "--marinkitagawa"],
        ))

    return services


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    log("launcher", "farmtgbot: unified multi-bot Railway worker starting")
    api_id, api_hash = require_env()
    materialize_farmclickers_env(api_id, api_hash)
    link_persistent_data()

    services = build_services()
    if not services:
        log("launcher", "FATAL: all services disabled. Set at least one ENABLE_* env var to 1.")
        return 1
    log("launcher", f"enabled services: {[s.tag for s in services]}")

    threads: list[threading.Thread] = []
    for svc in services:
        t = threading.Thread(target=svc.run_forever, name=svc.tag, daemon=True)
        t.start()
        threads.append(t)

    shutting_down = threading.Event()

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
