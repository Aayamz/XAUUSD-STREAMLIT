# AURIC — XAUUSD Trading Bot

A professional Forex auto-trading bot focused on **XAUUSD (Gold)** with a
Streamlit dashboard, MetaTrader 5 integration, and **8 configurable
strategies** including Smart-Money-Concepts, HuggingFace model plug-ins,
and classic scalpers.

> **Status:** working core — MT5 connector (real + mock), strategy registry,
> multi-TP trade manager, trailing/breakeven, backtester, and full dashboard.
> Ready for demo / paper trading immediately; tune strategy parameters via
> `config/config.yaml` before going live.

---

## Highlights

* **8 built-in strategies** — register via `@register_strategy`, select
  from the dashboard dropdown, combine preset HuggingFace models or build
  your own custom model from the Strategy Maker page.
* **Multi-TP with auto partial-close** — configurable TP levels (default:
  TP1@1R/30%, TP2@2R/30%, TP3@3R/40%), executed automatically per bar.
* **Trailing stop** — activates at a configurable R:R threshold
  (`trailing_start_rr`), only ratchets in profit direction.
* **Streamlit dashboard** with a Plotly chart annotated with Order Blocks,
  Fair Value Gaps, Liquidity levels, BOS/CHoCH, and premium/discount.
* **Strategy Maker** — 3-tab UI to browse HuggingFace repos, load preset
  models (XGBoost, LSTM, ensemble), or plug your own `.joblib`/`.pt` file.
* **Strict risk management** — dynamic position sizing, daily loss limit,
  max drawdown protection, trailing stop, breakeven, partial TP.
* **MT5 integration** via the official `MetaTrader5` Python package with
  automatic fallback to a **mock client** so everything is testable without
  an MT5 terminal.
* **Backtester** — event-driven engine with SL/TP intrabar checks, commission
  and spread.
* **Encrypted credentials** at rest (Fernet) and safe `.env`-based config.
* **Telegram alerts** for signals, executions, and risk breaches (optional).

---

## Project layout

```
xauusd-bot/
├── main.py                 # entry point (trading loop + optional dashboard)
├── run.bat                 # one-click launcher with a menu
├── requirements.txt
├── .env.example            # MT5 + Telegram + encryption key
├── config/
│   └── config.yaml         # strategy + risk + dashboard + TP levels config
├── mt5_connector/          # real + mock MT5 client, factory
│   ├── factory.py
│   ├── mock_client.py
│   └── real_client.py
├── data/                   # fetcher, indicator helpers
│   ├── fetcher.py
│   └── indicators.py
├── strategy/               # strategy registry + 8 built-in strategies
│   ├── __init__.py         # @register_strategy, create_strategy(), list_strategies()
│   ├── luxalgo_smc.py      # Smart-Money-Concepts (swing + scalp)
│   ├── hf_scalping.py      # MA crossover with trend persistence
│   ├── ema_crossover.py    # EMA crossover (9/21) with trend fallback
│   ├── bollinger_bounce.py # BB mean reversion + momentum fallback
│   ├── rsi_stoch.py        # RSI + Stochastic with momentum fallback
│   ├── grid_scalper.py     # Grid trading in range-bound markets
│   ├── tick_scalper.py     # Volume spike + price momentum
│   ├── macd_zero_line.py   # MACD zero-line cross + momentum fallback
│   └── hf_plugin.py        # Generic HuggingFace model plug-in (.joblib/.pt)
├── risk_manager/           # position sizing, limits, trade management
│   ├── position_sizer.py
│   ├── trade_manager.py    # multi-TP, trailing SL, breakeven, partial close
│   └── limits.py
├── backtester/             # event-driven backtest engine
├── dashboard/              # Streamlit multi-page app
│   ├── app.py              # autorefresh, navbar, strategy selector
│   ├── components/         # chart, metrics, signal panel, trade controls
│   └── views/              # home, live_chart, signals, trades, performance,
│                           # backtest, strategy_maker, settings, logs
├── utils/                  # logger, config, encryption, telegram, time utils
├── models/                 # cached HuggingFace models
├── logs/                   # bot.log, trades.jsonl, signals.jsonl
└── tests/test_smoke.py     # end-to-end smoke test with the mock client
```

---

## Quick start

### 1. Install

```bash
git clone https://github.com/Aayamz/Gold-scalper-mt5.git
cd Gold-scalper-mt5
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux / macOS:
source .venv/bin/activate

pip install -r requirements.txt
```

Copy and edit the env file:

```bash
cp .env.example .env       # then edit MT5_LOGIN, MT5_PASSWORD, MT5_SERVER
```

> The `MetaTrader5` package only installs on Windows. On other OSes the
> bot will automatically use the **mock client** so the UI / backtester
> are still fully exercisable.

### 2. Run

**Windows** — double-click `run.bat` and pick an option.

**Linux / macOS** — `./run.sh` and pick an option.

Or directly:

```bash
python main.py                 # trading loop only
python main.py --dashboard     # trading loop + Streamlit UI
python main.py --once          # one tick and exit (smoke test)
streamlit run dashboard/app.py # dashboard only
```

The dashboard opens at `http://localhost:8501`.

### 3. Smoke test (no MT5 required)

```bash
python -m tests.test_smoke
```

---

## Strategies

