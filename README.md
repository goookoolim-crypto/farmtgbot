# farmtgbot

Unified Railway worker running **4 Telegram mini-app autoclickers** in a single
container:

| Service | Bots | Upstream | Session type |
|---|---|---|---|
| `farmclickers` | Blum, Major | [faxw3b/main-telegram-autoclickers](https://github.com/faxw3b/main-telegram-autoclickers) | pyrogram `.session` |
| `notpixel` | NotPixel | [aDarkDev/NotPixel](https://github.com/aDarkDev/NotPixel) | telethon `.session` |
| `tomarketod` | Tomarket | [akasakaid/tomarketod](https://github.com/akasakaid/tomarketod) | WebApp init_data token (no login) |

One Railway Hobby plan ($5/month credit) is enough as long as all 3 run in the
same service — splitting them into separate services triples the idle-memory
cost.

> **Warning:** Never use your main Telegram account. There is always some
> risk of a ban on automated clients.

---

## Quick deploy (the short version)

```text
1. my.telegram.org          -> grab API_ID + API_HASH
2. clone this repo locally, python 3.11 venv, pip install -r requirements.txt
3. create sessions locally   (see "Local session bootstrap" below)
4. push to your own GitHub repo
5. Railway -> New project -> Deploy from GitHub -> pick this repo
6. Railway -> service -> Variables: set API_ID, API_HASH
7. Railway -> service -> Volume: mount at /data, upload sessions + data.txt
8. redeploy, watch logs
```

---

## Local session bootstrap (MUST run once on your machine)

Telegram requires phone verification (SMS / in-app code) to create a session.
You cannot do that on a Railway container — no way to enter the code. So run
each service once locally, then upload the resulting session files to Railway.

### 0. Setup

```bash
git clone https://github.com/<you>/farmtgbot.git
cd farmtgbot
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env: set API_ID and API_HASH
```

### 1. farmclickers (Blum + Major) — pyrogram sessions

```bash
cd services/farmclickers
cp .env-example .env
# edit .env: paste API_ID and API_HASH (same ones)
python3.11 main.py
# menu -> 1 (Create new session)
# enter session name (e.g. "main"), phone number, SMS code, 2FA password if set
```

Output lands in `services/farmclickers/sessions/<name>.session`.

Repeat option `1` for every extra Telegram account. When done, Ctrl-C.

### 2. notpixel — telethon sessions

notpixel uses a different library, so you must log in **again** (same phone,
same API_ID/HASH — just a different `.session` file format).

```bash
cd ../notpixel
# no .env file needed here - it reads env vars. With the venv active just:
export API_ID=12345 API_HASH=abcdef...   # or run under the root .env
python3.11 main.py
# prompt -> 1 (Add account)
# enter session name + phone
```

Output lands in `services/notpixel/sessions/<name>.session`.

### 3. tomarketod — no login, WebApp init_data token

Tomarketod does not use Telegram API sessions. Instead it wants the
`tgWebAppData` string that Telegram Desktop's Mini App WebView sends when you
open the Tomarket bot.

How to get it (see the upstream repo's "How to Get Data" section for a video):

1. Open Telegram Desktop, enable Dev Tools (Settings → Advanced → Experimental
   features → Enable WebView inspecting).
2. Open <https://t.me/Tomarket_ai_bot/app>.
3. Right-click inside the mini-app → Inspect → Console, paste:
   ```js
   copy(decodeURIComponent(sessionStorage.SourceTarget).split('#tgWebAppData=')[1].split('&tgWebAppVersion=')[0]);console.log('data copied');
   ```
4. The token is now in your clipboard. Paste it as one line in
   `services/tomarketod/data.txt`. Add one line per account.

### 4. Test locally (optional)

```bash
cd ../..                          # back to repo root
export $(grep -v '^#' .env | xargs)   # load vars
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

Keep it **private** — even though sessions aren't committed, the code still
references referral links you might want to customize.

### 2. Create the Railway service

- Railway dashboard → **New Project** → **Deploy from GitHub repo** → pick
  `farmtgbot`.
- Railway auto-detects the `Dockerfile` and builds the image.
- Railway will try to create a public domain — **do not enable networking**.
  This is a worker, not a web service. Leave "Public Networking" off.

### 3. Set env vars

In **Variables**:

| Key | Value |
|---|---|
| `API_ID` | from my.telegram.org |
| `API_HASH` | from my.telegram.org |

Optional:

| Key | Purpose |
|---|---|
| `ENABLE_FARMCLICKERS` | `0` to disable Blum+Major |
| `ENABLE_NOTPIXEL` | `0` to disable NotPixel |
| `ENABLE_TOMARKETOD` | `0` to disable Tomarket |
| `NOTPIXEL_PAINT_REWARD_MAX` / `NOTPIXEL_ENERGY_LIMIT_MAX` / `NOTPIXEL_RE_CHARGE_SPEED_MAX` | NotPixel upgrade caps |

### 4. Attach a persistent Volume at `/data`

Without this, sessions vanish every redeploy.

- Service → **Volumes** → **New Volume** → Mount path: `/data` (1 GB is plenty).
- Use the Railway CLI to upload your session files into the volume:
  ```bash
  # install once
  npm i -g @railway/cli
  railway login
  railway link        # pick the farmtgbot project

  # copy files into the running container's /data
  railway run --service farmtgbot -- mkdir -p /data/farmclickers/sessions /data/notpixel/sessions /data/tomarketod
  railway volume cp services/farmclickers/sessions/. /data/farmclickers/sessions/
  railway volume cp services/notpixel/sessions/.     /data/notpixel/sessions/
  railway volume cp services/tomarketod/data.txt     /data/tomarketod/data.txt
  ```
  (If your Railway CLI version doesn't have `volume cp`, alternatives: a
  temporary SFTP sidecar, or commit encrypted sessions — see "Alternative:
  sessions via env var" below.)

### 5. Redeploy and watch logs

After uploading sessions you need one more redeploy so the launcher picks them
up via the volume symlinks. Logs will show:

```
[launcher] Persistent volume found at /data
[launcher]   linked services/farmclickers/sessions -> /data/farmclickers/sessions
[launcher]   linked services/notpixel/sessions     -> /data/notpixel/sessions
[launcher]   linked services/tomarketod/data.txt   -> /data/tomarketod/data.txt
[launcher] enabled services: ['farmclickers', 'notpixel', 'tomarketod']
[farmclickers] starting: python3.11 main.py -a 2 (cwd=services/farmclickers)
[notpixel] starting: python3.11 main.py (cwd=services/notpixel)
[notpixel] [+] NOTPIXEL_AUTOSTART=1 - starting mine+claim with 1 session(s)
[tomarketod] starting: python3.11 bot.py --marinkitagawa (cwd=services/tomarketod)
```

Done. Leave it running.

---

## Alternative: sessions via env var (no volume)

If Railway volumes are awkward, you can embed each `.session` file as a base64
env var and write it at container boot. Not included by default because it
bloats the env and your .session ends up in Railway's audit log.

Ask if you want this.

---

## Cost estimate (Railway Hobby)

- Image size ~250 MB. RAM at steady state ~350-550 MB (mostly telethon +
  pyrogram clients).
- These bots spend most of their wall-clock sleeping (Blum+Major wake every
  ~6h per "soft circle", NotPixel claim loop is 1h, Tomarketod idles between
  account passes).
- Expected usage: **$3-5 / month**. Tight but within the $5 Hobby credit.
- If it goes over, either:
  - disable one service (e.g. `ENABLE_FARMCLICKERS=0`), or
  - upgrade to Pro ($20/mo, 8 GB included).

---

## Updating upstream code

Each service was vendored (not a submodule) because Railway builds from a flat
tree and the upstream repos are unmaintained in lockstep. To pull upstream
updates:

```bash
# farmclickers
( cd /tmp && git clone https://github.com/faxw3b/main-telegram-autoclickers && \
  rsync -av --delete --exclude .git main-telegram-autoclickers/ services/farmclickers/ )

# notpixel
# (remember to re-apply the config.py + main.py patches that enable env vars and autostart)
```

Then `git diff`, review, commit, push. Railway redeploys automatically.

---

## Troubleshooting

**`FATAL: API_ID env var missing or not numeric`** — set it in Railway Variables.

**`NOTPIXEL_AUTOSTART=1 but no sessions found`** — your `/data/notpixel/sessions`
volume directory is empty. Upload the telethon `.session` files via Railway CLI.

**`pyrogram.errors.AuthKeyUnregistered`** — the pyrogram `.session` was
invalidated (Telegram killed it, usually because you logged in from another
client). Regenerate locally and re-upload.

**Tomarket says `total account : 0`** — your `data.txt` is empty or not mounted.
Check `/data/tomarketod/data.txt` exists with one init_data line per account.

**Container OOM-killed** — you're probably over the Hobby memory limit.
Disable one service or upgrade.
