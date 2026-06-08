"""Event-driven backtester for the LuxAlgo SMC strategy.

Usage:
    from backtester.engine import Backtester
    bt = Backtester(df_ltf=df_ltf, df_htf=df_htf, ...)
    result = bt.run()
    print(result.metrics)
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from data.indicators import atr
from risk_manager.position_sizer import compute_lot_size
from strategy.luxalgo_smc import Direction, Signal
from strategy import create_strategy
from utils.logger import get_logger

log = get_logger(__name__)


@dataclass
class Trade:
    side: str
    entry_time: pd.Timestamp
    entry_price: float
    sl: float
    tp: float
    exit_time: pd.Timestamp | None = None
    exit_price: float | None = None
    pnl: float = 0.0
    reason: str = ""


@dataclass
class BacktestResult:
    trades: list[Trade] = field(default_factory=list)
    equity_curve: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    metrics: dict[str, float] = field(default_factory=dict)


class Backtester:
    def __init__(
        self,
        df_ltf: pd.DataFrame,
        df_htf: pd.DataFrame | None = None,
        initial_balance: float = 10_000.0,
        risk_pct: float = 1.0,
        contract_size: float = 100.0,
        commission_per_lot: float = 7.0,
        spread: float = 0.30,
        symbol_info: dict[str, Any] | None = None,
        strategy_mode: str = "swing",
    ):
        self.df = df_ltf.reset_index(drop=True).copy()
        self.df_htf = df_htf
        self.initial_balance = initial_balance
        self.risk_pct = risk_pct
        self.contract_size = contract_size
        self.commission = commission_per_lot
        self.spread = spread
        self.symbol_info = symbol_info or {
            "point": 0.01, "contract_size": contract_size, "digits": 2,
            "volume_min": 0.01, "volume_max": 100.0, "volume_step": 0.01,
        }
        self.strategy = create_strategy("luxalgo_smc", mode=strategy_mode)

    # --- public ---------------------------------------------------------------
    def run(self) -> BacktestResult:
        balance = self.initial_balance
        equity_pts: list[tuple[pd.Timestamp, float]] = []
        trades: list[Trade] = []
        open_trade: Trade | None = None

        n = len(self.df)
        for i in range(60, n):
            bar = self.df.iloc[i]
            # mark-to-market equity
            if open_trade is not None:
                cur = float(bar["close"])
                mtm = self._pnl(open_trade, cur)
                equity = balance + mtm
            else:
                equity = balance
            equity_pts.append((bar["time"], equity))

            # 1) Manage open trade: check SL / TP intrabar
            if open_trade is not None:
                hit_sl, hit_tp, exit_price = self._check_intrabar(open_trade, bar)
                if hit_sl or hit_tp:
                    open_trade.exit_time = bar["time"]
                    open_trade.exit_price = exit_price
                    open_trade.pnl = self._pnl(open_trade, exit_price) - self.commission * open_trade.lots  # type: ignore[attr-defined]
                    open_trade.reason = "TP" if hit_tp else "SL"
                    balance += open_trade.pnl
                    trades.append(open_trade)
                    open_trade = None
                    continue

            # 2) Generate signal on closed bar (only if trading is allowed)
            if not self._is_trading_allowed(bar["time"]):
                # Skip signal generation when outside trading session
                continue
                
            window = self.df.iloc[max(0, i - 250) : i + 1]
            htf = self._align_htf(bar["time"])
            sig: Signal = self.strategy.generate_signal(window, df_htf=htf)

            # 3) Open trade on fresh signal (only one at a time here)
            if open_trade is None and sig.is_actionable():
                lots = compute_lot_size(
                    equity=balance,
                    entry=sig.entry,
                    stop_loss=sig.stop_loss,
                    symbol_info=self.symbol_info,
                    risk_pct=self.risk_pct,
                )
                open_trade = Trade(
                    side="BUY" if sig.direction == Direction.LONG else "SELL",
                    entry_time=bar["time"],
                    entry_price=sig.entry + (self.spread / 2 if sig.direction == Direction.LONG else -self.spread / 2),
                    sl=sig.stop_loss,
                    tp=sig.take_profit,
                )
                open_trade.lots = lots  # type: ignore[attr-defined]
                open_trade.signal = sig  # type: ignore[attr-defined]

        # close any remaining open trade at last bar close
        if open_trade is not None:
            last = self.df.iloc[-1]
            open_trade.exit_time = last["time"]
            open_trade.exit_price = float(last["close"])
            open_trade.pnl = self._pnl(open_trade, open_trade.exit_price) - self.commission * open_trade.lots  # type: ignore[attr-defined]
            open_trade.reason = "eod"
            balance += open_trade.pnl
            trades.append(open_trade)

        eq_series = pd.Series(
            [v for _, v in equity_pts],
            index=pd.to_datetime([t for t, _ in equity_pts], utc=True),
            name="equity",
        )
        metrics = self._metrics(trades, eq_series)
        return BacktestResult(trades=trades, equity_curve=eq_series, metrics=metrics)

    # --- helpers --------------------------------------------------------------
    def _check_intrabar(self, t: Trade, bar: pd.Series) -> tuple[bool, bool, float]:
        if t.side == "BUY":
            hit_sl = bar["low"] <= t.sl
            hit_tp = bar["high"] >= t.tp
            if hit_sl and hit_tp:
                # conservative: assume SL first
                return True, False, t.sl
            if hit_sl:
                return True, False, t.sl
            if hit_tp:
                return False, True, t.tp
        else:
            hit_sl = bar["high"] >= t.sl
            hit_tp = bar["low"] <= t.tp
            if hit_sl and hit_tp:
                return True, False, t.sl
            if hit_sl:
                return True, False, t.sl
            if hit_tp:
                return False, True, t.tp
        return False, False, 0.0

    def _pnl(self, t: Trade, price: float) -> float:
        direction = 1 if t.side == "BUY" else -1
        return (price - t.entry_price) * direction * t.lots * self.contract_size  # type: ignore[attr-defined]

    def _align_htf(self, ts: pd.Timestamp) -> pd.DataFrame | None:
        if self.df_htf is None:
            return None
        mask = self.df_htf["time"] <= ts
        if not mask.any():
            return None
        return self.df_htf[mask].tail(200).reset_index(drop=True)

    def _is_trading_allowed(self, ts: pd.Timestamp) -> bool:
        """Check if trading is allowed at the given timestamp (respects session filter and weekend)."""
        from utils.config import get_config
        
        config = get_config().get("strategy", {})
        # Check if we should ignore session filters
        if config.get("ignore_session_filter", False):
            # Ignore session and weekend filters
            return True
        
        # Extract hour and weekday from the timestamp
        # ts is a pandas Timestamp, convert to python datetime for weekday check
        dt = ts.to_pydatetime()
        hour = dt.hour
        weekday = dt.weekday()  # Monday=0, Sunday=6
        
        # Check if it's weekend (Sat=5, Sun=6)
        if weekday >= 5:
            return False
            
        # Check session times from config
        cfg = config.get("sessions", {})
        if not cfg:
            return False
            
        # London: 7-16 UTC
        # New York: 12-21 UTC  
        # Asia: 0-8 UTC (disabled in config)
        
        london_enabled = cfg.get("london", {}).get("enabled", True)
        ny_enabled = cfg.get("new_york", {}).get("enabled", True)
        asia_enabled = cfg.get("asia", {}).get("enabled", False)
        
        london_start = cfg.get("london", {}).get("start", 7)
        london_end = cfg.get("london", {}).get("end", 16)
        ny_start = cfg.get("new_york", {}).get("start", 12)
        ny_end = cfg.get("new_york", {}).get("end", 21)
        asia_start = cfg.get("asia", {}).get("start", 0)
        asia_end = cfg.get("asia", {}).get("end", 8)
        
        in_london = london_enabled and (london_start <= hour < london_end)
        in_ny = ny_enabled and (ny_start <= hour < ny_end)
        in_asia = asia_enabled and (asia_start <= hour < asia_end)
        
        return in_london or in_ny or in_asia

    @staticmethod
    def _metrics(trades: list[Trade], equity: pd.Series) -> dict[str, float]:
        if not trades:
            return {"trades": 0}
        pnls = np.array([t.pnl for t in trades])
        wins = pnls[pnls > 0]
        losses = pnls[pnls <= 0]
        win_rate = (len(wins) / len(pnls) * 100) if len(pnls) else 0.0
        gross_profit = float(wins.sum()) if len(wins) else 0.0
        gross_loss = float(-losses.sum()) if len(losses) else 0.0
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf")
        avg_win = float(wins.mean()) if len(wins) else 0.0
        avg_loss = float(losses.mean()) if len(losses) else 0.0
        max_dd = 0.0
        if not equity.empty:
            peak = equity.cummax()
            dd = (equity - peak) / peak
            max_dd = float(dd.min() * 100)
        return {
            "trades": int(len(trades)),
            "win_rate_pct": round(win_rate, 2),
            "profit_factor": round(profit_factor, 2) if math.isfinite(profit_factor) else 99.99,
            "net_pnl": round(float(pnls.sum()), 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "max_drawdown_pct": round(max_dd, 2),
            "final_equity": round(float(equity.iloc[-1]) if not equity.empty else 0.0, 2),
        }
