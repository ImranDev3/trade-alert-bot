#!/usr/bin/env bash
# ============================================================
#  trade-alert-bot — Linux / macOS quick-start
#  Creates a venv, installs deps, and runs the bot.
# ============================================================
set -euo pipefail

if [ ! -d venv ]; then
    echo "[setup] Creating virtual environment..."
    python3 -m venv venv
fi

echo "[setup] Installing dependencies..."
# shellcheck disable=SC1091
source venv/bin/activate
python -m pip install --quiet --upgrade pip
pip install -r requirements.txt

if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        echo "[setup] Copying .env.example to .env -- add your TELEGRAM_BOT_TOKEN there."
        cp .env.example .env
    fi
fi

echo "[run] Starting trade-alert-bot..."
python main.py
