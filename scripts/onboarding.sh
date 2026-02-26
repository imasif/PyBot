#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SETUP_SCRIPT="$ROOT_DIR/scripts/setup_env.sh"

if [[ ! -f "$SETUP_SCRIPT" ]]; then
  echo "❌ Missing setup script: $SETUP_SCRIPT"
  exit 1
fi

if [[ ! -x "$SETUP_SCRIPT" ]]; then
  chmod +x "$SETUP_SCRIPT"
fi

echo "🚀 PyBot Onboarding (bash)"
echo "Project: $ROOT_DIR"
echo

"$SETUP_SCRIPT" "$@"

echo
echo "✅ Onboarding finished."
echo "Next: run ./dist/pybot/pybot (or python bot.py)"
