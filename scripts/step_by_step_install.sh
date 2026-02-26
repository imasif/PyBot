#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$ROOT_DIR/.venv"
PYTHON_BIN=""
NON_INTERACTIVE=0
OVERWRITE_ENV=0
BUILD_BINARY="ask"
INSTALL_SYSTEMD="ask"

for arg in "$@"; do
  case "$arg" in
    --non-interactive)
      NON_INTERACTIVE=1
      ;;
    --overwrite-env)
      OVERWRITE_ENV=1
      ;;
    --build-binary)
      BUILD_BINARY="yes"
      ;;
    --skip-binary)
      BUILD_BINARY="no"
      ;;
    --with-systemd)
      INSTALL_SYSTEMD="yes"
      ;;
    --skip-systemd)
      INSTALL_SYSTEMD="no"
      ;;
    *)
      echo "Unknown option: $arg"
      echo "Usage: $0 [--non-interactive] [--overwrite-env] [--build-binary|--skip-binary] [--with-systemd|--skip-systemd]"
      exit 1
      ;;
  esac
done

echo "🚀 PyBot Guided Installer"
echo "Project: $ROOT_DIR"
echo

cd "$ROOT_DIR"

if [[ -x "$VENV_DIR/bin/python" ]]; then
  PYTHON_BIN="$VENV_DIR/bin/python"
else
  if ! command -v python3 >/dev/null 2>&1; then
    echo "❌ python3 not found. Install Python 3.10+ first."
    exit 1
  fi
  echo "[1/6] Creating virtual environment (.venv)..."
  python3 -m venv "$VENV_DIR"
  PYTHON_BIN="$VENV_DIR/bin/python"
fi

echo "[2/6] Installing dependencies..."
"$PYTHON_BIN" -m pip install --upgrade pip
"$PYTHON_BIN" -m pip install -r requirements.txt

echo "[3/6] Configuring environment (.env)..."
SETUP_ARGS=()
if [[ "$NON_INTERACTIVE" -eq 1 ]]; then
  SETUP_ARGS+=(--non-interactive)
fi
if [[ "$OVERWRITE_ENV" -eq 1 ]]; then
  SETUP_ARGS+=(--overwrite)
fi
"$ROOT_DIR/scripts/setup_env.sh" "${SETUP_ARGS[@]}"

if [[ "$BUILD_BINARY" == "ask" ]]; then
  if [[ "$NON_INTERACTIVE" -eq 1 ]]; then
    BUILD_BINARY="yes"
  else
    read -r -p "Build executable binary now? [Y/n]: " build_choice
    build_choice="${build_choice:-Y}"
    if [[ "$build_choice" =~ ^[Yy]$ ]]; then
      BUILD_BINARY="yes"
    else
      BUILD_BINARY="no"
    fi
  fi
fi

if [[ "$BUILD_BINARY" == "yes" ]]; then
  echo "[4/6] Building binary..."
  "$ROOT_DIR/scripts/build_binary.sh"
else
  echo "[4/6] Skipped binary build."
fi

if [[ -x "$ROOT_DIR/dist/pybot/pybot" ]]; then
  if [[ "$INSTALL_SYSTEMD" == "ask" ]]; then
    if [[ "$NON_INTERACTIVE" -eq 1 ]]; then
      INSTALL_SYSTEMD="yes"
    else
      read -r -p "Install/start systemd user service now? [Y/n]: " svc_choice
      svc_choice="${svc_choice:-Y}"
      if [[ "$svc_choice" =~ ^[Yy]$ ]]; then
        INSTALL_SYSTEMD="yes"
      else
        INSTALL_SYSTEMD="no"
      fi
    fi
  fi

  if [[ "$INSTALL_SYSTEMD" == "yes" ]]; then
    echo "[5/6] Installing user service..."
    "$ROOT_DIR/scripts/install_systemd_user.sh"
    echo "[6/6] Service status:"
    systemctl --user status pybot --no-pager || true
  else
    echo "[5/6] Skipped service install."
    echo "[6/6] Done. Run binary with: ./dist/pybot/pybot"
  fi
else
  echo "[5/6] Binary not found; skipping service install."
  echo "[6/6] Done. You can build later: ./scripts/build_binary.sh"
fi

echo
echo "✅ Installation flow complete."
#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$ROOT_DIR/.venv"
PYTHON_BIN="$VENV_DIR/bin/python"
PIP_BIN="$VENV_DIR/bin/pip"

log() {
  printf '\n[%s] %s\n' "$1" "$2"
}

require_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "❌ Missing required command: $cmd"
    exit 1
  fi
}

cd "$ROOT_DIR"

log "STEP 1/7" "Checking prerequisites"
require_cmd "python3"
require_cmd "bash"
require_cmd "systemctl"

log "STEP 2/7" "Creating/updating virtual environment"
if [[ ! -x "$PYTHON_BIN" ]]; then
  python3 -m venv "$VENV_DIR"
fi

log "STEP 3/7" "Installing dependencies"
"$PIP_BIN" install --upgrade pip
"$PIP_BIN" install -r requirements.txt

log "STEP 4/7" "Configuring environment (.env)"
if [[ ! -f "$ROOT_DIR/.env" ]]; then
  "$ROOT_DIR/scripts/setup_env.sh"
else
  read -r -p ".env already exists. Reconfigure now? [y/N]: " reconfigure
  if [[ "$reconfigure" =~ ^[Yy]$ ]]; then
    "$ROOT_DIR/scripts/setup_env.sh"
  fi
fi

if [[ ! -f "$ROOT_DIR/.env" ]]; then
  echo "❌ .env is missing after configuration step."
  exit 1
fi

log "STEP 5/7" "Building binary"
"$ROOT_DIR/scripts/build_binary.sh"

if [[ ! -x "$ROOT_DIR/dist/pybot/pybot" ]]; then
  echo "❌ Build finished but binary not found at dist/pybot/pybot"
  exit 1
fi

log "STEP 6/7" "Installing user systemd service"
"$ROOT_DIR/scripts/install_systemd_user.sh"

log "STEP 7/7" "Verifying service status"
systemctl --user status pybot --no-pager || true

cat <<'EOF'

✅ Installation completed.

Useful commands:
  systemctl --user status pybot
  journalctl --user -u pybot -f
  systemctl --user restart pybot

EOF
