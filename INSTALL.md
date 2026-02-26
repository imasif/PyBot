# Installation and Binary Build (Linux)

This guide gives you:
- Step-by-step installation
- `.env` settings
- A build process for an executable binary

## OpenClaw-style (recommended)

Run one guided command:

```bash
./scripts/install_openclaw_style.sh
```

It will:
- create/use `.venv`
- install dependencies
- prompt required `.env` values
- optionally build binary
- optionally install/start user `systemd` service

Quick verify after install:

```bash
systemctl --user status pybot --no-pager
journalctl --user -u pybot -n 80 --no-pager
```

## OpenClaw-style (non-interactive / CI)

Use this when you want zero prompts.

Required env vars:

```bash
export TELEGRAM_BOT_TOKEN="<your_bot_token>"
export CRON_NOTIFY_USER_ID="<your_telegram_user_id>"
export AI_BACKEND="ollama"   # or openai
```

If `AI_BACKEND=ollama` (optional with defaults):

```bash
export OLLAMA_URL="http://127.0.0.1:11434/api/generate"
export OLLAMA_MODEL="llama3.2"
```

If `AI_BACKEND=openai` (required):

```bash
export OPENAI_API_KEY="<your_openai_api_key>"
export OPENAI_MODEL="gpt-4o-mini"
```

Run full non-interactive install:

```bash
./scripts/install_openclaw_style.sh --non-interactive --overwrite-env --build-binary --with-systemd
```

Optional integrations can also be provided as env vars before running:
`OPENWEATHER_API_KEY`, `NEWSAPI_KEY`, `GMAIL_EMAIL`, `GMAIL_APP_PASSWORD`, `TRELLO_API_KEY`, `TRELLO_TOKEN`.

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

## 4) Create `.env`

```bash
./scripts/setup_env.sh
```

The script will ask required settings:

```env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
CRON_NOTIFY_USER_ID=your_telegram_user_id

AI_BACKEND=ollama
OLLAMA_URL=http://127.0.0.1:11434/api/generate
OLLAMA_MODEL=llama3.2
```

If you choose `AI_BACKEND=openai`, it will ask for `OPENAI_API_KEY` instead.

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

Keep `.env` in the working directory where you run the binary.

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
