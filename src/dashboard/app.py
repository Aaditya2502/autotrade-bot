"""
src/dashboard/app.py
─────────────────────
AutoTrade Bot — Fully Automatic Dashboard

Two background loops run automatically:
  Crypto : fetches 15m candles + trades every 5 minutes
  Stocks : fetches 1d candles  + trades every 15 minutes
  UI     : auto-refreshes every 10 seconds
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime
import threading
import time
import sys, os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.execution.paper_trader import PaperTrader, STOCK_WATCHLIST, CRYPTO_WATCHLIST
from src.execution.trade_logger import TradeLogger
from src.strategy.engine import StrategyEngine
from src.data.fetcher import DataFetcher
from config.settings import settings

# ── Page config ───────────────────────────────────────────────────
st.set_page_config(
    page_title="AutoTrade Bot",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

try:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=10_000, key="autorefresh")
except ImportError:
    pass

# ── Background loops ──────────────────────────────────────────────

def _crypto_loop(trader: PaperTrader):
    """Fetch crypto 15m data + run crypto cycle every 5 minutes."""
    fetcher = DataFetcher()
    while True:
        try:
            fetcher.fetch_watchlist(crypto=CRYPTO_WATCHLIST, timeframe="15m", days=7)
            trader.run_crypto_cycle()
            st.session_state["last_crypto"] = datetime.now()
        except Exception as e:
            st.session_state["crypto_error"] = str(e)
        time.sleep(5 * 60)   # 5 minutes


def _stock_loop(trader: PaperTrader):
    """Fetch stock 1d data + run stock cycle every 15 minutes."""
    fetcher = DataFetcher()
    while True:
        try:
            fetcher.fetch_watchlist(stocks=STOCK_WATCHLIST, timeframe="1d", days=365)
            trader.run_stock_cycle()
            st.session_state["last_stock"] = datetime.now()
            _refresh_signals()
        except Exception as e:
            st.session_state["stock_error"] = str(e)
        time.sleep(15 * 60)  # 15 minutes


def _startup(trader: PaperTrader):
    """On first launch: fetch everything + run both cycles once."""
    fetcher = DataFetcher()
    try:
        st.session_state["startup_msg"] = "Fetching stock data..."
        fetcher.fetch_watchlist(stocks=STOCK_WATCHLIST, timeframe="1d", days=365)

        st.session_state["startup_msg"] = "Fetching crypto data..."
        fetcher.fetch_watchlist(crypto=CRYPTO_WATCHLIST, timeframe="15m", days=7)

        st.session_state["startup_msg"] = "Running first stock cycle..."
        trader.run_stock_cycle()

        st.session_state["startup_msg"] = "Running first crypto cycle..."
        trader.run_crypto_cycle()

        st.session_state["startup_msg"] = "done"
        st.session_state["last_stock"]  = datetime.now()
        st.session_state["last_crypto"] = datetime.now()
        _refresh_signals()
    except Exception as e:
        st.session_state["startup_msg"] = f"error: {e}"


def _refresh_signals():
    try:
        engine = StrategyEngine()
        rows = []
        for sym in STOCK_WATCHLIST:
            sig = engine.analyse(sym, timeframe="1d")
            rows.append({"symbol": sig.symbol, "action": sig.action.value,
                         "confidence": sig.confidence, "price": sig.price,
                         "stop_loss": sig.stop_loss, "take_profit": sig.take_profit,
                         "reason": sig.reasons[0] if sig.reasons else ""})
        for sym in CRYPTO_WATCHLIST:
            sig = engine.analyse(sym, timeframe="15m")
            rows.append({"symbol": sig.symbol, "action": sig.action.value,
                         "confidence": sig.confidence, "price": sig.price,
                         "stop_loss": sig.stop_loss, "take_profit": sig.take_profit,
                         "reason": sig.reasons[0] if sig.reasons else ""})
        st.session_state["signals_df"] = pd.DataFrame(rows)
    except Exception as e:
        st.session_state["signals_error"] = str(e)


# ── Session state ─────────────────────────────────────────────────
if "trader" not in st.session_state:
    st.session_state["trader"]       = PaperTrader(capital=100_000)
    st.session_state["signals_df"]   = None
    st.session_state["startup_msg"]  = "starting"
    st.session_state["last_stock"]   = None
    st.session_state["last_crypto"]  = None

    threading.Thread(target=_startup,
                     args=(st.session_state["trader"],), daemon=True).start()
    threading.Thread(target=_stock_loop,
                     args=(st.session_state["trader"],), daemon=True).start()
    threading.Thread(target=_crypto_loop,
                     args=(st.session_state["trader"],), daemon=True).start()

trader       = st.session_state["trader"]
trade_logger = TradeLogger()

# ── Sidebar ───────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🤖 AutoTrade Bot")
    st.markdown("**Mode:** 🟡 PAPER")
    st.markdown(f"**Capital:** ₹{trader.capital:,.0f}")
    st.divider()

    msg = st.session_state.get("startup_msg", "starting")
    if msg == "done":
        st.success("✅ Bot running automatically")
    elif msg.startswith("error"):
        st.error(msg)
    else:
        st.info(f"⏳ {msg}")

    last_s = st.session_state.get("last_stock")
    last_c = st.session_state.get("last_crypto")
    if last_s: st.caption(f"📊 Stocks last run: {last_s.strftime('%H:%M:%S')} (every 15 min)")
    if last_c: st.caption(f"🪙  Crypto last run: {last_c.strftime('%H:%M:%S')} (every 5 min)")

    st.divider()
    st.markdown("### Manual controls")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("📊 Run stocks", use_container_width=True):
            with st.spinner("Running..."):
                try:
                    DataFetcher().fetch_watchlist(stocks=STOCK_WATCHLIST, timeframe="1d", days=365)
                    trader.run_stock_cycle()
                    _refresh_signals()
                    st.session_state["last_stock"] = datetime.now()
                except Exception as e:
                    st.error(str(e))
            st.rerun()
    with col2:
        if st.button("🪙 Run crypto", use_container_width=True):
            with st.spinner("Running..."):
                try:
                    DataFetcher().fetch_watchlist(crypto=CRYPTO_WATCHLIST, timeframe="15m", days=7)
                    trader.run_crypto_cycle()
                    st.session_state["last_crypto"] = datetime.now()
                except Exception as e:
                    st.error(str(e))
            st.rerun()

# ── Header ────────────────────────────────────────────────────────
st.title("📈 AutoTrade Bot")
st.caption(
    f"📊 Stocks: every 15 min  ·  🪙 Crypto: every 5 min  ·  "
    f"🔄 UI: every 10 sec  ·  {datetime.now().strftime('%d %b %Y %H:%M:%S')}"
)

# ── Section 1: Portfolio ──────────────────────────────────────────
st.header("💼 Portfolio")

summary  = trader.portfolio.get_summary()
cb       = trader.risk.breaker.get_status_report()

col1, col2, col3, col4, col5 = st.columns(5)
with col1: st.metric("Value",    f"₹{summary['current_value']:,.0f}", f"{summary['total_pnl_pct']:+.2f}%")
with col2: st.metric("Cash",     f"₹{summary['cash']:,.0f}")
with col3: st.metric("P&L",      f"₹{summary['total_pnl']:+,.0f}", f"₹{summary['realized_pnl']:+,.0f} realized")
with col4: st.metric("Positions",summary['open_positions'], f"Max: {settings.risk.max_open_positions}")
with col5:
    icon = "🟢" if cb['status'] == "ok" else "🔴"
    st.metric("Circuit", f"{icon} {cb['status'].upper()}", f"Loss: {cb['daily_loss_pct']:.1f}%")

if trader.portfolio.positions:
    st.subheader("📂 Open Positions")
    rows = []
    for sym, pos in trader.portfolio.positions.items():
        market = "🪙" if sym.endswith("USDT") else "📊"
        rows.append({
            "":       market,
            "Symbol": sym,
            "Side":   pos.side.upper(),
            "Qty":    pos.quantity,
            "Entry":  f"₹{pos.entry_price:,.2f}",
            "Current":f"₹{pos.current_price:,.2f}" if pos.current_price else "—",
            "SL":     f"₹{pos.stop_loss:,.2f}",
            "TP":     f"₹{pos.take_profit:,.2f}",
            "P&L":    f"₹{pos.unrealized_pnl:+,.2f}",
            "P&L %":  f"{pos.unrealized_pnl_pct:+.2f}%",
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
else:
    st.info("No open positions — bot scanning every 5-15 min for signals above 40% confidence")

st.divider()

# ── Section 2: Live Signals ───────────────────────────────────────
st.header("📡 Live Signals")

if st.session_state.get("startup_msg") != "done" and st.session_state["signals_df"] is None:
    st.info("⏳ Starting up — signals will appear shortly...")
elif st.session_state["signals_df"] is not None:
    df = st.session_state["signals_df"].copy()

    def color_action(val):
        if val == "BUY":  return "background-color: #003d1a; color: #00FF94"
        if val == "SELL": return "background-color: #3d0000; color: #FF5757"
        return "background-color: #2a2a1a; color: #FFB800"

    disp = df.copy()
    disp["market"]     = disp["symbol"].apply(lambda s: "🪙 Crypto" if s.endswith("USDT") else "📊 Stock")
    disp["confidence"] = disp["confidence"].apply(lambda x: f"{x:.0%}")
    disp["price"]      = disp["price"].apply(lambda x: f"₹{x:,.2f}")
    disp["stop_loss"]  = disp["stop_loss"].apply(lambda x: f"₹{x:,.2f}" if x else "—")
    disp["take_profit"]= disp["take_profit"].apply(lambda x: f"₹{x:,.2f}" if x else "—")

    st.dataframe(
        disp[["market","symbol","action","confidence","price","stop_loss","take_profit","reason"]]
        .style.map(color_action, subset=["action"]),
        use_container_width=True, hide_index=True,
    )

    col1, col2 = st.columns(2)
    with col1:
        counts = df["action"].value_counts()
        fig = px.pie(values=counts.values, names=counts.index, title="Signal Distribution",
                     color=counts.index,
                     color_discrete_map={"BUY":"#00FF94","SELL":"#FF5757","HOLD":"#FFB800"})
        fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, use_container_width=True)
    with col2:
        fig2 = px.bar(df, x="symbol", y="confidence", color="action",
                      color_discrete_map={"BUY":"#00FF94","SELL":"#FF5757","HOLD":"#FFB800"},
                      title="Confidence by Symbol")
        fig2.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig2, use_container_width=True)
else:
    st.info("Signals loading...")

st.divider()

# ── Section 3: Risk ───────────────────────────────────────────────
st.header("🛡️ Risk Status")

col1, col2, col3, col4 = st.columns(4)
with col1:
    daily_loss = cb["daily_loss_pct"]
    max_loss   = cb["max_daily_loss_pct"]
    st.metric("Daily Loss", f"{daily_loss:.2f}%", f"Limit: {max_loss}%")
    st.progress(min(abs(daily_loss) / max_loss, 1.0) if max_loss > 0 else 0.0)
with col2:
    st.metric("Max Risk/Trade", f"{settings.risk.max_position_size_pct}%")
    st.metric("Max Positions",  f"{settings.risk.max_open_positions}")
with col3:
    st.metric("Trades Today",       cb["trades_today"])
    st.metric("Consecutive Losses", cb["consecutive_losses"])
with col4:
    st.metric("P&L Today", f"₹{cb['realized_pnl_today']:+,.0f}")
    st.metric("Win Rate",  f"{cb.get('win_rate_today', 0):.0f}%")

st.divider()

# ── Section 4: Trade History ──────────────────────────────────────
st.header("📋 Trade History")

all_trades = trade_logger.get_all_trades()
stats      = trade_logger.get_stats()

if not all_trades.empty:
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1: st.metric("Total Trades", stats.get("total_trades", 0))
    with col2: st.metric("Win Rate",     f"{stats.get('win_rate_pct', 0):.1f}%")
    with col3: st.metric("Total P&L",    f"₹{stats.get('total_pnl', 0):+,.0f}")
    with col4: st.metric("Avg Win",      f"₹{stats.get('avg_win', 0):+,.0f}")
    with col5: st.metric("Avg Loss",     f"₹{stats.get('avg_loss', 0):+,.0f}")

    col1, col2 = st.columns(2)
    with col1:
        syms = ["All"] + sorted(all_trades["symbol"].unique().tolist())
        sel_sym = st.selectbox("Symbol", syms)
    with col2:
        sel_out = st.selectbox("Outcome", ["All","Winners","Losers"])

    disp = all_trades.copy()
    if sel_sym != "All":      disp = disp[disp["symbol"] == sel_sym]
    if sel_out == "Winners":  disp = disp[disp["winner"] == True]
    elif sel_out == "Losers": disp = disp[disp["winner"] == False]

    disp["pnl"]     = disp["pnl"].apply(lambda x: f"₹{x:+,.2f}")
    disp["pnl_pct"] = disp["pnl_pct"].apply(lambda x: f"{x:+.2f}%")
    disp["entry"]   = disp["entry"].apply(lambda x: f"₹{x:,.2f}")
    disp["exit"]    = disp["exit"].apply(lambda x: f"₹{x:,.2f}")
    disp["winner"]  = disp["winner"].apply(lambda x: "✅" if x else "❌")

    st.dataframe(
        disp[["symbol","side","quantity","entry","exit","pnl","pnl_pct",
              "winner","strategy","exit_reason","closed_at"]],
        use_container_width=True, hide_index=True,
    )
else:
    st.info("No closed trades yet — first trades will appear here once SL or TP is hit")

st.divider()

# ── Section 5: Charts ─────────────────────────────────────────────
st.header("📈 Performance Charts")

raw = trade_logger.get_all_trades()
if not raw.empty:
    col1, col2 = st.columns(2)
    with col1:
        srt = raw.sort_values("closed_at")
        srt["equity"] = 100_000 + srt["pnl"].cumsum()
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=srt["closed_at"], y=srt["equity"],
            mode="lines+markers", line=dict(color="#00FF94", width=2),
            fill="tozeroy", fillcolor="rgba(0,255,148,0.1)",
        ))
        fig.add_hline(y=100_000, line_dash="dash", line_color="#666",
                      annotation_text="Starting Capital")
        fig.update_layout(title="Equity Curve",
                          paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          font=dict(color="white"),
                          xaxis=dict(gridcolor="#2e2e3e"),
                          yaxis=dict(gridcolor="#2e2e3e", tickprefix="₹"))
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        fig2 = px.histogram(raw, x="pnl", nbins=20, color="winner",
                            color_discrete_map={True:"#00FF94", False:"#FF5757"},
                            title="P&L Distribution")
        fig2.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                           font=dict(color="white"))
        st.plotly_chart(fig2, use_container_width=True)

    col3, col4 = st.columns(2)
    with col3:
        sym_s = raw.groupby("symbol").agg(total_pnl=("pnl","sum")).reset_index()
        fig3 = px.bar(sym_s, x="symbol", y="total_pnl", color="total_pnl",
                      color_continuous_scale=["#FF5757","#FFB800","#00FF94"],
                      title="P&L by Symbol")
        fig3.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                           font=dict(color="white"))
        st.plotly_chart(fig3, use_container_width=True)
    with col4:
        ec = raw["exit_reason"].value_counts().reset_index()
        ec.columns = ["reason","count"]
        fig4 = px.pie(ec, values="count", names="reason", title="Exit Reasons",
                      color_discrete_sequence=["#00FF94","#FF5757","#FFB800","#00C2FF"])
        fig4.update_layout(paper_bgcolor="rgba(0,0,0,0)", font=dict(color="white"))
        st.plotly_chart(fig4, use_container_width=True)
else:
    st.info("Charts appear after first closed trades")

st.divider()
st.caption("AutoTrade Bot · Paper Trading · No real money at risk · 📊 Stocks every 15 min · 🪙 Crypto every 5 min")
