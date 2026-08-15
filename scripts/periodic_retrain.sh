#!/usr/bin/env bash
# scripts/periodic_retrain.sh
# Scheduled job to trigger model retraining on historical uploads and hot-reload model in running app.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== DocuVault Periodic Model Retraining ==="
echo "Project directory: $PROJECT_DIR"

cd "$PROJECT_DIR"

if [ -f "venv/bin/python3" ]; then
    PYTHON_BIN="venv/bin/python3"
else
    PYTHON_BIN="python3"
fi

echo "Running model retraining pipeline..."
$PYTHON_BIN app/train_models.py

echo "Triggering model hot-reload in DocuVault app..."
curl -s -X POST http://127.0.0.1:5001/admin/reload-models || true

echo "=== Retraining & Hot-Reload Complete ==="
