# farmtgbot

Unified Railway worker running **4 Telegram mini-app autoclickers** in a single
container:

| Service | Bots | Upstream | Session type |
|---|---|---|---|
| `farmclickers` | Blum, Major | [faxw3b/main-telegram-autoclickers](https://github.com/faxw3b/main-telegram-autoclickers) | WebApp init_data token |
| `notpixel` | NotPixel | [aDarkDev/NotPixel](https://github.com/aDarkDev/NotPixel) | WebApp init_data token |
| `tomarketod` | Tomarket | [akasakaid/tomarketod](https://github.com/akasakaid/tomarketod) | WebApp init_data token |

All 4 bots use the same authentication method: **WebApp `init_data` tokens**
pasted into `data.txt` files. No pyrogram/telethon session files, no phone
verification, no Telegram API client libraries needed.

One Railway Hobby plan ($5/month credit) is enough as long as all 3 run in the
same service.

> **Warning:** Never use your main Telegram account. There is always some
> risk of a ban on automated clients.

---

## Quick deploy (the short version)

```text
1. my.telegram.org          -> grab API_ID + API_HASH
2. Extract init_data tokens  (see "Getting init_data" below)
3. Push to your own GitHub repo
4. Railway -> New project -> Deploy from GitHub -> pick this repo
5. Railway -> service -> Variables: set API_ID, API_HASH, FARMCLICKERS_DATA, NOTPIXEL_DATA, TOMARKET_DATA
6. Redeploy, watch logs
```

---

## Getting init_data tokens

All 4 bots need `tgWebAppData` strings extracted from Telegram Desktop. The
process is the same for each bot — only the bot link differs.

### Setup (one-time)

1. Open **Telegram Desktop**
2. Go to **Settings → Advanced → Experimental features**
3. Enable **"Enable WebView inspecting"** (or similar option)

### Extract token for each bot

| Bot | Link to open |
|---|---|
| Blum | `https://t.me/BlumCryptoBot/app` |
| Major | `https://t.me/major/start` |
| NotPixel | `https://t.me/notpixel` |
| Tomarket | `https://t.me/Tomarket_ai_bot/app` |

For each bot:

1. Open the link above in Telegram Desktop
2. When the mini-app loads, **right-click** inside it → **Inspect**
3. Go to the **Console** tab and paste:
   ```js
   copy(Telegram.WebApp.initData);console.log('copied');
   ```
4. The `tgWebAppData` token is now in your clipboard
5. Paste it as **one line** into the appropriate `data.txt` file

Add one line per Telegram account. For Railway deployment, set the tokens as
env vars instead (see below).

### Where to put the tokens

**Local development:**
- `services/farmclickers/data.txt` — used by both Blum and Major
- `services/notpixel/data.txt` — used by NotPixel
- `services/tomarketod/data.txt` — used by Tomarket

**Railway deployment (env vars):**
- `FARMCLICKERS_DATA` — init_data for Blum + Major
- `NOTPIXEL_DATA` — init_data for NotPixel
- `TOMARKET_DATA` — init_data for Tomarket

Multiple accounts: put one token per line (separate with `\n` in env vars).

---

## Local development

### Setup

```bash
git clone https://github.com/<you>/farmtgbot.git
cd farmtgbot
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env: set API_ID and API_HASH
```

### Add tokens

Extract init_data for each bot (see above) and paste into the data.txt files:

```bash
# Blum + Major (shared data file)
echo 'query_id=AAG...your_token_here' > services/farmclickers/data.txt

# NotPixel
echo 'query_id=AAG...your_token_here' > services/notpixel/data.txt

# Tomarket
echo 'query_id=AAG...your_token_here' > services/tomarketod/data.txt
```

### Run

```bash
export $(grep -v '^#' .env | xargs)
python3.11 run_all.py
```

You should see logs tagged `[launcher]`, `[farmclickers]`, `[notpixel]`,
`[tomarketod]` interleaving. Stop with Ctrl-C.

---

## Deploy to Railway

### 1. Push this repo to your GitHub

```bash
git init
git add .
git commit -m "initial farmtgbot deploy"
gh repo create farmtgbot --private --source=. --remote=origin --push
```

### 2. Create the Railway service

- Railway dashboard → **New Project** → **Deploy from GitHub repo** → pick
  `farmtgbot`.
- Railway auto-detects the `Dockerfile` and builds the image.
- Leave **Public Networking** off — this is a worker, not a web service.

### 3. Set env vars

In **Variables**:

| Key | Value |
|---|---|
| `API_ID` | from my.telegram.org |
| `API_HASH` | from my.telegram.org |
| `FARMCLICKERS_DATA` | init_data token(s) for Blum + Major |
| `NOTPIXEL_DATA` | init_data token(s) for NotPixel |
| `TOMARKET_DATA` | init_data token(s) for Tomarket |

Optional:

| Key | Purpose |
|---|---|
| `ENABLE_FARMCLICKERS` | `0` to disable Blum+Major |
| `ENABLE_NOTPIXEL` | `0` to disable NotPixel |
| `ENABLE_TOMARKETOD` | `0` to disable Tomarket |
| `NOTPIXEL_PAINT_REWARD_MAX` / `NOTPIXEL_ENERGY_LIMIT_MAX` / `NOTPIXEL_RE_CHARGE_SPEED_MAX` | NotPixel upgrade caps |

### 4. (Optional) Persistent Volume at `/data`

A volume is optional but recommended so data.txt files survive redeploys
without re-setting env vars.

- Service → **Volumes** → **New Volume** → Mount path: `/data` (1 GB is plenty)
- Upload data files:
  ```bash
  railway run -- mkdir -p /data/farmclickers /data/notpixel /data/tomarketod
  railway volume cp services/farmclickers/data.txt /data/farmclickers/data.txt
  railway volume cp services/notpixel/data.txt     /data/notpixel/data.txt
  railway volume cp services/tomarketod/data.txt   /data/tomarketod/data.txt
  ```

### 5. Redeploy and watch logs

Logs will show:

```
[launcher] Persistent volume found at /data
[launcher]   linked services/farmclickers/data.txt -> /data/farmclickers/data.txt
[launcher]   linked services/notpixel/data.txt     -> /data/notpixel/data.txt
[launcher]   linked services/tomarketod/data.txt   -> /data/tomarketod/data.txt
[launcher] enabled services: ['farmclickers', 'notpixel', 'tomarketod']
```

Done. Leave it running.

---

## Cost estimate (Railway Hobby)

- Image size ~150 MB (no C toolchain or Telegram client libraries needed).
- RAM at steady state ~150-300 MB (pure HTTP clients only).
- These bots spend most of their wall-clock sleeping.
- Expected usage: **$2-4 / month**. Well within the $5 Hobby credit.

---

## Troubleshooting

**`FATAL: API_ID env var missing or not numeric`** — set it in Railway Variables.

**`NOTPIXEL_AUTOSTART=1 but no data in data.txt`** — your data.txt is empty.
Set the `NOTPIXEL_DATA` env var or upload data.txt to the volume.

**`0 accounts in data.txt`** — the data.txt file exists but is empty. Add
init_data tokens (one per line).

**Tomarket says `total account : 0`** — your `data.txt` is empty or not mounted.
Check `TOMARKET_DATA` env var or `/data/tomarketod/data.txt`.

**Auth failures / 401 errors** — your init_data token may have expired. Extract
a fresh token from Telegram Desktop and update the data.txt / env var.

**Container OOM-killed** — unlikely with this lightweight setup. If it happens,
disable one service or upgrade plan.
