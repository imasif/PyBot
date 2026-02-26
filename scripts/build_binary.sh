#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
  PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
else
  PYTHON_BIN="$(command -v python3 || true)"
fi

if [[ -z "${PYTHON_BIN:-}" ]]; then
  echo "❌ Python3 not found. Install Python 3.10+ and retry."
  exit 1
fi

echo "Using Python: $PYTHON_BIN"

"$PYTHON_BIN" -m pip install --upgrade pip pyinstaller

mapfile -t SKILL_MODULES < <("$PYTHON_BIN" - <<'PY'
import json
from pathlib import Path

skills_root = Path("skills")
modules = []

if skills_root.exists():
    for metadata_path in sorted(skills_root.glob("*/metadata.json")):
        try:
            raw = json.loads(metadata_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        module = raw.get("module")
        if module:
            modules.append(str(module))

for module in sorted(set(modules)):
    print(module)
PY
)

BUILD_CMD=(
  "$PYTHON_BIN" -m PyInstaller
  --noconfirm
  --clean
  --name "${BINARY_NAME:-pybot}"
  --onedir
  --add-data "skills:skills"
  --add-data "services:services"
  --add-data ".env.example:.env.example"
  bot.py
)

for module in "${SKILL_MODULES[@]}"; do
  BUILD_CMD+=(--hidden-import "$module")
done

echo "Building executable..."
"${BUILD_CMD[@]}"

echo "✅ Build complete"
echo "Run with: ./dist/${BINARY_NAME:-pybot}/${BINARY_NAME:-pybot}"
