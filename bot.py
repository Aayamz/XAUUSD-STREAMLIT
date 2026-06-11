"""Auto-trading loop.

The loop:
  1. Fetches LTF + HTF bars
  2. Runs the strategy
  3. Checks risk limits
  4. Opens / manages trades accordingly
  5. Logs results and emits Telegram notifications

It is designed to be safe to restart (idempotent) and resilient to MT5
disconnects (will try to reconnect on the next tick).
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone

import pandas as pd

from data.fetcher import DataFetcher
from mt5_connector.factory import build_client
from risk_manager import RiskLimits, TradeManager
from risk_manager.position_sizer import compute_lot_size
from strategy.luxalgo_smc import Direction, Signal
from strategy import create_strategy
from utils.config import get_config
from utils.logger import get_logger, log_trade
from utils.telegram import notifier

log = get_logger(__name__)
SIGNAL_LOG = "logs/signals.jsonl"


class TradingBot:
    def __init__(self):
        self.cfg = get_config()
        self.client = build_client()
        self.fetcher = DataFetcher(self.client)
        strat_cfg = self.cfg.get("strategy", {})
        self.strategy = create_strategy(
            strat_cfg.get("active_strategy", "luxalgo_smc"),
            cfg=strat_cfg,
            mode=strat_cfg.get("mode", "swing"),
        )
        self.risk = RiskLimits()
        self.trade_mgr = TradeManager()
        self.symbol = self.cfg.get("app", {}).get("symbol", "XAUUSD")
        self._last_realized_pnl: float = 0.0

    # --- public ---------------------------------------------------------------
    def tick(self) -> Signal | None:
        """Run one strategy cycle. Returns the latest signal (for the UI)."""
        try:
            if not self.client.is_connected():
                log.warning("MT5 not connected — attempting reconnect")
                self.client.connect()
        except Exception as e:  # noqa: BLE001
            log.error("Reconnect failed: %s", e)
            return None

        try:
            ltf = self.cfg.get("strategy", {}).get("entry_timeframe", "M15")
            htf = self.cfg.get("strategy", {}).get("higher_timeframe", "H4")
            df_ltf = self.fetcher.get_bars(self.symbol, ltf, 300)
            df_htf = self.fetcher.get_bars(self.symbol, htf, 300) if htf else None
        except Exception as e:  # noqa: BLE001
            log.error("Failed to fetch bars: %s", e)
            return None

        sig = self.strategy.generate_signal(df_ltf, df_htf=df_htf, symbol=self.symbol)
        self._log_signal(sig)
        notifier().send(self._format_signal_msg(sig))

        # update risk state
        try:
            account = self.client.get_account_info()
            equity = float(account.get("equity", 0.0))
            balance = float(account.get("balance", 0.0))
            realised = balance - (self._last_realized_pnl or 0)
            self.risk.update(equity=equity, closed_pnl=balance - (self._last_realized_pnl or balance))
            self._last_realized_pnl = balance
        except Exception as e:  # noqa: BLE001
            log.error("Failed to read account info: %s", e)
            return sig

        try:
            positions = self.client.get_positions(symbol=self.symbol)
        except Exception as e:  # noqa: BLE001
            log.error("Failed to read positions: %s", e)
            positions = []

        decision = self.risk.check(equity=equity, open_positions=len(positions))
        # Check if we should ignore session filters for testing
        from utils.config import get_config
        config = get_config().get("strategy", {})
        ignore_sessions = config.get("ignore_session_filter", False)
        
        if not decision.allowed and not ignore_sessions:
            log.warning("Trading paused: %s", decision.reason)
            notifier().send(f"⏸ <b>Trading paused</b>: {decision.reason}")
            self._manage_open_trades(positions, df_ltf)
            return sig

        # 1) Manage open positions
        self._manage_open_trades(positions, df_ltf)

        # 2) Open new position on fresh signal
        min_confidence = self.cfg.get("strategy", {}).get("confidence_threshold", 55)
        if self.cfg.get("strategy", {}).get("mode") == "scalp":
            min_confidence = self.cfg.get("strategy", {}).get("scalp_confidence_threshold", 50)

        min_rr = self.cfg.get("strategy", {}).get("min_rr", 2.0)
        if self.cfg.get("strategy", {}).get("mode") == "scalp":
            min_rr = self.cfg.get("strategy", {}).get("scalp_min_rr", 1.0)

        if sig.is_actionable(min_confidence=min_confidence, min_rr=min_rr) and not positions:
            self._open_trade(sig, account, df_ltf)
        
        # 3) Handle manual trade requests from dashboard (for testing)
        # Check if there's a manual trade request in the control bus
        try:
            from dashboard.state import get_control_bus
            control_bus = get_control_bus()
            manual_cmds = control_bus.drain()
            for cmd in manual_cmds:
                if cmd.get("type") == "MANUAL_TRADE" and cmd.get("signal_data"):
                    signal_data = cmd["signal_data"]
                    # Reconstruct signal object from data
                    from strategy.luxalgo_smc import Signal, Direction
                    import numpy as np
                    
                    # Only execute if the signal is still valid and actionable
                    if signal_data.get("is_actionable", False):
                        # Create a temporary signal object for execution
                        temp_sig = Signal(
                            direction=Direction.LONG if signal_data["direction"] == "LONG" else Direction.SHORT,
                            confidence=signal_data["confidence"],
                            reasons=signal_data["reasons"],
                            htf_bias=signal_data.get("htf_bias", "UNKNOWN"),
                            session=signal_data.get("session"),
                            entry=signal_data["entry"],
                            stop_loss=signal_data["stop_loss"],
                            take_profit=signal_data["take_profit"],
                            rr=signal_data["rr"],
                            metadata=signal_data.get("metadata", {}),
                            timestamp=signal_data["timestamp"]
                        )
                        
                        # Execute the trade if no positions exist (safety check)
                        if not positions:
                            self._open_trade(temp_sig, account, df_ltf)
                            log.info(f"Manual trade executed via dashboard: {signal_data['direction']} at {signal_data['entry']}")
                        else:
                            log.info("Manual trade requested but position already exists - skipping")
        except Exception as e:  # noqa: BLE001
            log.error(f"Error processing manual trade request: {e}")

        return sig

    # --- helpers --------------------------------------------------------------
    def _open_trade(self, sig: Signal, account: dict, df_ltf: pd.DataFrame) -> None:
        try:
            info = self.client.get_symbol_info(self.symbol)
        except Exception as e:  # noqa: BLE001
            log.error("get_symbol_info failed: %s", e)
            return
        equity = float(account.get("equity", 0.0))
        # Preserve the strategy's risk distance and RR but rebase them to the
        # *current* tick price — the signal's absolute SL/TP are stale once the
        # market moves.
        risk = abs(sig.entry - sig.stop_loss)
        rr = sig.rr if sig.rr > 0 else 2.0
        bid = float(info.get("bid", 0))
        ask = float(info.get("ask", 0))
        digits = int(info.get("digits", 2))

        if sig.direction == Direction.LONG:
            order_type = "BUY"
            sl = round(bid - risk, digits)
            tp = round(ask + risk * rr, digits)
        else:
            order_type = "SELL"
            sl = round(ask + risk, digits)
            tp = round(bid - risk * rr, digits)

        lots = compute_lot_size(equity, sig.entry, sig.stop_loss, info)
        if lots <= 0:
            log.warning("Computed lot size is 0 — skipping")
            return
        log.info("_open_trade %s bid=%.2f ask=%.2f risk=%.2f rr=%.1f -> sl=%.2f tp=%.2f lots=%.2f",
                 order_type, bid, ask, risk, rr, sl, tp, lots)
        try:
            r = self.client.place_order(
                self.symbol, order_type, lots,
                sl=sl, tp=tp,
                comment=f"smc:{sig.htf_bias}",
                magic=9001,
            )
        except Exception as e:  # noqa: BLE001
            log.error("Order failed: %s", e)
            notifier().send(f"❌ Order failed: {e}")
            return
        log.info("place_order response: %s", r)
        if r.get("ok"):
            final_sl = r.get("sl_adjusted") if r.get("sl_adjusted") is not None else sig.stop_loss
            final_tp = r.get("tp_adjusted") if r.get("tp_adjusted") is not None else sig.take_profit
            final_vol = r.get("volume", lots)
            log.info("Opened %s %.2f @ %.2f (sl=%.2f tp=%.2f ticket=%s)",
                     order_type, final_vol, r.get("price", sig.entry),
                     final_sl, final_tp, r.get("ticket"))
            log_trade({
                "event": "open", "ticket": r.get("ticket"),
                "side": order_type, "volume": final_vol,
                "price": r.get("price", sig.entry),
                "sl": final_sl, "tp": final_tp,
                "htf_bias": sig.htf_bias, "confidence": sig.confidence,
                "reasons": sig.reasons,
            })
            notifier().send(
                f"✅ <b>{order_type}</b> {final_vol} {self.symbol} @ {r.get('price', sig.entry):.2f}\n"
                f"SL {final_sl:.2f} · TP {final_tp:.2f} · conf {sig.confidence:.0f}%\n"
                f"Ticket: <code>{r.get('ticket')}</code>"
            )
        else:
            err = r.get("error") or r.get("message") or r.get("comment") or "unknown error"
            log.error("MT5 rejected order: %s (retcode=%s, full response: %s)",
                      err, r.get("retcode"), r)
            notifier().send(f"❌ MT5 rejected order ({r.get('retcode')}): {err}")

    def _manage_open_trades(self, positions: list[dict], df_ltf: pd.DataFrame) -> None:
        try:
            info = self.client.get_symbol_info(self.symbol)
        except Exception:
            info = None
        bid = float(info.get("bid", 0)) if info else 0.0
        ask = float(info.get("ask", 0)) if info else 0.0
        for p in positions:
            current = bid if p["type"] == "BUY" else ask
            act = self.trade_mgr.manage(p, df_ltf, current_price=current)

            # Partial close (multi-TP)
            if act.partial_closed and act.partial_close_volume is not None:
                try:
                    ok = self.client.partial_close_position(
                        p["ticket"], act.partial_close_volume
                    )
                    if ok:
                        log.info(
                            "Partial close ticket=%s vol=%.2f — %s",
                            p["ticket"], act.partial_close_volume, act.note,
                        )
                        notifier().send(
                            f"🎯 <b>Partial TP</b> ticket <code>{p['ticket']}</code>\n"
                            f"Closed {act.partial_close_volume} lots — {act.note}"
                        )
                    else:
                        log.warning("Partial close failed for ticket %s", p["ticket"])
                except Exception as e:  # noqa: BLE001
                    log.error("Partial close error for %s: %s", p["ticket"], e)

            # SL / TP modification
            if act.modified and act.new_sl is not None:
                try:
                    self.client.modify_position(p["ticket"], sl=act.new_sl, tp=p.get("tp"))
                    log.info("Modified ticket %s: SL -> %.2f (%s)", p["ticket"], act.new_sl, act.note)
                except Exception as e:  # noqa: BLE001
                    log.error("Modify failed for %s: %s", p["ticket"], e)

    def _log_signal(self, sig: Signal) -> None:
        import os
        os.makedirs("logs", exist_ok=True)
        with open(SIGNAL_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": sig.timestamp,
                "direction": sig.direction.value,
                "confidence": sig.confidence,
                "entry": sig.entry, "sl": sig.stop_loss, "tp": sig.take_profit,
                "rr": sig.rr, "htf_bias": sig.htf_bias,
                "reasons": sig.reasons,
            }) + "\n")

    def _format_signal_msg(self, sig: Signal) -> str:
        return (
            f"📊 <b>{sig.direction.value}</b> · conf {sig.confidence:.0f}% · "
            f"HTF {sig.htf_bias}\n"
            f"E {sig.entry:.2f} · SL {sig.stop_loss:.2f} · TP {sig.take_profit:.2f} · RR {sig.rr:.2f}\n"
            + "; ".join(sig.reasons[:3])
        )

    def shutdown(self) -> None:
        try:
            self.client.disconnect()
        except Exception:
            pass
