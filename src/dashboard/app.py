"""
src/dashboard/app.py
─────────────────────
AutoTrade Bot — Streamlit Dashboard

Sections:
  1. 📊 Portfolio Overview   — value, P&L, open positions
  2. 📡 Live Signals         — current signals for all symbols
  3. 🛡️ Risk Status          — circuit breaker, daily limits
  4. 📋 Trade History        — all closed trades with filters
  5. 📈 Performance Charts   — equity curve, win rate, P&L distribution
  6. ⚙️  Controls            — run cycle, refresh data

Run with:
    streamlit run src/dashboard/app.py
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.execution.paper_trader import PaperTrader, STOCK_WATCHLIST, CRYPTO_WATCHLIST
from src.execution.trade_logger import TradeLogger
from src.strategy.engine import StrategyEngine
from src.risk.manager import RiskManager
from src.data.fetcher import DataFetcher
from config.settings import settings

# ── Page config ───────────────────────────────────────────────────
from streamlit_autorefresh import st_autorefresh
st.set_page_config(
    page_title="AutoTrade Bot",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)
st_autorefresh(interval=10000, key="autorefresh")

# ── Custom CSS ────────────────────────────────────────────────────
st.markdown("""
<style>
    .metric-card {
        background: #1e1e2e;
        border-radius: 12px;
        padding: 16px;
        border: 1px solid #2e2e3e;
    }
    .signal-buy  { color: #00FF94; font-weight: bold; }
    .signal-sell { color: #FF5757; font-weight: bold; }
    .signal-hold { color: #FFB800; font-weight: bold; }
    .stMetric > div { background: #1e1e2e; border-radius: 8px; padding: 8px; }
    div[data-testid="stSidebar"] { background: #111118; }
</style>
""", unsafe_allow_html=True)

# ── Session state ─────────────────────────────────────────────────
if "trader" not in st.session_state:
    st.session_state.trader = PaperTrader(capital=100_000)
if "last_cycle" not in st.session_state:
    st.session_state.last_cycle = None
if "signals_df" not in st.session_state:
    st.session_state.signals_df = None

trader      = st.session_state.trader
trade_logger= TradeLogger()
engine      = StrategyEngine()

# ── Sidebar ───────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🤖 AutoTrade Bot")
    st.markdown(f"**Mode:** 🟡 PAPER TRADING")
    st.markdown(f"**Capital:** ₹{trader.capital:,.0f}")
    st.divider()

    st.markdown("### ⚙️ Controls")
    if st.button("▶️ Run Trading Cycle", use_container_width=True, type="primary"):
        with st.spinner("Running cycle..."):
            trader.run_cycle()
            st.session_state.last_cycle = datetime.now()
        st.success("Cycle complete!")
        st.rerun()

    if st.button("📡 Refresh Signals", use_container_width=True):
        with st.spinner("Scanning markets..."):
            engine2 = StrategyEngine()
            rows = []
            for sym in STOCK_WATCHLIST:
                sig = engine2.analyse(sym, timeframe="1d")
                rows.append({"symbol": sig.symbol, "action": sig.action.value,
                              "confidence": sig.confidence, "price": sig.price,
                              "reason": sig.reasons[0] if sig.reasons else ""})
            for sym in CRYPTO_WATCHLIST:
                sig = engine2.analyse(sym, timeframe="1h")
                rows.append({"symbol": sig.symbol, "action": sig.action.value,
                              "confidence": sig.confidence, "price": sig.price,
                              "reason": sig.reasons[0] if sig.reasons else ""})
            st.session_state.signals_df = pd.DataFrame(rows)
        st.success("Signals refreshed!")

    if st.button("🔄 Fetch Latest Data", use_container_width=True):
        with st.spinner("Fetching market data..."):
            fetcher = DataFetcher()
            fetcher.fetch_watchlist(stocks=STOCK_WATCHLIST, timeframe="1d", days=365)
            fetcher.fetch_watchlist(crypto=CRYPTO_WATCHLIST, timeframe="1h", days=60)
        st.success("Data updated!")

    st.divider()
    if st.session_state.last_cycle:
        st.caption(f"Last cycle: {st.session_state.last_cycle.strftime('%H:%M:%S')}")
    st.caption(f"App mode: {settings.mode.upper()}")

# ── Main header ───────────────────────────────────────────────────
st.title("📈 AutoTrade Bot Dashboard")
st.caption(f"Paper Trading · {datetime.now().strftime('%A, %d %B %Y %H:%M')}")

# ─────────────────────────────────────────────────────────────────
# SECTION 1: Portfolio Overview
# ─────────────────────────────────────────────────────────────────
st.header("💼 Portfolio Overview")

portfolio = trader.portfolio
summary   = portfolio.get_summary()
cb_report = trader.risk.breaker.get_status_report()

col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    st.metric("Portfolio Value", f"₹{summary['current_value']:,.0f}",
              f"{summary['total_pnl_pct']:+.2f}%")
with col2:
    st.metric("Cash Available", f"₹{summary['cash']:,.0f}")
with col3:
    pnl_color = "normal" if summary['total_pnl'] >= 0 else "inverse"
    st.metric("Total P&L", f"₹{summary['total_pnl']:+,.0f}",
              f"₹{summary['realized_pnl']:+,.0f} realized")
with col4:
    st.metric("Open Positions", summary['open_positions'],
              f"Max: {settings.risk.max_open_positions}")
with col5:
    cb_status = cb_report['status'].upper()
    cb_icon   = "🟢" if cb_status == "OK" else "🔴"
    st.metric("Circuit Breaker", f"{cb_icon} {cb_status}",
              f"Daily loss: {cb_report['daily_loss_pct']:.1f}%")

# Open positions table
if portfolio.positions:
    st.subheader("📂 Open Positions")
    pos_data = []
    for sym, pos in portfolio.positions.items():
        pos_data.append({
            "Symbol":    sym,
            "Side":      pos.side.upper(),
            "Qty":       pos.quantity,
            "Entry ₹":   f"₹{pos.entry_price:,.2f}",
            "Current ₹": f"₹{pos.current_price:,.2f}" if pos.current_price else "—",
            "Stop Loss":  f"₹{pos.stop_loss:,.2f}",
            "Take Profit":f"₹{pos.take_profit:,.2f}",
            "P&L":        f"₹{pos.unrealized_pnl:+,.2f}",
            "P&L %":     f"{pos.unrealized_pnl_pct:+.2f}%",
            "Strategy":  pos.strategy,
        })
    pos_df = pd.DataFrame(pos_data)
    st.dataframe(pos_df, use_container_width=True, hide_index=True)
else:
    st.info("No open positions — waiting for high-confidence signals")

st.divider()

# ─────────────────────────────────────────────────────────────────
# SECTION 2: Live Signals
# ─────────────────────────────────────────────────────────────────
st.header("📡 Live Signals")

if st.session_state.signals_df is not None:
    df = st.session_state.signals_df.copy()

    # Color code actions
    def color_action(val):
        if val == "BUY":  return "background-color: #003d1a; color: #00FF94"
        if val == "SELL": return "background-color: #3d0000; color: #FF5757"
        return "background-color: #2a2a1a; color: #FFB800"

    df["confidence"] = df["confidence"].apply(lambda x: f"{x:.0%}")
    df["price"]      = df["price"].apply(lambda x: f"₹{x:,.2f}")

    st.dataframe(
        df.style.map(color_action, subset=["action"]),
        use_container_width=True,
        hide_index=True,
    )

    # Signal distribution
    col1, col2 = st.columns(2)
    with col1:
        counts = st.session_state.signals_df["action"].value_counts()
        fig = px.pie(
            values=counts.values, names=counts.index,
            title="Signal Distribution",
            color=counts.index,
            color_discrete_map={"BUY": "#00FF94", "SELL": "#FF5757", "HOLD": "#FFB800"},
        )
        fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        conf_df = st.session_state.signals_df.copy()
        conf_df["color"] = conf_df["action"].map({"BUY": "#00FF94", "SELL": "#FF5757", "HOLD": "#FFB800"})
        fig2 = px.bar(
            conf_df, x="symbol", y="confidence",
            color="action",
            color_discrete_map={"BUY": "#00FF94", "SELL": "#FF5757", "HOLD": "#FFB800"},
            title="Signal Confidence by Symbol",
        )
        fig2.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig2, use_container_width=True)
else:
    st.info("Click **Refresh Signals** in the sidebar to load live market signals")

st.divider()

# ─────────────────────────────────────────────────────────────────
# SECTION 3: Risk Status
# ─────────────────────────────────────────────────────────────────
st.header("🛡️ Risk Status")

col1, col2, col3, col4 = st.columns(4)
with col1:
    daily_loss = cb_report["daily_loss_pct"]
    max_loss   = cb_report["max_daily_loss_pct"]
    pct_used   = (daily_loss / max_loss * 100) if max_loss > 0 else 0
    st.metric("Daily Loss", f"{daily_loss:.2f}%", f"Limit: {max_loss}%")
    st.progress(min(pct_used / 100, 1.0))
with col2:
    st.metric("Max Risk/Trade", f"{settings.risk.max_position_size_pct}%")
    st.metric("Max Positions",  f"{settings.risk.max_open_positions}")
with col3:
    st.metric("Trades Today",      cb_report["trades_today"])
    st.metric("Consecutive Losses",cb_report["consecutive_losses"])
with col4:
    st.metric("Realized P&L Today", f"₹{cb_report['realized_pnl_today']:+,.0f}")
    win_today = cb_report.get("win_rate_today", 0)
    st.metric("Win Rate Today", f"{win_today:.0f}%")

st.divider()

# ─────────────────────────────────────────────────────────────────
# SECTION 4: Trade History
# ─────────────────────────────────────────────────────────────────
st.header("📋 Trade History")

all_trades = trade_logger.get_all_trades()
stats      = trade_logger.get_stats()

if not all_trades.empty:
    # Stats row
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1: st.metric("Total Trades",  stats.get("total_trades", 0))
    with col2: st.metric("Win Rate",      f"{stats.get('win_rate_pct', 0):.1f}%")
    with col3: st.metric("Total P&L",     f"₹{stats.get('total_pnl', 0):+,.0f}")
    with col4: st.metric("Avg Win",       f"₹{stats.get('avg_win', 0):+,.0f}")
    with col5: st.metric("Avg Loss",      f"₹{stats.get('avg_loss', 0):+,.0f}")

    # Filters
    col1, col2 = st.columns(2)
    with col1:
        symbols   = ["All"] + sorted(all_trades["symbol"].unique().tolist())
        sel_sym   = st.selectbox("Filter by symbol", symbols)
    with col2:
        outcomes  = ["All", "Winners", "Losers"]
        sel_out   = st.selectbox("Filter by outcome", outcomes)

    display = all_trades.copy()
    if sel_sym != "All":
        display = display[display["symbol"] == sel_sym]
    if sel_out == "Winners":
        display = display[display["winner"] == True]
    elif sel_out == "Losers":
        display = display[display["winner"] == False]

    # Format for display
    display["pnl"]     = display["pnl"].apply(lambda x: f"₹{x:+,.2f}")
    display["pnl_pct"] = display["pnl_pct"].apply(lambda x: f"{x:+.2f}%")
    display["entry"]   = display["entry"].apply(lambda x: f"₹{x:,.2f}")
    display["exit"]    = display["exit"].apply(lambda x: f"₹{x:,.2f}")
    display["winner"]  = display["winner"].apply(lambda x: "✅" if x else "❌")

    st.dataframe(
        display[["symbol","side","quantity","entry","exit","pnl","pnl_pct","winner","strategy","exit_reason","closed_at"]],
        use_container_width=True, hide_index=True,
    )
else:
    st.info("No closed trades yet — trades will appear here after stop loss or take profit is hit")

st.divider()

# ─────────────────────────────────────────────────────────────────
# SECTION 5: Performance Charts
# ─────────────────────────────────────────────────────────────────
st.header("📈 Performance Charts")

raw_trades = trade_logger.get_all_trades()

if not raw_trades.empty and len(raw_trades) > 0:
    col1, col2 = st.columns(2)

    with col1:
        # Equity curve
        raw_trades_sorted = raw_trades.sort_values("closed_at")
        raw_trades_sorted["cumulative_pnl"] = raw_trades_sorted["pnl"].cumsum()
        raw_trades_sorted["equity"] = 100_000 + raw_trades_sorted["cumulative_pnl"]

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=raw_trades_sorted["closed_at"],
            y=raw_trades_sorted["equity"],
            mode="lines+markers",
            line=dict(color="#00FF94", width=2),
            fill="tozeroy",
            fillcolor="rgba(0,255,148,0.1)",
            name="Portfolio Value",
        ))
        fig.add_hline(y=100_000, line_dash="dash", line_color="#666", annotation_text="Starting Capital")
        fig.update_layout(
            title="📈 Equity Curve",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="white"),
            xaxis=dict(gridcolor="#2e2e3e"),
            yaxis=dict(gridcolor="#2e2e3e", tickprefix="₹"),
        )
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        # P&L distribution
        fig2 = px.histogram(
            raw_trades, x="pnl", nbins=20,
            color="winner",
            color_discrete_map={True: "#00FF94", False: "#FF5757"},
            title="P&L Distribution",
            labels={"pnl": "P&L (₹)", "winner": "Winner"},
        )
        fig2.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="white"),
        )
        st.plotly_chart(fig2, use_container_width=True)

    col3, col4 = st.columns(2)
    with col3:
        # Win/loss by symbol
        symbol_stats = raw_trades.groupby("symbol").agg(
            trades=("pnl", "count"),
            total_pnl=("pnl", "sum"),
            win_rate=("winner", "mean"),
        ).reset_index()
        symbol_stats["win_rate"] = (symbol_stats["win_rate"] * 100).round(1)

        fig3 = px.bar(
            symbol_stats, x="symbol", y="total_pnl",
            color="total_pnl",
            color_continuous_scale=["#FF5757", "#FFB800", "#00FF94"],
            title="P&L by Symbol",
        )
        fig3.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color="white"))
        st.plotly_chart(fig3, use_container_width=True)

    with col4:
        # Exit reason breakdown
        exit_counts = raw_trades["exit_reason"].value_counts().reset_index()
        exit_counts.columns = ["reason", "count"]
        fig4 = px.pie(
            exit_counts, values="count", names="reason",
            title="Exit Reasons",
            color_discrete_sequence=["#00FF94", "#FF5757", "#FFB800", "#00C2FF"],
        )
        fig4.update_layout(paper_bgcolor="rgba(0,0,0,0)", font=dict(color="white"))
        st.plotly_chart(fig4, use_container_width=True)
else:
    st.info("Charts will appear here once you have closed trades — run a few cycles!")

# ── Footer ────────────────────────────────────────────────────────
st.divider()
st.caption("AutoTrade Bot · Paper Trading Mode · No real money at risk · Built with ❤️")
