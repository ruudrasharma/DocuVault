#!/bin/bash
# =============================================================================
# DocuVault — Full Server Deployment Script
# Usage: bash setup_server.sh
# Runs on the TARGET Linux server as user 'rudra'
# =============================================================================
set -e

# ── Configuration ─────────────────────────────────────────────────────────────
APP_NAME="docuvault"
APP_DIR="/home/rudra/DocuVault"
REPO_URL="https://github.com/ruudrasharma/DocuVault.git"
VENV_DIR="$APP_DIR/venv"
SERVICE_USER="rudra"
APP_PORT="5000"
PYTHON="python3"

# ── Colors ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log()  { echo -e "${BLUE}[•]${NC} $*"; }
ok()   { echo -e "${GREEN}[✓]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
err()  { echo -e "${RED}[✗]${NC} $*"; exit 1; }

# ── Detect package manager ────────────────────────────────────────────────────
detect_pm() {
    if command -v apt-get &>/dev/null; then echo "apt"
    elif command -v dnf &>/dev/null; then echo "dnf"
    elif command -v yum &>/dev/null; then echo "yum"
    else err "Unsupported package manager. Install manually."; fi
}
PM=$(detect_pm)
log "Detected package manager: $PM"

# ── Install system dependencies ───────────────────────────────────────────────
log "Installing system dependencies..."
if [ "$PM" = "apt" ]; then
    sudo apt-get update -y
    sudo apt-get install -y \
        git python3 python3-pip python3-venv python3-dev \
        build-essential cmake ninja-build \
        libssl-dev libffi-dev \
        tesseract-ocr tesseract-ocr-eng \
        poppler-utils \
        libgl1-mesa-glx libglib2.0-0 \
        libjpeg-dev zlib1g-dev \
        curl wget unzip
elif [ "$PM" = "dnf" ] || [ "$PM" = "yum" ]; then
    sudo $PM install -y \
        git python3 python3-pip python3-devel \
        gcc gcc-c++ cmake ninja-build \
        openssl-devel libffi-devel \
        tesseract tesseract-langpack-eng \
        poppler-utils \
        mesa-libGL glib2 \
        libjpeg-turbo-devel zlib-devel \
        curl wget unzip
fi
ok "System dependencies installed"

# ── Clone / Update repo ───────────────────────────────────────────────────────
if [ -d "$APP_DIR/.git" ]; then
    log "Repo exists — pulling latest..."
    git -C "$APP_DIR" pull
else
    log "Cloning DocuVault from GitHub..."
    git clone "$REPO_URL" "$APP_DIR"
fi
ok "Code ready at $APP_DIR"

# ── Python virtual environment ────────────────────────────────────────────────
log "Setting up Python virtual environment..."
$PYTHON -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"
pip install --upgrade pip wheel setuptools
ok "Virtual environment ready"

# ── Build liboqs (Post-Quantum Cryptography) ──────────────────────────────────
LIBOQS_SRC="$HOME/liboqs_src"
LIBOQS_INSTALL="$HOME/liboqs_install"

log "Building liboqs (Post-Quantum Cryptography library)..."
if [ ! -d "$LIBOQS_SRC" ]; then
    git clone --depth 1 https://github.com/open-quantum-safe/liboqs.git "$LIBOQS_SRC"
fi
mkdir -p "$LIBOQS_SRC/build"
cmake -S "$LIBOQS_SRC" -B "$LIBOQS_SRC/build" \
    -DCMAKE_INSTALL_PREFIX="$LIBOQS_INSTALL" \
    -DBUILD_SHARED_LIBS=ON \
    -DOQS_BUILD_ONLY_LIB=ON \
    -GNinja
cmake --build "$LIBOQS_SRC/build" --parallel
cmake --install "$LIBOQS_SRC/build"
ok "liboqs built and installed to $LIBOQS_INSTALL"

log "Building liboqs-python..."
LIBOQS_PYTHON_SRC="$HOME/liboqs_python_src"
if [ ! -d "$LIBOQS_PYTHON_SRC" ]; then
    git clone https://github.com/open-quantum-safe/liboqs-python.git "$LIBOQS_PYTHON_SRC"
fi
cd "$LIBOQS_PYTHON_SRC"
export liboqs_DIR="$LIBOQS_INSTALL"
pip install .
cd "$APP_DIR"
ok "liboqs-python installed"

# ── Install Python dependencies ───────────────────────────────────────────────
log "Installing Python packages from requirements.txt..."
log "  (PyTorch ~2GB — may take 10-20 minutes on first run)"
pip install -r "$APP_DIR/requirements.txt"
ok "Python dependencies installed"

# ── Create runtime directories ────────────────────────────────────────────────
log "Creating runtime directories..."
mkdir -p "$APP_DIR/instance"
mkdir -p "$APP_DIR/data"
mkdir -p "$APP_DIR/blockchain_data"
ok "Directories created"

# ── Set up .env ───────────────────────────────────────────────────────────────
if [ ! -f "$APP_DIR/.env" ]; then
    log "Generating .env with a secure SECRET_KEY..."
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    cat > "$APP_DIR/.env" << EOF
SECRET_KEY=$SECRET_KEY
FLASK_ENV=production
PORT=5000
EOF
    warn ".env created with auto-generated SECRET_KEY"
    warn "Edit $APP_DIR/.env if you need custom settings"
else
    ok ".env already exists — skipping"
fi

# ── Create systemd service ────────────────────────────────────────────────────
log "Creating systemd service: $APP_NAME..."
sudo tee /etc/systemd/system/${APP_NAME}.service > /dev/null << EOF
[Unit]
Description=DocuVault - Document Vault Application
After=network.target
StartLimitIntervalSec=0

[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$VENV_DIR/bin/gunicorn \
    --workers 2 \
    --bind 0.0.0.0:$APP_PORT \
    --timeout 120 \
    --access-logfile $APP_DIR/access.log \
    --error-logfile $APP_DIR/error.log \
    "run:app"
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=$APP_NAME

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable "$APP_NAME"
ok "Systemd service created and enabled"

# ── ML Anomaly Retrain timer (weekly) ────────────────────────────────────────
log "Installing ML anomaly model retrain timer..."
sudo tee /etc/systemd/system/docuvault-retrain.service > /dev/null << EOF
[Unit]
Description=DocuVault — Weekly ML anomaly model retrain
After=network.target

[Service]
Type=oneshot
User=$SERVICE_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$VENV_DIR/bin/python3 -m app.ml_anomaly --retrain
StandardOutput=journal
StandardError=journal
SyslogIdentifier=docuvault-retrain
EOF

sudo tee /etc/systemd/system/docuvault-retrain.timer > /dev/null << EOF
[Unit]
Description=DocuVault — Run ML retrain every Sunday at 03:00

[Timer]
OnCalendar=Sun *-*-* 03:00:00
Persistent=true

[Install]
WantedBy=timers.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable docuvault-retrain.timer
sudo systemctl start docuvault-retrain.timer
ok "ML retrain timer enabled (fires weekly Sun 03:00)"

# ── Federated Learning server ─────────────────────────────────────────────────
log "Installing Federated Learning server service..."
sudo tee /etc/systemd/system/docuvault-fl.service > /dev/null << EOF
[Unit]
Description=DocuVault — Federated Learning Flower server
After=network.target

[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$VENV_DIR/bin/python3 -m app.federated_learning --server
Restart=on-failure
RestartSec=30
StandardOutput=journal
StandardError=journal
SyslogIdentifier=docuvault-fl

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable docuvault-fl
ok "Federated Learning server service installed and enabled"

# ── Open firewall port ────────────────────────────────────────────────────────
log "Opening port $APP_PORT in firewall..."
if command -v ufw &>/dev/null; then
    sudo ufw allow "$APP_PORT/tcp" 2>/dev/null || warn "ufw allow failed — check manually"
    ok "ufw: port $APP_PORT allowed"
elif command -v firewall-cmd &>/dev/null; then
    sudo firewall-cmd --permanent --add-port="$APP_PORT/tcp" 2>/dev/null || warn "firewalld failed — check manually"
    sudo firewall-cmd --reload 2>/dev/null || true
    ok "firewalld: port $APP_PORT allowed"
else
    warn "No firewall manager found — ensure port $APP_PORT is open"
fi

# ── Start the service ─────────────────────────────────────────────────────────
log "Starting DocuVault service..."
sudo systemctl restart "$APP_NAME"
sleep 3

if sudo systemctl is-active --quiet "$APP_NAME"; then
    ok "DocuVault is running!"
    echo ""
    echo -e "${GREEN}════════════════════════════════════════${NC}"
    echo -e "${GREEN}  DocuVault is LIVE!${NC}"
    echo -e "${GREEN}  URL: http://$(hostname -I | awk '{print $1}'):$APP_PORT${NC}"
    echo -e "${GREEN}  Tailscale: http://100.100.10.10:$APP_PORT${NC}"
    echo -e "${GREEN}════════════════════════════════════════${NC}"
    echo ""
    echo "  Useful commands:"
    echo "    sudo systemctl status $APP_NAME   # Check status"
    echo "    sudo journalctl -u $APP_NAME -f   # View live logs"
    echo "    sudo systemctl restart $APP_NAME  # Restart"
    echo "    sudo systemctl stop $APP_NAME     # Stop"
else
    err "Service failed to start. Check logs: sudo journalctl -u $APP_NAME -n 50"
fi
