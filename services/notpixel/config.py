import os

# Read from environment variables (falls back to 0/empty if unset)
API_ID = int(os.environ.get("API_ID", "0") or "0")
API_HASH = os.environ.get("API_HASH", "")

# =============[upgrades]================
# default is 5 level you can change it your self
PAINT_REWARD_MAX = int(os.environ.get("NOTPIXEL_PAINT_REWARD_MAX", "5"))  # max is 7
ENERGY_LIMIT_MAX = int(os.environ.get("NOTPIXEL_ENERGY_LIMIT_MAX", "5"))  # max is 6
RE_CHARGE_SPEED_MAX = int(os.environ.get("NOTPIXEL_RE_CHARGE_SPEED_MAX", "5"))  # max is 11

# ================[proxy]================
USE_PROXY = os.environ.get("NOTPIXEL_USE_PROXY", "False").lower() == "true"
PROXIES = {
    "http": os.environ.get("NOTPIXEL_PROXY_HTTP", "socks5://127.0.0.1"),
    "https": os.environ.get("NOTPIXEL_PROXY_HTTPS", "socks5://127.0.0.1"),
}
