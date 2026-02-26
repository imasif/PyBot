# Installation and Binary Build (Linux)

This guide gives you:
- Bash onboarding (`scripts/onboarding.sh`)
- Built-in config management (`gateway`)
- A build process for executable binaries

## Run (recommended: bash onboarding)

Run onboarding script first:

```bash
./scripts/onboarding.sh
```

Then run the binary:

```bash
./dist/pybot/pybot
```

The binary `onboard` command delegates to this bash script.

You can also run onboarding explicitly:

```bash
./dist/pybot/pybot onboard
```

And later edit settings from CLI:

```bash
./dist/pybot/pybot gateway list
./dist/pybot/pybot gateway get OPENWEATHER_API_KEY
./dist/pybot/pybot gateway set OPENWEATHER_API_KEY <your_key>
```

Quick verify after install:

```bash
systemctl --user status pybot --no-pager
journalctl --user -u pybot -n 80 --no-pager
```

## Run (non-interactive / CI)

For CI, you can pre-create `.env` and run binary with `gateway` commands.
Legacy script-based installers still exist under `scripts/`, but are optional.

## 1) Clone and enter project

```bash
git clone <your-repo-url> aiBot
cd aiBot
```

## 2) Create and activate virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

## 3) Install dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

## 4) Create `.env` (if running from source)

You can still create it manually from source mode:

```env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
CRON_NOTIFY_USER_ID=your_telegram_user_id

AI_BACKEND=ollama
OLLAMA_URL=http://127.0.0.1:11434/api/generate
OLLAMA_MODEL=llama3.2
```

If you choose `AI_BACKEND=openai`, include `OPENAI_API_KEY`.

Manual alternative:

```bash
cp .env.example .env
```

Optional but recommended:

```env
OPENWEATHER_API_KEY=your_openweather_key
NEWSAPI_KEY=your_newsapi_key
GMAIL_EMAIL=your_email@gmail.com
GMAIL_APP_PASSWORD=your_gmail_app_password
TRELLO_API_KEY=your_trello_key
TRELLO_TOKEN=your_trello_token
```

## 5) Run in development

```bash
python bot.py
```

Or use existing scripts:

```bash
./run_bot.sh
# or
./run_bot_prod.sh
```

## 6) Build executable binary

Use the build script:

```bash
./scripts/build_binary.sh
```

Output:
- Binary folder: `dist/pybot/`
- Executable file: `dist/pybot/pybot`

## 7) Run executable binary

From project root (recommended):

```bash
./dist/pybot/pybot
```

On first run, this will prompt onboarding automatically if required values are missing.

You can manage config later with:

```bash
./dist/pybot/pybot gateway list
./dist/pybot/pybot gateway set KEY VALUE
```

## 8) Notes for production

- If you change Python code, rebuild binary.
- If you only change `.env`, no rebuild is needed.
- Database file (`*.db`) is created in the current working directory.

## 9) Run with systemd (user service)

Install and start the user service:

```bash
./scripts/install_systemd_user.sh
```

Useful commands:

```bash
systemctl --user status pybot
journalctl --user -u pybot -f
journalctl --user -u pybot -n 200 --no-pager
journalctl --user -u pybot --since "1 hour ago"
systemctl --user restart pybot
systemctl --user stop pybot
```

`systemd` captures your bot logs from stdout/stderr automatically via `journald`.

Optional custom values:

```bash
SERVICE_NAME=pybot-qemu PROJECT_DIR=$HOME/projects/aiBot BINARY_PATH=$HOME/projects/aiBot/dist/pybot/pybot ./scripts/install_systemd_user.sh
```

If you want the user service to continue running after logout, enable lingering once:

```bash
sudo loginctl enable-linger $USER
```
