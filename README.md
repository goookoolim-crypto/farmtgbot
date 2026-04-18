# farmtgbot

Unified Railway worker running **Telegram mini-app autoclickers** in a single
container:

| Service | Bots | Upstream | Session type |
|---|---|---|---|
| `farmclickers` | Yescoin, DotCoin, Cats | [faxw3b/main-telegram-autoclickers](https://github.com/faxw3b/main-telegram-autoclickers) | WebApp init_data token |
| `majorbot` | Major | [GravelFire/MajorBot](https://github.com/GravelFire/MajorBot) | Pyrogram session file |
| `notpixel` | NotPixel | [aDarkDev/NotPixel](https://github.com/aDarkDev/NotPixel) | WebApp init_data token |
| `tomarketod` | Tomarket | [akasakaid/tomarketod](https://github.com/akasakaid/tomarketod) | WebApp init_data token |

**Changes from previous version:**

- **Blum** has been removed (disabled in farmclickers config).
- **Major** has been moved from farmclickers (init_data based) to a standalone
  `majorbot` service powered by [GravelFire/MajorBot](https://github.com/GravelFire/MajorBot),
  which uses **Pyrogram sessions** instead of init_data tokens. This means it
  connects directly to Telegram and automatically extracts fresh tgWebAppData —
  no manual token rotation needed.
- **NotPixel** (notpx.app) is currently offline (returns 404). The service is
  still included but will fail to connect until the upstream API is restored.

Most services use **WebApp `init_data` tokens** pasted into `data.txt` files.
**MajorBot** is the exception — it uses a **Pyrogram `.session` file** provided
via `MAJORBOT_SESSION_B64` env var (gzipped + base64 encoded).

One Railway Hobby plan ($5/month credit) is enough as long as all services run
in the same container.

> **Warning:** Never use your main Telegram account. There is always some
> risk of a ban on automated clients.

---

## Quick deploy (the short version)

```text
1. my.telegram.org          -> grab API_ID + API_HASH
2. Extract init_data tokens  (see "Getting init_data" below)
3. (Optional) Create a Pyrogram session for MajorBot
4. Push to your own GitHub repo
5. Railway -> New project -> Deploy from GitHub -> pick this repo
6. Railway -> service -> Variables: set API_ID, API_HASH, FARMCLICKERS_DATA, NOTPIXEL_DATA, TOMARKET_DATA
7. (Optional) Set MAJORBOT_SESSION_NAME + MAJORBOT_SESSION_B64
8. Redeploy, watch logs
```

---

## Getting init_data tokens

Farmclickers, NotPixel, and Tomarket need `tgWebAppData` strings extracted from
Telegram Desktop. The process is the same for each bot — only the bot link
differs.

### Setup (one-time)

1. Open **Telegram Desktop**
2. Go to **Settings → Advanced → Experimental features**
3. Enable **"Enable WebView inspecting"** (or similar option)

### Extract token for each bot

| Bot | Link to open |
|---|---|
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
- `services/farmclickers/data.txt` — used by farmclickers bots
- `services/notpixel/data.txt` — used by NotPixel
- `services/tomarketod/data.txt` — used by Tomarket

**Railway deployment (env vars):**
- `FARMCLICKERS_DATA` — init_data for farmclickers
- `NOTPIXEL_DATA` — init_data for NotPixel
- `TOMARKET_DATA` — init_data for Tomarket

Multiple accounts: put one token per line (separate with `\n` in env vars).

---

## MajorBot session setup

MajorBot uses Pyrogram to connect directly to Telegram. You need to provide a
`.session` file instead of init_data tokens.

### Create a session locally

```bash
pip install Pyrogram==2.0.106 TgCrypto==1.2.5
python3 -c "
from pyrogram import Client
app = Client('newone', api_id=YOUR_API_ID, api_hash='YOUR_API_HASH')
app.start()
print('Session created: newone.session')
app.stop()
"
```

### Encode the session for Railway

```bash
gzip -c newone.session | base64 -w0
```

Set the output as `MAJORBOT_SESSION_B64` and `MAJORBOT_SESSION_NAME=newone` in
Railway Variables.

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

### Add tokens / sessions

Extract init_data for each bot (see above) and paste into the data.txt files:

```bash
# Farmclickers
echo 'query_id=AAG...your_token_here' > services/farmclickers/data.txt

# NotPixel
echo 'query_id=AAG...your_token_here' > services/notpixel/data.txt

# Tomarket
echo 'query_id=AAG...your_token_here' > services/tomarketod/data.txt
```

For MajorBot, copy your `.session` file:

```bash
cp newone.session services/majorbot/sessions/
```

### Run

```bash
export $(grep -v '^#' .env | xargs)
python3.11 run_all.py
```

You should see logs tagged `[launcher]`, `[farmclickers]`, `[majorbot]`,
`[notpixel]`, `[tomarketod]` interleaving. Stop with Ctrl-C.

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
| `FARMCLICKERS_DATA` | init_data token(s) for farmclickers |
| `NOTPIXEL_DATA` | init_data token(s) for NotPixel |
| `TOMARKET_DATA` | init_data token(s) for Tomarket |
| `MAJORBOT_SESSION_NAME` | session file name (e.g. `newone`) |
| `MAJORBOT_SESSION_B64` | gzipped+base64 session file |

Optional:

| Key | Purpose |
|---|---|
| `ENABLE_FARMCLICKERS` | `0` to disable farmclickers |
| `ENABLE_MAJORBOT` | `0` to disable MajorBot |
| `ENABLE_NOTPIXEL` | `0` to disable NotPixel |
| `ENABLE_TOMARKETOD` | `0` to disable Tomarket |
| `NOTPIXEL_PAINT_REWARD_MAX` / `NOTPIXEL_ENERGY_LIMIT_MAX` / `NOTPIXEL_RE_CHARGE_SPEED_MAX` | NotPixel upgrade caps |

### 4. (Optional) Persistent Volume at `/data`

A volume is optional but recommended so data.txt files survive redeploys
without re-setting env vars.

- Service → **Volumes** → **New Volume** → Mount path: `/data` (1 GB is plenty)

### 5. Redeploy and watch logs

Logs will show:

```
[launcher] Persistent volume found at /data
[launcher]   linked services/farmclickers/data.txt -> /data/farmclickers/data.txt
[launcher]   linked services/notpixel/data.txt     -> /data/notpixel/data.txt
[launcher]   linked services/tomarketod/data.txt   -> /data/tomarketod/data.txt
[launcher] enabled services: ['farmclickers', 'majorbot', 'notpixel', 'tomarketod']
```

Done. Leave it running.

---

## Cost estimate (Railway Hobby)

- Image size ~150 MB.
- RAM at steady state ~150-300 MB.
- These bots spend most of their wall-clock sleeping.
- Expected usage: **$2-4 / month**. Well within the $5 Hobby credit.

---

## Troubleshooting

**`FATAL: API_ID env var missing or not numeric`** — set it in Railway Variables.

**`majorbot: SKIPPED - no .session files found`** — set `MAJORBOT_SESSION_NAME`
and `MAJORBOT_SESSION_B64` env vars and redeploy.

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
