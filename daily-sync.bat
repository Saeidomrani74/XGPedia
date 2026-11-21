@echo off
REM XGPedia v10 - Daily production chain for Windows Task Scheduler
REM Recommended: run daily (e.g. 09:00 Tehran / 05:30 UTC) - previews are made
REM for TOMORROW's matches, so the review queue is ready during the day.
REM
REM One command does the whole chain (NEXT_STEPS stage 3):
REM   sync-results -> fixtures --days 7 -> status (staleness warning) ->
REM   for each tomorrow match without a post: facts -> draft -> render-post ->
REM   Telegram review queue (needs TELEGRAM_BOT_TOKEN; otherwise WARN only).
REM Re-running the same day creates no duplicate posts (daily is idempotent).
REM
REM Exit codes for Task Scheduler: 0 = all good, 1 = partial failures.
REM Full log: logs\daily.log   (Telegram moderation bot must run separately:
REM   python -m src.xgpedia.publishers.telegram_bot)
REM NOTE: keep this file ASCII-only. cmd.exe mis-parses .bat files containing UTF-8 text.

setlocal
cd /d "%~dp0"

set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

if not exist .venv (
    echo [ERROR] .venv not found. Run setup.bat first.
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat

if not exist logs mkdir logs

echo === XGPedia daily chain - %date% %time% === >> logs\daily.log

python run.py daily >> logs\daily.log 2>&1
if errorlevel 1 (
    echo [WARN] daily chain finished with errors - see logs\daily.log >> logs\daily.log
    echo === done with errors === >> logs\daily.log
    exit /b 1
)

echo === done OK === >> logs\daily.log
exit /b 0
