#!/usr/bin/env bash
# IBKR Read-Only Setup Script (v2: IB Gateway + ib_insync)
# Supports: Debian and macOS

set -euo pipefail

TRADING_DIR="${1:-$HOME/trading}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

log() {
  printf "[setup] %s\n" "$1"
}

die() {
  printf "[setup] ERROR: %s\n" "$1" >&2
  exit 1
}

detect_platform() {
  case "$(uname -s)" in
    Darwin)
      echo "macos"
      ;;
    Linux)
      if [[ -f /etc/debian_version ]]; then
        echo "debian"
      else
        echo "linux_other"
      fi
      ;;
    *)
      echo "unsupported"
      ;;
  esac
}

print_java_install_hint() {
  local platform="$1"
  if [[ "$platform" == "macos" ]]; then
    cat <<'EOF'
Java 17+ is required. Install with:
  brew install openjdk@17
EOF
  elif [[ "$platform" == "debian" ]]; then
    cat <<'EOF'
Java 17+ is required. Install with:
  sudo apt-get update
  sudo apt-get install -y openjdk-17-jre-headless
EOF
  else
    cat <<'EOF'
Java 17+ is required. Please install OpenJDK 17 with your distro package manager.
EOF
  fi
}

copy_runtime_scripts() {
  cp "$REPO_ROOT/scripts/ibkr_readonly.py" "$TRADING_DIR/ibkr_readonly.py"
  cp "$REPO_ROOT/scripts/keepalive.py" "$TRADING_DIR/keepalive.py"
  chmod +x "$TRADING_DIR/ibkr_readonly.py" "$TRADING_DIR/keepalive.py"
}

create_env_if_missing() {
  local env_file="$TRADING_DIR/.env"
  if [[ -f "$env_file" ]]; then
    log ".env already exists, keeping current values"
    return
  fi

  cat > "$env_file" <<'EOF'
IB_HOST=127.0.0.1
IB_PORT=4001
IB_CLIENT_ID=1

# Optional: Telegram alerting for keepalive.py
# TG_BOT_TOKEN=
# TG_CHAT_ID=
EOF
  log "Created $env_file"
}

create_helper_scripts() {
  cat > "$TRADING_DIR/run-readonly.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
source venv/bin/activate
python ibkr_readonly.py
EOF

  cat > "$TRADING_DIR/run-keepalive.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
source venv/bin/activate
python keepalive.py
EOF

  chmod +x "$TRADING_DIR/run-readonly.sh" "$TRADING_DIR/run-keepalive.sh"
}

main() {
  local platform
  platform="$(detect_platform)"

  if [[ "$platform" == "unsupported" ]]; then
    die "Unsupported OS. Use Debian or macOS."
  fi

  if ! command -v python3 >/dev/null 2>&1; then
    die "python3 not found. Install Python 3.9+ first."
  fi

  if ! command -v java >/dev/null 2>&1; then
    print_java_install_hint "$platform"
    die "java not found."
  fi

  mkdir -p "$TRADING_DIR"
  cd "$TRADING_DIR"

  if [[ ! -d "venv" ]]; then
    log "Creating Python virtual environment at $TRADING_DIR/venv"
    python3 -m venv venv
  else
    log "Python virtual environment already exists"
  fi

  # shellcheck disable=SC1091
  source venv/bin/activate
  log "Installing Python dependencies (ib_insync, requests)"
  pip install --upgrade pip >/dev/null
  pip install ib_insync requests >/dev/null

  copy_runtime_scripts
  create_env_if_missing
  create_helper_scripts

  cat <<EOF

========================================
IBKR read-only setup completed.
Install location: $TRADING_DIR

Next steps:
1) Install and login IB Gateway (Stable): https://www.interactivebrokers.com/en/trading/ibgateway-stable.php
2) In IB Gateway -> API settings:
   - Enable socket clients
   - Port 4001 (live) or 4002 (paper)
   - Trusted IP: 127.0.0.1
3) Run: cd "$TRADING_DIR" && ./run-readonly.sh
4) Optional health check cron:
   */5 * * * * cd $TRADING_DIR && ./run-keepalive.sh >> $TRADING_DIR/keepalive.log 2>&1
========================================
EOF
}

main "$@"
