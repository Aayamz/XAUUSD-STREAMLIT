#!/usr/bin/env bash
# XAUUSD SMC Bot launcher (Linux/macOS)
set -e
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "[setup] Creating virtual environment..."
  python3 -m venv .venv
  # shellcheck disable=SC1091
  source .venv/bin/activate
  pip install --upgrade pip
  pip install -r requirements.txt
else
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

if [ ! -f ".env" ]; then
  echo "[setup] Copying .env.example to .env — please edit with your MT5 credentials."
  cp .env.example .env
fi

echo
echo "Choose what to launch:"
echo "  1) Trading loop only"
echo "  2) Trading loop + dashboard"
echo "  3) Dashboard only"
echo "  4) Run a single bot tick (smoke test)"
echo "  5) Run a backtest"
read -rp "Enter 1-5: " CHOICE

case "$CHOICE" in
  1) python main.py ;;
  2) python main.py --dashboard ;;
  3) python -m streamlit run dashboard/app.py ;;
  4) python main.py --once ;;
  5) python -c "from backtester.engine import Backtester; from mt5_connector.factory import build_client; c=build_client(); df=c.get_ohlcv('XAUUSD','H1',2000); r=Backtester(df).run(); print(r.metrics)" ;;
esac
