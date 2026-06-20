@echo off
REM ============================================================
REM  trade-alert-bot — Windows quick-start
REM  Creates a venv, installs deps, and runs the bot.
REM ============================================================
setlocal

if not exist venv (
    echo [setup] Creating virtual environment...
    python -m venv venv
)

echo [setup] Installing dependencies...
call venv\Scripts\activate.bat
python -m pip install --quiet --upgrade pip
pip install -r requirements.txt

if not exist .env (
    if exist .env.example (
        echo [setup] Copying .env.example to .env -- add your TELEGRAM_BOT_TOKEN there.
        copy .env.example .env >nul
    )
)

echo [run] Starting trade-alert-bot...
python main.py

endlocal