| Name | Mode | Description |
|---|---|---|
| `luxalgo_smc` | swing / scalp | Smart-Money-Concepts — OBs, FVGs, liquidity sweeps, BOS/CHoCH, premium/discount |
| `hf_scalping` | scalp | MA crossover with trend persistence fallback, no external model required |
| `ema_crossover` | scalp | 9/21 EMA crossover with trend persistence fallback |
| `bollinger_bounce` | scalp | BB mean reversion + momentum fallback, `min_confidence=45` |
| `rsi_stoch` | scalp | RSI + Stochastic crossover with momentum fallback, `min_rr=0.5` |
| `grid_scalper` | scalp | Grid trading for range-bound markets, range filter |
| `tick_scalper` | scalp | Volume spike detection + price momentum fallback |
| `macd_zero_line` | scalp | MACD zero-line cross + momentum fallback, `use_volume_filter=False` |

All strategies produce directional signals (LONG / SHORT) consistently on
mock data. Strategies without strong entry conditions use price-momentum
fallback so the bot always has a view.

### Strategy Maker

The **Strategy Maker** page (dashboard sidebar) has three tabs:
1. **Preset Models** — load XGBoost, LSTM, or ensemble models from the
   HuggingFace repo `JonusNattapong/xauusd-scalping-models`.
2. **Custom Model** — plug your own `.joblib` or `.pt` file.
3. **Browse HuggingFace** — search for models and download directly.

### Configuring strategies

Set the active strategy in `config/config.yaml`:

```yaml
strategy:
  active_strategy: hf_scalping   # or ema_crossover, rsi_stoch, etc.
```

---

## Configuration

All knobs live in [`config/config.yaml`](config/config.yaml):

| Section | What |
|---|---|
| `app` | symbol, log level, loop interval |
| `dashboard` | theme, default TF, lookback |
| `strategy` | active_strategy, HTF / LTF, swing length, OB / FVG / liquidity, sessions, min R:R |
| `tp_levels` | list of `{rr, close_pct}` — auto partial-close levels |
| `trailing_start_rr` | R:R threshold before trailing SL activates (default 1.0) |
| `risk` | risk %, daily loss limit, max DD, max concurrent, trailing, BE, max_lot_size |
| `backtest` | default symbol / TF / bars, commission, spread |

### Multi-TP example

```yaml
tp_levels:
  - rr: 1.0
    close_pct: 30    # close 30% at 1R
  - rr: 2.0
    close_pct: 30    # close 30% at 2R
  - rr: 3.0
    close_pct: 40    # close remaining 40% at 3R
```

The bot automatically executes partial closes at each level.

### Trading sessions (UTC)

Default in `config.yaml`:

* **London**  07:00–16:00
* **New York** 12:00–21:00
* **Asia**  00:00–08:00 (off by default)

Weekends are skipped automatically.

---

## Risk management

* **Position sizing** — `risk_amount = equity * risk_pct`, lots = risk /
  `(sl_distance / point * contract_size * point)`, rounded down to the
  volume step, bounded by `max_lot_size` (default 0.01 for $100 account).
* **Multi-TP auto-close** — partial closes executed automatically at each
  configured TP level; remaining lots tracked via Telegram notifications.
* **Daily loss limit** — the bot stops opening trades once realised P&L
  drops below `daily_loss_limit_pct` (default 4%).
* **Max drawdown** — emergency brake if equity drops by
  `max_drawdown_pct` from peak.
* **Max concurrent positions** — `max_concurrent_positions` (default 1).
* **Trailing stop** — ATR-based, activates after `trailing_start_rr` R:R,
  only ratchets in profit direction.
* **Breakeven move** — SL is moved to entry once R:R ≥ `break_even_after_rr`.
* **ATR fallback for SL** — when SL is missing, uses 1.5×ATR so TP / BE /
  trailing still operate.

---

## MT5 connection

The factory in `mt5_connector/factory.py` picks the right client:

* `TRADING_MODE=demo` (default) → tries the **real** client; falls back to
  the **mock** client if MT5 is unreachable or credentials are missing.
* `TRADING_MODE=mock` → always mock.

Set `TRADING_MODE` in `.env`. The dashboard shows the active mode in the
sidebar.

---

## Security

* MT5 credentials are stored in `credentials.enc` (Fernet / AES-128-CBC + HMAC).
  The encryption key lives in `ENCRYPTION_KEY` (auto-generated on first run
  if missing).
* `.env` and `credentials.enc` are git-ignored.
* `.env.example` documents the variables; never commit your real `.env`.

---

## Backtesting

Open the **Backtest** page in the dashboard, pick a timeframe and bar count,
click **Run backtest**. Results (metrics, equity curve, trade list) appear
inline and are appended to `logs/trades.jsonl` so the **Performance** page
also reflects them.

---

## Telegram alerts (optional)

Set in `.env`:

```
TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

The bot will send a short message for every signal, every fill, every
partial close, and every risk-pause event.

---

## Roadmap / extension points

* **News filter** — plug a ForexFactory / Investing.com scraper into
  `strategy/session_filter.py` and let `trading_allowed()` return False
  during high-impact events.
* **Multi-symbol** — extend `factory.py` and `data/fetcher.py` to handle a
  watchlist.
* **Walk-forward optimisation** — parameter sweep over rolling windows,
  results rendered on a new dashboard page.

---

## License

MIT — use, modify, trade responsibly. This software is provided as-is and
does not constitute financial advice.
