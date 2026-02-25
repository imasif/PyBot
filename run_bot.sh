#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$ROOT_DIR/.venv"
PYTHON_BIN="$VENV_DIR/bin/python"
WATCHMEDO_BIN="$VENV_DIR/bin/watchmedo"
LOG_DIR="$ROOT_DIR/logs"
LOG_FILE="$LOG_DIR/bot-watch-$(date +"%Y-%m-%d").log"

mkdir -p "$LOG_DIR"

log() {
  printf '%s [%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1" "$2"
}

# Mirror all stdout/stderr to terminal + log file
exec > >(tee -a "$LOG_FILE") 2>&1

trap 'log INFO "Stopping bot watcher..."' INT TERM

cd "$ROOT_DIR"

if [[ ! -x "$PYTHON_BIN" ]]; then
  log ERROR "Python executable not found at $PYTHON_BIN"
  log ERROR "Create the environment first, e.g. python3 -m venv .venv"
  exit 1
fi

if [[ ! -x "$WATCHMEDO_BIN" ]]; then
  log ERROR "watchmedo not found in .venv. Install watchdog in your venv:"
  log ERROR "  $PYTHON_BIN -m pip install watchdog"
  exit 1
fi

log INFO "Project root: $ROOT_DIR"
log INFO "Using Python: $PYTHON_BIN"
log INFO "Log file: $LOG_FILE"
log INFO "Starting auto-restart bot watcher..."

# Better than relying on system python3/watchmedo:
# run both from your project venv for consistent dependencies.
exec "$WATCHMEDO_BIN" auto-restart \
  --directory="$ROOT_DIR" \
  --pattern="*.py" \
  --recursive \
  --signal=SIGTERM \
  -- "$PYTHON_BIN" "$ROOT_DIR/bot.py"
