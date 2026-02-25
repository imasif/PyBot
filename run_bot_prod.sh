#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$ROOT_DIR/.venv"
PYTHON_BIN="$VENV_DIR/bin/python"
LOG_DIR="$ROOT_DIR/logs"
TIMESTAMP="$(date +"%Y-%m-%d_%H-%M-%S")"
LOG_FILE="$LOG_DIR/bot-prod-$TIMESTAMP.log"
MAX_LOG_FILES="${MAX_LOG_FILES:-14}"

mkdir -p "$LOG_DIR"

log() {
  printf '%s [%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1" "$2"
}

# Mirror stdout/stderr to terminal + log file
exec > >(tee -a "$LOG_FILE") 2>&1

trap 'log INFO "Stopping production bot..."' INT TERM

cd "$ROOT_DIR"

if [[ ! -x "$PYTHON_BIN" ]]; then
  log ERROR "Python executable not found at $PYTHON_BIN"
  log ERROR "Create the environment first, e.g. python3 -m venv .venv"
  exit 1
fi

# Simple retention: keep newest N production log files
find "$LOG_DIR" -maxdepth 1 -type f -name 'bot-prod-*.log' -printf '%T@ %p\n' \
  | sort -nr \
  | awk -v keep="$MAX_LOG_FILES" 'NR > keep {sub(/^[^ ]+ /, ""); print}' \
  | while IFS= read -r old_file; do
      [[ -n "$old_file" ]] && rm -f "$old_file"
    done

log INFO "Project root: $ROOT_DIR"
log INFO "Using Python: $PYTHON_BIN"
log INFO "Log file: $LOG_FILE"
log INFO "Retention: keeping latest $MAX_LOG_FILES prod logs"
log INFO "Starting bot in production mode (no auto-restart)..."

exec "$PYTHON_BIN" "$ROOT_DIR/bot.py"
