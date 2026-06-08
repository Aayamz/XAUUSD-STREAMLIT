"""Entry point — start the trading loop, then optionally launch the dashboard.

Usage:
    python main.py              # trading loop only
    python main.py --dashboard  # also launches the Streamlit dashboard
    python main.py --once       # run a single tick and exit (smoke test)
"""
from __future__ import annotations

import argparse
import signal
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from bot import TradingBot  # noqa: E402
from utils.config import get_config  # noqa: E402
from utils.logger import get_logger  # noqa: E402

log = get_logger(__name__)


def _install_signal_handlers(bot: TradingBot) -> None:
    def _handler(signum, _frame):
        log.info("Received signal %s — shutting down", signum)
        bot.shutdown()
        sys.exit(0)

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _handler)
        except Exception:
            pass  # Windows ignores SIGTERM in some envs


def main() -> None:
    p = argparse.ArgumentParser(description="XAUUSD SMC trading bot")
    p.add_argument("--dashboard", action="store_true", help="Also start the Streamlit dashboard")
    p.add_argument("--once", action="store_true", help="Run a single tick and exit")
    args = p.parse_args()

    bot = TradingBot()
    _install_signal_handlers(bot)

    if args.once:
        log.info("Running a single tick…")
        bot.tick()
        bot.shutdown()
        return

    if args.dashboard:
        import subprocess
        log.info("Launching dashboard…")
        subprocess.Popen(
            [sys.executable, "-m", "streamlit", "run", "dashboard/app.py",
             "--server.port", str(get_config().get("app", {}).get("dashboard_port", 8501))],
            cwd=str(ROOT),
        )

    cfg = get_config()
    interval = int(cfg.get("app", {}).get("refresh_seconds", 60))
    log.info("Starting trading loop — interval=%ss, symbol=%s",
             interval, cfg.get("app", {}).get("symbol", "XAUUSD"))

    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
    except ImportError:
        log.error(
            "APScheduler is not installed. Run `pip install -r requirements.txt` "
            "or use `--once` for a single tick."
        )
        bot.shutdown()
        sys.exit(1)

    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(bot.tick, "interval", seconds=interval, id="strategy", max_instances=1, coalesce=True)
    scheduler.start()


if __name__ == "__main__":
    main()
