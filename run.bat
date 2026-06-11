@echo off
REM AURIC - XAUUSD Trading Bot launcher (Windows)
setlocal EnableDelayedExpansion
cd /d "%~dp0"

REM --- locate python ---------------------------------------------------------
where python >nul 2>nul
if errorlevel 1 (
  echo [error] Python is not on PATH. Install Python 3.11+ from https://python.org
  pause & exit /b 1
)

REM --- create venv if missing ------------------------------------------------
if not exist .venv\Scripts\python.exe (
  echo [setup] Creating virtual environment...
  python -m venv .venv
  if errorlevel 1 (
    echo [error] Failed to create venv
    pause & exit /b 1
  )
)

REM --- always (re)install deps so this is idempotent -------------------------
echo [setup] Activating venv + installing dependencies (this can take a few minutes the first time)...
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip --quiet
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo [error] pip install failed — see messages above
  pause & exit /b 1
)

REM --- copy .env if missing --------------------------------------------------
if not exist .env (
  echo [setup] Copying .env.example to .env — please edit with your MT5 credentials.
  copy .env.example .env >nul
)

REM --- menu ------------------------------------------------------------------
echo.
echo ============================================================
echo  AURIC  -  XAUUSD Trading Bot
echo ============================================================
echo   1) Trading loop only
echo   2) Trading loop + dashboard
echo   3) Dashboard only
echo   4) Run a single bot tick (smoke test)
echo   5) Run a backtest
echo ============================================================
set /p CHOICE="Enter 1-5: "

if "%CHOICE%"=="1" python main.py
if "%CHOICE%"=="2" python main.py --dashboard
if "%CHOICE%"=="3" python -m streamlit run dashboard/app.py
if "%CHOICE%"=="4" python main.py --once
if "%CHOICE%"=="5" python -c "from backtester.engine import Backtester; from mt5_connector.factory import build_client; c=build_client(); df=c.get_ohlcv('XAUUSD','H1',2000); r=Backtester(df).run(); print(r.metrics)"

endlocal
