#!/bin/bash
# Startup script for HERMES Laptop Health & Performance Monitor
cd "$(dirname "$0")"

if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

echo "Starting HERMES Laptop Health Monitor Dashboard on http://127.0.0.1:8000 ..."
python -m uvicorn src.dashboard.app:app --host 127.0.0.1 --port 8000
