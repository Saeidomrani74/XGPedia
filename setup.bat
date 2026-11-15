@echo off
REM XGPedia v8 - Windows setup (run this once, by double-click)
REM Requires Python 3.12+ from python.org (check "Add python.exe to PATH" during install).
REM NOTE: keep this file ASCII-only. cmd.exe mis-parses .bat files containing UTF-8 text.

setlocal
cd /d "%~dp0"

set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

echo ============================================
echo   XGPedia v8 - Setup
echo ============================================

REM -- find a working Python (python, then py -3 launcher) --
set PYCMD=
python --version >nul 2>nul && set PYCMD=python
if not defined PYCMD py -3 --version >nul 2>nul && set PYCMD=py -3
if not defined PYCMD (
    echo [ERROR] Python not found.
    echo Install Python 3.12+ from https://www.python.org/downloads/
    echo and enable "Add python.exe to PATH" during install, then run setup.bat again.
    pause
    exit /b 1
)
echo [1/5] Python found: %PYCMD%

%PYCMD% -c "import sys; raise SystemExit(0 if sys.version_info>=(3,12) else 1)"
if errorlevel 1 (
    echo [ERROR] Python 3.12 or newer is required.
    echo Tip: if several Pythons are installed, run:  py -3.12 -m venv .venv
    pause
    exit /b 1
)

REM -- create virtual environment --
if exist .venv (
    echo [2/5] Virtual environment already exists.
) else (
    echo [2/5] Creating virtual environment...
    %PYCMD% -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Could not create the virtual environment.
        pause
        exit /b 1
    )
)

call .venv\Scripts\activate.bat

REM -- install packages (needs internet) --
echo [3/5] Installing packages...
python -m pip install --upgrade pip --quiet
pip install -e . --quiet
if errorlevel 1 (
    echo [ERROR] Package install failed. Check your internet connection,
    echo or run this and retry:  pip install -e . -i https://pypi.org/simple
    pause
    exit /b 1
)
pip install pytest --quiet
if errorlevel 1 (
    echo [ERROR] pytest install failed.
    pause
    exit /b 1
)

REM -- prepare .env from template --
echo [4/5] Preparing .env file...
if not exist .env (
    copy .env.example .env >nul
    echo   Created .env - later put your FOOTBALL_DATA_ORG_TOKEN inside it.
)

REM -- init database + run tests --
echo [5/5] Creating database and running tests...
python run.py init
if errorlevel 1 (
    echo [ERROR] Database init failed.
    pause
    exit /b 1
)
python -m pytest tests/ -q
if errorlevel 1 (
    echo [ERROR] Tests failed - see the output above.
    pause
    exit /b 1
)

echo.
echo ============================================
echo   Setup complete. All tests passed.
echo ============================================
echo Next steps:
echo   1^) Get a free token at https://www.football-data.org
echo   2^) Open the .env file and set:  FOOTBALL_DATA_ORG_TOKEN=your_token
echo   3^) Download results+xG:     python run.py sync-results
echo   4^) Upcoming fixtures:        python run.py fixtures --days 7
echo   5^) Data health check:       python run.py status
echo   6^) Browse fixture IDs:       python run.py list-fixtures
echo.
echo Full guide: README.md  and  docs\ folder
echo.
pause
