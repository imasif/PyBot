#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT_DIR/.env"
ENV_EXAMPLE="$ROOT_DIR/.env.example"
NON_INTERACTIVE=0
OVERWRITE=0

for arg in "$@"; do
  case "$arg" in
    --non-interactive)
      NON_INTERACTIVE=1
      ;;
    --overwrite)
      OVERWRITE=1
      ;;
    *)
      echo "Unknown option: $arg"
      echo "Usage: $0 [--non-interactive] [--overwrite]"
      exit 1
      ;;
  esac
done

if [[ ! -f "$ENV_EXAMPLE" ]]; then
  echo "❌ Missing .env.example at $ENV_EXAMPLE"
  exit 1
fi

if [[ -f "$ENV_FILE" ]]; then
  if [[ "$OVERWRITE" -eq 1 ]]; then
    :
  elif [[ "$NON_INTERACTIVE" -eq 1 ]]; then
    echo "❌ .env already exists. Use --overwrite in non-interactive mode."
    exit 1
  else
    read -r -p ".env already exists. Overwrite? [y/N]: " overwrite
    if [[ ! "$overwrite" =~ ^[Yy]$ ]]; then
      echo "Canceled."
      exit 0
    fi
  fi
fi

cp "$ENV_EXAMPLE" "$ENV_FILE"

set_key() {
  local key="$1"
  local value="$2"
  python3 - "$ENV_FILE" "$key" "$value" <<'PY'
import pathlib
import re
import sys

env_path = pathlib.Path(sys.argv[1])
key = sys.argv[2]
value = sys.argv[3]

text = env_path.read_text(encoding="utf-8")
pattern = re.compile(rf"^{re.escape(key)}=.*$", re.MULTILINE)
line = f"{key}={value}"

if pattern.search(text):
    text = pattern.sub(line, text)
else:
    if not text.endswith("\n"):
        text += "\n"
    text += line + "\n"

env_path.write_text(text, encoding="utf-8")
PY
}

ask_required() {
  local key="$1"
  local prompt="$2"
  local value=""
  while [[ -z "$value" ]]; do
    read -r -p "$prompt: " value
    if [[ -z "$value" ]]; then
      echo "This value is required."
    fi
  done
  set_key "$key" "$value"
}

ask_optional() {
  local key="$1"
  local prompt="$2"
  local current_default="${3:-}"
  local value=""
  if [[ -n "$current_default" ]]; then
    read -r -p "$prompt [$current_default]: " value
    value="${value:-$current_default}"
  else
    read -r -p "$prompt (optional): " value
  fi
  if [[ -n "$value" ]]; then
    set_key "$key" "$value"
  fi
}

require_env() {
  local key="$1"
  local value="${!key:-}"
  if [[ -z "$value" ]]; then
    echo "❌ Missing required environment variable: $key"
    exit 1
  fi
  set_key "$key" "$value"
}

if [[ "$NON_INTERACTIVE" -eq 1 ]]; then
  echo "Configuring .env in non-interactive mode..."
  require_env "TELEGRAM_BOT_TOKEN"
  require_env "CRON_NOTIFY_USER_ID"

  AI_BACKEND="${AI_BACKEND:-ollama}"
  if [[ "$AI_BACKEND" != "ollama" && "$AI_BACKEND" != "openai" ]]; then
    echo "❌ AI_BACKEND must be either 'ollama' or 'openai'"
    exit 1
  fi
  set_key "AI_BACKEND" "$AI_BACKEND"

  if [[ "$AI_BACKEND" == "ollama" ]]; then
    set_key "OLLAMA_URL" "${OLLAMA_URL:-http://127.0.0.1:11434/api/generate}"
    set_key "OLLAMA_MODEL" "${OLLAMA_MODEL:-llama3.2}"
  else
    require_env "OPENAI_API_KEY"
    set_key "OPENAI_MODEL" "${OPENAI_MODEL:-gpt-4o-mini}"
  fi

  optional_keys=(
    OPENWEATHER_API_KEY
    NEWSAPI_KEY
    GMAIL_EMAIL
    GMAIL_APP_PASSWORD
    TRELLO_API_KEY
    TRELLO_TOKEN
  )

  for key in "${optional_keys[@]}"; do
    value="${!key:-}"
    if [[ -n "$value" ]]; then
      set_key "$key" "$value"
    fi
  done

  echo "✅ .env created at $ENV_FILE (non-interactive)"
  exit 0
fi

echo "Configuring required settings..."
ask_required "TELEGRAM_BOT_TOKEN" "Enter TELEGRAM_BOT_TOKEN"
ask_required "CRON_NOTIFY_USER_ID" "Enter CRON_NOTIFY_USER_ID (your Telegram numeric user id)"

read -r -p "AI_BACKEND [ollama/openai] (default: ollama): " ai_backend
ai_backend="${ai_backend:-ollama}"
if [[ "$ai_backend" != "ollama" && "$ai_backend" != "openai" ]]; then
  echo "Invalid AI_BACKEND. Using ollama."
  ai_backend="ollama"
fi
set_key "AI_BACKEND" "$ai_backend"

if [[ "$ai_backend" == "ollama" ]]; then
  ask_optional "OLLAMA_URL" "Enter OLLAMA_URL" "http://127.0.0.1:11434/api/generate"
  ask_optional "OLLAMA_MODEL" "Enter OLLAMA_MODEL" "llama3.2"
else
  ask_required "OPENAI_API_KEY" "Enter OPENAI_API_KEY"
  ask_optional "OPENAI_MODEL" "Enter OPENAI_MODEL" "gpt-4o-mini"
fi

echo
echo "Optional integrations (press Enter to skip):"
ask_optional "OPENWEATHER_API_KEY" "OPENWEATHER_API_KEY"
ask_optional "NEWSAPI_KEY" "NEWSAPI_KEY"
ask_optional "GMAIL_EMAIL" "GMAIL_EMAIL"
ask_optional "GMAIL_APP_PASSWORD" "GMAIL_APP_PASSWORD"
ask_optional "TRELLO_API_KEY" "TRELLO_API_KEY"
ask_optional "TRELLO_TOKEN" "TRELLO_TOKEN"

echo
echo "✅ .env created at $ENV_FILE"
echo "You can edit it anytime: nano $ENV_FILE"
