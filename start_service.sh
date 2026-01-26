#!/usr/bin/env bash
# Avvia il servizio web + scheduler per il progetto BET
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$ROOT_DIR/.venv_new"
LOG_DIR="$ROOT_DIR/logs"
mkdir -p "$LOG_DIR"

# Crea venv se non esiste
if [ ! -d "$VENV_DIR" ]; then
  /usr/bin/python3 -m venv "$VENV_DIR"
fi

# Attiva venv
source "$VENV_DIR/bin/activate"

# Installa requisiti
pip install --upgrade pip > /dev/null 2>&1 || true
pip install -r "$ROOT_DIR/requirements.txt" > /dev/null 2>&1 || true

# Export environment variables utili
export FLASK_ENV=production
export BET_DASH_PORT="5000"

# Avvia l'app in background, logga su file
echo "[$(date)] Avvio servizio BET..." >> "$LOG_DIR/service.log"
nohup python "$ROOT_DIR/app.py" >> "$LOG_DIR/service.log" 2>&1 &
PID=$!
echo "Servizio avviato (PID: $PID). Log: $LOG_DIR/service.log"

# Disattiva venv (il processo figlio mantiene l'ambiente)
deactivate || true
