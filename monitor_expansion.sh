#!/bin/bash
# Monitor dataset expansion progress

LOG_FILE="logs/dataset_expansion.log"

echo "=== DATASET EXPANSION MONITOR ==="
echo "Log file: $LOG_FILE"
echo ""

# Check if process is running
if ps aux | grep "expand_historical" | grep -v grep > /dev/null; then
    echo "✓ Processo in esecuzione"
    PID=$(ps aux | grep "expand_historical" | grep -v grep | awk '{print $2}')
    echo "  PID: $PID"
else
    echo "✗ Processo non in esecuzione"
fi

echo ""
echo "--- Ultimi log (aggiornamento real-time) ---"
echo ""

# Tail log file with follow
if [ -f "$LOG_FILE" ]; then
    tail -f "$LOG_FILE"
else
    echo "⚠ File log non ancora creato"
    echo "Aspettando..."
    # Wait for file to be created
    while [ ! -f "$LOG_FILE" ]; do
        sleep 1
    done
    tail -f "$LOG_FILE"
fi
