@echo off
REM XGPedia v8 - Daily data sync for Windows Task Scheduler
REM Recommended: run daily (e.g. 09:00 Tehran / 06:00 UTC).
REM The CSV updates weekly after match rounds; daily runs keep data fresh.
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

echo === XGPedia daily sync - %date% %time% === >> logs\sync.log

REM 1) snapshot before
python run.py status >> logs\sync.log 2>&1

REM 2) download results + xG for current season
python run.py sync-results >> logs\sync.log 2>&1
if errorlevel 1 echo [ERROR] sync-results failed >> logs\sync.log

REM 3) upcoming fixtures (needs FOOTBALL_DATA_ORG_TOKEN in .env)
python run.py fixtures --days 7 >> logs\sync.log 2>&1
if errorlevel 2 echo [WARN] fixtures failed (token missing or network) >> logs\sync.log

REM 4) snapshot after + freshness warning
python run.py status >> logs\sync.log 2>&1

echo === done === >> logs\sync.log
