# 🟡 XAUUSD SMC Trading Bot

A professional Forex auto-trading bot focused on **XAUUSD (Gold)** with a
Streamlit dashboard, MetaTrader 5 integration, and a Smart-Money-Concepts
strategy inspired by **LuxAlgo**.

> **Status:** working core — MT5 connector (real + mock), SMC strategy,
> risk manager, backtester, and full dashboard. Ready for demo / paper trading
> immediately; tune strategy parameters via `config/config.yaml` before going
> live.

---

## Highlights

* **Streamlit dashboard** with a beautiful Plotly chart annotated with
  Order Blocks, Fair Value Gaps, Liquidity levels, BOS/CHoCH, and the
  premium/discount equilibrium.
* **LuxAlgo-inspired SMC strategy** — multi-timeframe bias, mitigated
  order blocks, FVG confluence, liquidity sweeps, premium/discount filter,
  session awareness, min R:R filter.
* **Strict risk management** — dynamic position sizing, daily loss limit,
  max drawdown protection, trailing stop, breakeven, partial take-profit.
* **MT5 integration** via the official `MetaTrader5` Python package with
  automatic fallback to a **mock client** so the dashboard, backtester and
  strategy are testable without an MT5 terminal.
* **Backtester** — event-driven engine with SL/TP intrabar checks, commission
  and spread.
* **Encrypted credentials** at rest (Fernet) and safe `.env`-based config.
* **Telegram alerts** for signals, executions, and risk breaches (optional).

---

## Project layout

```
xauusd-bot/
├── main.py                # entry point (trading loop + optional dashboard)
├── run.bat / run.sh       # one-click launchers with a menu
├── requirements.txt
├── .env.example           # MT5 + Telegram + encryption key
├── config/
│   └── config.yaml        # strategy + risk + dashboard config
├── mt5_connector/         # real + mock MT5 client, factory
├── data/                  # fetcher, indicator helpers
├── strategy/              # SMC components (OB, FVG, liquidity, …) + main
├── risk_manager/          # position sizing, limits, trade management
├── backtester/            # event-driven backtest engine
├── dashboard/             # Streamlit multi-page app
│   ├── app.py
│   ├── components/        # chart, metrics, signal panel, trade controls
│   └── pages/             # home, live_chart, signals, trades, performance,
│                          # backtest, settings, logs
├── utils/                 # logger, config, encryption, telegram, time utils
├── logs/                  # bot.log, trades.jsonl, signals.jsonl
└── tests/test_smoke.py    # end-to-end smoke test with the mock client
```

---

## Quick start

### 1. Install

```bash
git clone <your-repo> xauusd-bot
cd xauusd-bot
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

or

```bash
python tests/test_smoke.py
```

---

## Configuration

All knobs live in [`config/config.yaml`](config/config.yaml):

| Section | What |
|---|---|
| `app` | symbol, log level, loop interval |
| `dashboard` | theme, default TF, lookback |
| `strategy` | HTF / LTF, swing length, OB / FVG / liquidity params, sessions, min R:R |
| `risk` | risk %, daily loss limit, max DD, max concurrent, trailing, BE, partial TP |
| `backtest` | default symbol / TF / bars, commission, spread |

The **Settings** page in the dashboard lets you edit `config.yaml` from the
browser (with validation) and save MT5 credentials (encrypted to
`credentials.enc`).

### Trading sessions (UTC)

Default in `config.yaml`:

* **London**  07:00–16:00
* **New York** 12:00–21:00
* **Asia**  00:00–08:00 (off by default)

Weekends are skipped automatically.

---

## Strategy — how a trade is generated

A trade is only placed when **all** of these align:

1. **HTF bias** is BULL or BEAR (no trades in NEUTRAL).
2. An **Order Block** is mitigated in the direction of the bias.
3. **Premium / discount** filter agrees (longs in discount, shorts in premium).
4. (Optional, +confidence) **Fair Value Gap** is in the path of price.
5. (Optional, +confidence) **Liquidity** has been swept (stop hunt).
6. **Min R:R** ≥ `strategy.min_rr` (default 2.0).
7. We're inside an **enabled session** and not on a weekend.
8. **Risk limits** allow new positions.

The result is a `Signal` carrying direction, entry, SL, TP, R:R, and a
human-readable list of reasons — which is what the **Signals** page displays.

---

## Risk management

* **Position sizing** — `risk_amount = equity * risk_pct`, lots = risk /
  `(sl_distance / point * contract_size * point)`, rounded down to the
  volume step, bounded by `max_lot_size`.
* **Daily loss limit** — the bot stops opening trades once realised P&L
  drops below `daily_loss_limit_pct` (default 4%).
* **Max drawdown** — emergency brake if equity drops by
  `max_drawdown_pct` from peak.
* **Max concurrent positions** — `max_concurrent_positions` (default 1).
* **Trailing stop** — ATR-based, only ratchets in profit direction.
* **Breakeven move** — SL is moved to entry once R:R ≥ `break_even_after_rr`.
* **Partial TP** — sets a flag when R:R ≥ `partial_tp_rr`; close 50% manually
  from the **Trades** page (full automation is a small extension).

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

The bot will send a short message for every signal, every fill, and every
risk-pause event.

---

## Roadmap / extension points

* **News filter** — plug a ForexFactory / Investing.com scraper into
  `strategy/session_filter.py` and let `trading_allowed()` return False
  during high-impact events.
* **Full partial TP automation** — wire `ManageAction.partial_closed` into
  `client.place_order` with reduced volume.
* **Multi-symbol** — extend `factory.py` and `data/fetcher.py` to handle a
  watchlist.
* **Walk-forward optimisation** — parameter sweep over rolling windows,
  results rendered on a new dashboard page.

---

## License

MIT — use, modify, trade responsibly. This software is provided as-is and
does not constitute financial advice.
