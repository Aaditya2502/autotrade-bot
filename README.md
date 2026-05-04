# AutoTrade Bot 📈

A production-grade automated trading system built in Python. Analyses NSE/BSE stocks and crypto using technical indicators, generates buy/sell signals, manages risk automatically, and executes trades — starting in paper (simulated) mode before going live.

![Python](https://img.shields.io/badge/Python-3.12-blue) ![Tests](https://img.shields.io/badge/tests-68%20passing-brightgreen) ![Mode](https://img.shields.io/badge/mode-paper%20trading-yellow)

---

## What it does

Every hour, the bot:
1. Fetches live prices for 5 NSE stocks + 4 crypto pairs
2. Runs 3 technical strategies on each symbol
3. Combines signals into a confidence-weighted consensus
4. Gates every trade through a risk manager (position sizing, stop loss, circuit breaker)
5. Executes approved trades in a simulated paper portfolio
6. Updates a live Streamlit dashboard with P&L, charts, and trade history

---

## Dashboard

The bot ships with a full Streamlit web dashboard showing live signals, open positions, equity curve, trade history, and risk status — auto-refreshing every 10 seconds.

```
streamlit run src/dashboard/app.py
```

---

## Tech Stack

| Layer | Tools |
|---|---|
| Language | Python 3.12 |
| Market data (stocks) | yfinance (free, no account needed) |
| Market data (crypto) | Binance API |
| Live trading (stocks) | Zerodha Kite API (Phase 7) |
| Technical indicators | pandas-ta (RSI, MACD, EMA, Bollinger Bands, ATR) |
| Backtesting | Backtrader |
| Database | SQLite via SQLAlchemy |
| Scheduler | APScheduler |
| Dashboard | Streamlit + Plotly |
| Alerts | Telegram Bot API |
| Testing | pytest (68 tests) |

---

## Project Structure

```
autotrade/
├── src/
│   ├── data/           # Market data fetchers + database
│   ├── strategy/       # 3 trading strategies + indicator engine
│   ├── risk/           # Position sizing, stop loss, circuit breaker
│   ├── execution/      # Paper portfolio + trade logger
│   ├── dashboard/      # Streamlit web UI
│   ├── alerts/         # Telegram notifications
│   └── utils/          # Logger
├── tests/              # 68 tests across all modules
├── config/             # Settings loaded from .env
├── run_paper_trader.py # Main entry point
├── run_pipeline.py     # Populate database with market data
└── run_strategy.py     # Run strategy engine and see signals
```

---

## Strategies

**1. EMA Crossover** — Golden cross (EMA20 > EMA50) signals uptrend, death cross signals downtrend. Boosted by volume confirmation, RSI, and MACD agreement.

**2. RSI + MACD Confluence** — Requires both RSI oversold/overbought AND MACD crossover to agree before generating a signal. Reduces false signals significantly.

**3. Bollinger Bands** — Mean reversion when price touches bands. Switches to breakout mode during a BB squeeze (bands narrowing = big move incoming).

All three strategies vote on each symbol. The consensus engine combines their confidence scores — when all three agree, confidence is highest.

---

## Risk Management

- **Position sizing** — Fixed-fractional method. Never risks more than 2% of capital on a single trade
- **Stop loss** — Fixed, ATR-based, or trailing stop loss per position
- **Circuit breaker** — Halts all trading if daily loss exceeds 3% or after 3 consecutive losses
- **Exposure limits** — Max 5 open positions, max 60% of capital deployed at once

---

## Quick Start

```bash
# 1. Clone and set up
git clone https://github.com/yourusername/autotrade-bot.git
cd autotrade-bot

# 2. Create virtual environment (Python 3.12 required)
py -3.12 -m venv venv
venv\Scripts\activate          # Windows
source venv/bin/activate        # Mac/Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure
cp .env.example .env
# Edit .env — Binance API keys required, Zerodha optional for paper trading

# 5. Populate database with market data
python run_pipeline.py

# 6. Run tests
python -m pytest tests/ -v

# 7. Start paper trading
python run_paper_trader.py --once    # Single cycle
python run_paper_trader.py           # Continuous (every 60 min)

# 8. Launch dashboard
streamlit run src/dashboard/app.py
```

---

## API Keys Needed

| Service | Purpose | Cost |
|---|---|---|
| Binance | Crypto data + execution | Free |
| Zerodha Kite | NSE/BSE data + execution | Paid (Phase 7 only) |
| Telegram | Trade alerts | Free |

For paper trading, only Binance is needed. Zerodha is required only when going live with real money.

---

## Build Phases

| Phase | Status | What was built |
|---|---|---|
| 1 — Environment | ✅ | Python setup, API registration, config system |
| 2 — Data pipeline | ✅ | Market data fetchers, SQLite DB, auto-scheduler |
| 3 — Strategy engine | ✅ | 3 strategies, indicator calculator, backtesting |
| 4 — Risk management | ✅ | Position sizing, stop loss, circuit breaker |
| 5 — Paper trading | ✅ | Virtual portfolio, trade lifecycle, persistence |
| 6 — Dashboard | ✅ | Streamlit UI, Plotly charts, Telegram alerts |
| 7 — Live trading | 🔲 | Real order execution via Zerodha Kite API |

---

## Disclaimer

This project is for educational purposes. Past performance of any strategy does not guarantee future results. Always paper trade for several weeks before risking real money. Never invest more than you can afford to lose.

---

Built with Python · Tested on Windows 10/11
