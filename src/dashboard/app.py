"""
src/dashboard/app.py  —  AutoTrade Bot Dashboard  (Phase 6 redesign)
Trading-terminal aesthetic: dark, sharp, professional.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime
import threading, time, sys, os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.execution.paper_trader  import PaperTrader, STOCK_WATCHLIST, CRYPTO_WATCHLIST
from src.execution.trade_logger  import TradeLogger
from src.strategy.engine         import StrategyEngine
from src.data.fetcher            import DataFetcher
from config.settings             import settings

# ── Page ──────────────────────────────────────────────────────────
st.set_page_config(page_title="AutoTrade", page_icon="📈",
                   layout="wide", initial_sidebar_state="collapsed")

try:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=60_000, key="ar")
except ImportError:
    pass

# ── Global CSS ────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=DM+Sans:wght@300;400;500;600&display=swap');

:root {
  --bg:      #070b12;
  --bg2:     #0d1420;
  --bg3:     #111c2e;
  --border:  #1e2d42;
  --green:   #00ff88;
  --red:     #ff3d5a;
  --yellow:  #ffc542;
  --blue:    #3d8eff;
  --text:    #e2eaf5;
  --muted:   #4e6585;
  --mono:    'Space Mono', monospace;
  --sans:    'DM Sans', sans-serif;
}

html, body, [class*="css"] {
  background-color: var(--bg) !important;
  color: var(--text) !important;
  font-family: var(--sans) !important;
}

/* Hide streamlit chrome */
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding: 1.5rem 2rem !important; max-width: 100% !important; }
[data-testid="stSidebar"] { background: var(--bg2) !important; border-right: 1px solid var(--border); }

/* Metric cards */
[data-testid="metric-container"] {
  background: var(--bg2) !important;
  border: 1px solid var(--border) !important;
  border-radius: 10px !important;
  padding: 14px 18px !important;
}
[data-testid="stMetricLabel"]  { color: var(--muted) !important; font-size: 11px !important; letter-spacing: .08em; text-transform: uppercase; }
[data-testid="stMetricValue"]  { color: var(--text)  !important; font-family: var(--mono) !important; font-size: 22px !important; }
[data-testid="stMetricDelta"]  { font-family: var(--mono) !important; font-size: 12px !important; }

/* Dataframe */
[data-testid="stDataFrame"] { border: 1px solid var(--border) !important; border-radius: 10px !important; overflow: hidden; }
.dvn-scroller { background: var(--bg2) !important; }

/* Buttons */
.stButton > button {
  background: transparent !important;
  border: 1px solid var(--border) !important;
  color: var(--text) !important;
  border-radius: 8px !important;
  font-family: var(--sans) !important;
  font-size: 13px !important;
  padding: 6px 14px !important;
  transition: all .15s !important;
}
.stButton > button:hover {
  border-color: var(--blue) !important;
  color: var(--blue) !important;
  background: rgba(61,142,255,.07) !important;
}
.stButton > button[kind="primary"] {
  background: var(--green) !important;
  color: #000 !important;
  border-color: var(--green) !important;
  font-weight: 600 !important;
}

/* Selectbox */
[data-testid="stSelectbox"] > div > div {
  background: var(--bg2) !important;
  border: 1px solid var(--border) !important;
  border-radius: 8px !important;
  color: var(--text) !important;
}

/* Divider */
hr { border-color: var(--border) !important; margin: 1.5rem 0 !important; }

/* Progress bar */
.stProgress > div > div { background: var(--bg3) !important; border-radius: 4px !important; }
.stProgress > div > div > div { background: var(--green) !important; border-radius: 4px !important; }

/* Tabs */
.stTabs [data-baseweb="tab-list"] { background: var(--bg2) !important; border-radius: 10px !important; padding: 4px !important; border: 1px solid var(--border) !important; gap: 4px; }
.stTabs [data-baseweb="tab"] { background: transparent !important; color: var(--muted) !important; border-radius: 7px !important; font-size: 13px !important; padding: 6px 16px !important; }
.stTabs [aria-selected="true"] { background: var(--bg3) !important; color: var(--text) !important; }

/* Info / warning boxes */
.stAlert { border-radius: 10px !important; border: 1px solid var(--border) !important; background: var(--bg2) !important; }
</style>
""", unsafe_allow_html=True)

# ── Helpers ───────────────────────────────────────────────────────
def card(content: str):
    st.markdown(f"""
    <div style="background:var(--bg2);border:1px solid var(--border);
                border-radius:12px;padding:20px 22px;margin-bottom:8px;">
        {content}
    </div>""", unsafe_allow_html=True)

def badge(text, color):
    return f'<span style="background:{color}22;color:{color};border:1px solid {color}44;border-radius:99px;font-size:11px;font-weight:600;padding:2px 10px;font-family:var(--mono);">{text}</span>'

def mono(val):
    return f'<span style="font-family:var(--mono);font-size:13px;">{val}</span>'

# ── Background loops ──────────────────────────────────────────────
def _crypto_loop(trader):
    fetcher = DataFetcher()
    while True:
        try:
            fetcher.fetch_watchlist(crypto=CRYPTO_WATCHLIST, timeframe="15m", days=7)
            trader.run_crypto_cycle()
            st.session_state["last_crypto"] = datetime.now()
        except Exception as e:
            st.session_state["crypto_error"] = str(e)
        time.sleep(5 * 60)

def _stock_loop(trader):
    fetcher = DataFetcher()
    while True:
        try:
            fetcher.fetch_watchlist(stocks=STOCK_WATCHLIST, timeframe="1d", days=365)
            trader.run_stock_cycle()
            st.session_state["last_stock"] = datetime.now()
            _refresh_signals()
        except Exception as e:
            st.session_state["stock_error"] = str(e)
        time.sleep(15 * 60)

def _startup(trader):
    fetcher = DataFetcher()
    try:
        for msg, fn in [
            ("Fetching stock data...",  lambda: fetcher.fetch_watchlist(stocks=STOCK_WATCHLIST, timeframe="1d", days=365)),
            ("Fetching crypto data...", lambda: fetcher.fetch_watchlist(crypto=CRYPTO_WATCHLIST, timeframe="15m", days=7)),
            ("Running stock cycle...",  trader.run_stock_cycle),
            ("Running crypto cycle...", trader.run_crypto_cycle),
        ]:
            st.session_state["startup_msg"] = msg
            fn()
        st.session_state["startup_msg"]  = "done"
        st.session_state["last_stock"]   = datetime.now()
        st.session_state["last_crypto"]  = datetime.now()
        _refresh_signals()
    except Exception as e:
        st.session_state["startup_msg"] = f"error: {e}"

def _refresh_signals():
    try:
        engine = StrategyEngine()
        rows = []
        for sym in STOCK_WATCHLIST:
            sig = engine.analyse(sym, timeframe="1d")
            rows.append({"market":"📊","symbol":sig.symbol,"action":sig.action.value,
                         "confidence":sig.confidence,"price":sig.price,
                         "stop_loss":sig.stop_loss,"take_profit":sig.take_profit,
                         "reason":sig.reasons[0] if sig.reasons else ""})
        for sym in CRYPTO_WATCHLIST:
            sig = engine.analyse(sym, timeframe="15m")
            rows.append({"market":"🪙","symbol":sig.symbol,"action":sig.action.value,
                         "confidence":sig.confidence,"price":sig.price,
                         "stop_loss":sig.stop_loss,"take_profit":sig.take_profit,
                         "reason":sig.reasons[0] if sig.reasons else ""})
        st.session_state["signals_df"] = pd.DataFrame(rows)
    except Exception as e:
        st.session_state["signals_error"] = str(e)

# ── Session init ──────────────────────────────────────────────────
if "trader" not in st.session_state:
    st.session_state["trader"]      = PaperTrader(capital=100_000)
    st.session_state["signals_df"]  = None
    st.session_state["startup_msg"] = "starting"
    st.session_state["last_stock"]  = None
    st.session_state["last_crypto"] = None
    threading.Thread(target=_startup,      args=(st.session_state["trader"],), daemon=True).start()
    threading.Thread(target=_stock_loop,   args=(st.session_state["trader"],), daemon=True).start()
    threading.Thread(target=_crypto_loop,  args=(st.session_state["trader"],), daemon=True).start()

trader       = st.session_state["trader"]
trade_logger = TradeLogger()
summary      = trader.portfolio.get_summary()
cb           = trader.risk.breaker.get_status_report()
msg          = st.session_state.get("startup_msg", "starting")

# ── Top bar ───────────────────────────────────────────────────────
c1, c2, c3 = st.columns([3, 4, 3])
with c1:
    st.markdown("""
    <div style="display:flex;align-items:center;gap:12px;padding:6px 0;">
      <span style="font-size:26px;">📈</span>
      <div>
        <div style="font-family:var(--mono);font-size:18px;font-weight:700;color:var(--text);">AUTOTRADE</div>
        <div style="font-size:11px;color:var(--muted);letter-spacing:.1em;">PAPER TRADING TERMINAL</div>
      </div>
    </div>""", unsafe_allow_html=True)

with c2:
    pnl_color = "var(--green)" if summary['total_pnl'] >= 0 else "var(--red)"
    pnl_arrow = "▲" if summary['total_pnl'] >= 0 else "▼"
    st.markdown(f"""
    <div style="text-align:center;padding:6px;">
      <div style="font-family:var(--mono);font-size:28px;font-weight:700;color:{pnl_color};">
        ₹{summary['current_value']:,.0f}
      </div>
      <div style="font-size:13px;color:{pnl_color};">
        {pnl_arrow} ₹{summary['total_pnl']:+,.0f} &nbsp;({summary['total_pnl_pct']:+.2f}%)
      </div>
    </div>""", unsafe_allow_html=True)

with c3:
    cb_color = "var(--green)" if cb['status'] == "ok" else "var(--red)"
    cb_dot   = "●"
    last_s   = st.session_state.get("last_stock")
    last_c   = st.session_state.get("last_crypto")
    st.markdown(f"""
    <div style="text-align:right;padding:6px 0;">
      <div style="font-size:13px;color:{cb_color};font-family:var(--mono);">
        {cb_dot} CIRCUIT {cb['status'].upper()}
      </div>
      <div style="font-size:11px;color:var(--muted);margin-top:4px;">
        📊 {last_s.strftime('%H:%M') if last_s else '—'} &nbsp;|&nbsp; 🪙 {last_c.strftime('%H:%M') if last_c else '—'}
      </div>
      <div style="font-size:11px;color:var(--muted);">
        {datetime.now().strftime('%d %b %Y  %H:%M:%S')}
      </div>
    </div>""", unsafe_allow_html=True)

st.markdown("<hr>", unsafe_allow_html=True)

# ── KPI row ───────────────────────────────────────────────────────
k1, k2, k3, k4, k5, k6 = st.columns(6)
stats = trade_logger.get_stats()

with k1: st.metric("Cash",         f"₹{summary['cash']:,.0f}")
with k2: st.metric("Open",         summary['open_positions'], f"max {settings.risk.max_open_positions}")
with k3: st.metric("Realized P&L", f"₹{summary['realized_pnl']:+,.0f}")
with k4: st.metric("Total Trades", stats.get("total_trades", 0))
with k5: st.metric("Win Rate",     f"{stats.get('win_rate_pct', 0):.0f}%")
with k6: st.metric("Daily Loss",   f"{cb['daily_loss_pct']:.2f}%", f"limit {cb['max_daily_loss_pct']}%")

st.markdown("<hr>", unsafe_allow_html=True)

# ── Main tabs ─────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs(["📡  Signals", "💼  Positions", "📋  Trades", "📈  Charts"])

# ────────────────────────── TAB 1 — Signals ──────────────────────
with tab1:

    if msg != "done" and st.session_state["signals_df"] is None:
        st.markdown(f"""
        <div style="background:var(--bg2);border:1px solid var(--border);border-radius:12px;
                    padding:40px;text-align:center;margin:20px 0;">
          <div style="font-size:32px;margin-bottom:12px;">⏳</div>
          <div style="font-family:var(--mono);color:var(--yellow);font-size:14px;">{msg}</div>
          <div style="color:var(--muted);font-size:12px;margin-top:8px;">
            Fetching market data and running first analysis...
          </div>
        </div>""", unsafe_allow_html=True)

    elif st.session_state["signals_df"] is not None:
        df = st.session_state["signals_df"].copy()

        # Signal cards
        cols = st.columns(len(df))
        for i, (_, row) in enumerate(df.iterrows()):
            act   = row["action"]
            color = "var(--green)" if act == "BUY" else ("var(--red)" if act == "SELL" else "var(--yellow)")
            conf  = row["confidence"]
            bar_w = int(conf * 100)
            with cols[i]:
                st.markdown(f"""
                <div style="background:var(--bg2);border:1px solid var(--border);
                            border-top:2px solid {color};border-radius:10px;
                            padding:14px 12px;text-align:center;">
                  <div style="font-size:10px;color:var(--muted);letter-spacing:.08em;margin-bottom:4px;">
                    {row['market']}
                  </div>
                  <div style="font-family:var(--mono);font-size:13px;font-weight:700;
                              color:var(--text);margin-bottom:6px;">
                    {row['symbol'].replace('.NS','').replace('.BO','')}
                  </div>
                  <div style="font-size:11px;font-weight:700;color:{color};
                              letter-spacing:.08em;margin-bottom:8px;">
                    {act}
                  </div>
                  <div style="background:var(--bg3);border-radius:99px;height:4px;overflow:hidden;margin-bottom:6px;">
                    <div style="background:{color};width:{bar_w}%;height:100%;border-radius:99px;"></div>
                  </div>
                  <div style="font-family:var(--mono);font-size:10px;color:var(--muted);">
                    {conf:.0%} conf
                  </div>
                  <div style="font-family:var(--mono);font-size:11px;color:var(--text);margin-top:4px;">
                    ₹{row['price']:,.0f}
                  </div>
                </div>""", unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # Signal table
        disp = df.copy()
        disp["confidence"] = disp["confidence"].apply(lambda x: f"{x:.0%}")
        disp["price"]      = disp["price"].apply(lambda x: f"₹{x:,.2f}")
        disp["stop_loss"]  = disp["stop_loss"].apply(lambda x: f"₹{x:,.2f}" if x else "—")
        disp["take_profit"]= disp["take_profit"].apply(lambda x: f"₹{x:,.2f}" if x else "—")

        def color_action(val):
            if val == "BUY":  return "background-color:#003d1a;color:#00ff88;font-weight:700"
            if val == "SELL": return "background-color:#3d0010;color:#ff3d5a;font-weight:700"
            return "background-color:#2a2500;color:#ffc542;font-weight:700"

        st.dataframe(
            disp[["market","symbol","action","confidence","price","stop_loss","take_profit","reason"]]
            .style.map(color_action, subset=["action"]),
            use_container_width=True, hide_index=True, height=320,
        )

        # Manual refresh
        col1, col2, col3 = st.columns([1,1,4])
        with col1:
            if st.button("📊 Run stocks now", use_container_width=True):
                with st.spinner(""):
                    try:
                        DataFetcher().fetch_watchlist(stocks=STOCK_WATCHLIST, timeframe="1d", days=365)
                        trader.run_stock_cycle()
                        _refresh_signals()
                        st.session_state["last_stock"] = datetime.now()
                    except Exception as e: st.error(str(e))
                st.rerun()
        with col2:
            if st.button("🪙 Run crypto now", use_container_width=True):
                with st.spinner(""):
                    try:
                        DataFetcher().fetch_watchlist(crypto=CRYPTO_WATCHLIST, timeframe="15m", days=7)
                        trader.run_crypto_cycle()
                        st.session_state["last_crypto"] = datetime.now()
                    except Exception as e: st.error(str(e))
                st.rerun()

# ────────────────────────── TAB 2 — Positions ────────────────────
with tab2:
    if not trader.portfolio.positions:
        st.markdown("""
        <div style="background:var(--bg2);border:1px solid var(--border);border-radius:12px;
                    padding:60px;text-align:center;margin:20px 0;">
          <div style="font-size:40px;margin-bottom:16px;">🔍</div>
          <div style="font-family:var(--mono);color:var(--muted);font-size:14px;">
            No open positions
          </div>
          <div style="color:var(--muted);font-size:12px;margin-top:8px;">
            Bot is scanning every 5–15 min for signals above 40% confidence
          </div>
        </div>""", unsafe_allow_html=True)
    else:
        for sym, pos in trader.portfolio.positions.items():
            pnl_c = "var(--green)" if pos.unrealized_pnl >= 0 else "var(--red)"
            side_c= "var(--green)" if pos.side == "long" else "var(--red)"
            pct_sl = ((pos.current_price or pos.entry_price) - pos.stop_loss) / pos.entry_price * 100
            pct_tp = (pos.take_profit - pos.entry_price) / pos.entry_price * 100
            st.markdown(f"""
            <div style="background:var(--bg2);border:1px solid var(--border);
                        border-left:3px solid {pnl_c};border-radius:12px;
                        padding:20px 24px;margin-bottom:12px;">
              <div style="display:flex;justify-content:space-between;align-items:flex-start;">
                <div>
                  <div style="font-family:var(--mono);font-size:18px;font-weight:700;
                              color:var(--text);">{sym}</div>
                  <div style="margin-top:6px;display:flex;gap:8px;align-items:center;">
                    <span style="color:{side_c};font-size:12px;font-weight:600;
                                 background:{side_c}22;padding:2px 8px;border-radius:99px;
                                 font-family:var(--mono);">{pos.side.upper()}</span>
                    <span style="color:var(--muted);font-size:12px;">{pos.strategy}</span>
                  </div>
                </div>
                <div style="text-align:right;">
                  <div style="font-family:var(--mono);font-size:22px;font-weight:700;
                              color:{pnl_c};">
                    ₹{pos.unrealized_pnl:+,.2f}
                  </div>
                  <div style="font-family:var(--mono);font-size:13px;color:{pnl_c};">
                    {pos.unrealized_pnl_pct:+.2f}%
                  </div>
                </div>
              </div>
              <div style="display:grid;grid-template-columns:repeat(4,1fr);
                          gap:16px;margin-top:16px;padding-top:16px;
                          border-top:1px solid var(--border);">
                <div>
                  <div style="font-size:10px;color:var(--muted);text-transform:uppercase;
                               letter-spacing:.08em;margin-bottom:4px;">Quantity</div>
                  <div style="font-family:var(--mono);font-size:14px;">{pos.quantity}</div>
                </div>
                <div>
                  <div style="font-size:10px;color:var(--muted);text-transform:uppercase;
                               letter-spacing:.08em;margin-bottom:4px;">Entry</div>
                  <div style="font-family:var(--mono);font-size:14px;">₹{pos.entry_price:,.2f}</div>
                </div>
                <div>
                  <div style="font-size:10px;color:var(--red);text-transform:uppercase;
                               letter-spacing:.08em;margin-bottom:4px;">Stop Loss</div>
                  <div style="font-family:var(--mono);font-size:14px;color:var(--red);">₹{pos.stop_loss:,.2f}</div>
                </div>
                <div>
                  <div style="font-size:10px;color:var(--green);text-transform:uppercase;
                               letter-spacing:.08em;margin-bottom:4px;">Take Profit</div>
                  <div style="font-family:var(--mono);font-size:14px;color:var(--green);">₹{pos.take_profit:,.2f}</div>
                </div>
              </div>
            </div>""", unsafe_allow_html=True)

# ────────────────────────── TAB 3 — Trades ───────────────────────
with tab3:
    all_trades = trade_logger.get_all_trades()

    if not all_trades.empty:
        # Summary bar
        w = stats.get("winning_trades", 0)
        l = stats.get("losing_trades", 0)
        t = stats.get("total_trades", 1)
        st.markdown(f"""
        <div style="background:var(--bg2);border:1px solid var(--border);border-radius:12px;
                    padding:18px 24px;margin-bottom:16px;
                    display:flex;gap:32px;align-items:center;flex-wrap:wrap;">
          <div>
            <div style="font-size:10px;color:var(--muted);letter-spacing:.08em;
                         text-transform:uppercase;margin-bottom:4px;">Total Trades</div>
            <div style="font-family:var(--mono);font-size:20px;font-weight:700;">{t}</div>
          </div>
          <div>
            <div style="font-size:10px;color:var(--muted);letter-spacing:.08em;
                         text-transform:uppercase;margin-bottom:4px;">Win Rate</div>
            <div style="font-family:var(--mono);font-size:20px;font-weight:700;
                         color:var(--green);">{stats.get('win_rate_pct',0):.0f}%</div>
          </div>
          <div>
            <div style="font-size:10px;color:var(--muted);letter-spacing:.08em;
                         text-transform:uppercase;margin-bottom:4px;">Total P&L</div>
            <div style="font-family:var(--mono);font-size:20px;font-weight:700;
                         color:{'var(--green)' if stats.get('total_pnl',0)>=0 else 'var(--red)'};">
              ₹{stats.get('total_pnl',0):+,.0f}
            </div>
          </div>
          <div>
            <div style="font-size:10px;color:var(--muted);letter-spacing:.08em;
                         text-transform:uppercase;margin-bottom:4px;">Avg Win</div>
            <div style="font-family:var(--mono);font-size:20px;font-weight:700;
                         color:var(--green);">₹{stats.get('avg_win',0):+,.0f}</div>
          </div>
          <div>
            <div style="font-size:10px;color:var(--muted);letter-spacing:.08em;
                         text-transform:uppercase;margin-bottom:4px;">Avg Loss</div>
            <div style="font-family:var(--mono);font-size:20px;font-weight:700;
                         color:var(--red);">₹{stats.get('avg_loss',0):+,.0f}</div>
          </div>
          <div style="flex:1;min-width:120px;">
            <div style="font-size:10px;color:var(--muted);letter-spacing:.08em;
                         text-transform:uppercase;margin-bottom:6px;">W/L Ratio</div>
            <div style="background:var(--bg3);border-radius:99px;height:6px;overflow:hidden;">
              <div style="background:var(--green);width:{w/t*100:.0f}%;height:100%;border-radius:99px;"></div>
            </div>
            <div style="font-size:10px;color:var(--muted);margin-top:4px;">{w}W · {l}L</div>
          </div>
        </div>""", unsafe_allow_html=True)

        col1, col2 = st.columns(2)
        with col1:
            syms    = ["All"] + sorted(all_trades["symbol"].unique().tolist())
            sel_sym = st.selectbox("Symbol", syms, key="sym_filter")
        with col2:
            sel_out = st.selectbox("Outcome", ["All","Winners","Losers"], key="out_filter")

        disp = all_trades.copy()
        if sel_sym != "All":       disp = disp[disp["symbol"] == sel_sym]
        if sel_out == "Winners":   disp = disp[disp["winner"] == True]
        elif sel_out == "Losers":  disp = disp[disp["winner"] == False]

        disp["pnl"]     = disp["pnl"].apply(lambda x: f"₹{x:+,.2f}")
        disp["pnl_pct"] = disp["pnl_pct"].apply(lambda x: f"{x:+.2f}%")
        disp["entry"]   = disp["entry"].apply(lambda x: f"₹{x:,.2f}")
        disp["exit"]    = disp["exit"].apply(lambda x: f"₹{x:,.2f}")
        disp["winner"]  = disp["winner"].apply(lambda x: "✅ Win" if x else "❌ Loss")

        st.dataframe(
            disp[["symbol","side","quantity","entry","exit","pnl","pnl_pct",
                  "winner","strategy","exit_reason","closed_at"]],
            use_container_width=True, hide_index=True,
        )
    else:
        st.markdown("""
        <div style="background:var(--bg2);border:1px solid var(--border);border-radius:12px;
                    padding:60px;text-align:center;margin:20px 0;">
          <div style="font-size:40px;margin-bottom:16px;">📋</div>
          <div style="font-family:var(--mono);color:var(--muted);font-size:14px;">
            No closed trades yet
          </div>
          <div style="color:var(--muted);font-size:12px;margin-top:8px;">
            Trades appear here once stop loss or take profit is hit
          </div>
        </div>""", unsafe_allow_html=True)

# ────────────────────────── TAB 4 — Charts ───────────────────────
with tab4:
    raw = trade_logger.get_all_trades()

    CHART_BG = dict(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#4e6585", family="Space Mono"),
                    xaxis=dict(gridcolor="#1e2d42", showgrid=True, zeroline=False),
                    yaxis=dict(gridcolor="#1e2d42", showgrid=True, zeroline=False))

    if not raw.empty:
        col1, col2 = st.columns(2)

        with col1:
            srt = raw.sort_values("closed_at")
            srt["equity"] = 100_000 + srt["pnl"].cumsum()
            above = srt["equity"] >= 100_000

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=srt["closed_at"], y=srt["equity"],
                mode="lines", line=dict(color="#00ff88", width=2),
                fill="tozeroy", fillcolor="rgba(0,255,136,0.06)",
                name="Portfolio",
            ))
            fig.add_hline(y=100_000, line_dash="dot", line_color="#1e2d42",
                          annotation_text="₹1,00,000", annotation_font_color="#4e6585")
            fig.update_layout(title=dict(text="Equity Curve", font=dict(color="#e2eaf5")),
                              showlegend=False, margin=dict(t=40,b=20,l=0,r=0), **CHART_BG)
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            wins   = raw[raw["winner"]==True]["pnl"]
            losses = raw[raw["winner"]==False]["pnl"]
            fig2 = go.Figure()
            if len(wins):
                fig2.add_trace(go.Histogram(x=wins,   nbinsx=10, name="Win",
                                            marker_color="rgba(0,255,136,0.7)"))
            if len(losses):
                fig2.add_trace(go.Histogram(x=losses, nbinsx=10, name="Loss",
                                            marker_color="rgba(255,61,90,0.7)"))
            fig2.update_layout(title=dict(text="P&L Distribution", font=dict(color="#e2eaf5")),
                               barmode="overlay", margin=dict(t=40,b=20,l=0,r=0),
                               legend=dict(font=dict(color="#e2eaf5")), **CHART_BG)
            st.plotly_chart(fig2, use_container_width=True)

        col3, col4 = st.columns(2)
        with col3:
            sym_s = raw.groupby("symbol").agg(pnl=("pnl","sum")).reset_index()
            sym_s["color"] = sym_s["pnl"].apply(lambda x: "#00ff88" if x>=0 else "#ff3d5a")
            fig3 = go.Figure(go.Bar(
                x=sym_s["symbol"], y=sym_s["pnl"],
                marker_color=sym_s["color"],
                text=sym_s["pnl"].apply(lambda x: f"₹{x:+,.0f}"),
                textposition="outside", textfont=dict(color="#e2eaf5", size=11),
            ))
            fig3.update_layout(title=dict(text="P&L by Symbol", font=dict(color="#e2eaf5")),
                               margin=dict(t=40,b=20,l=0,r=0), **CHART_BG)
            st.plotly_chart(fig3, use_container_width=True)

        with col4:
            ec   = raw["exit_reason"].value_counts().reset_index()
            ec.columns = ["reason","count"]
            fig4 = go.Figure(go.Pie(
                labels=ec["reason"], values=ec["count"],
                hole=0.5,
                marker=dict(colors=["#00ff88","#ff3d5a","#ffc542","#3d8eff"],
                            line=dict(color="#070b12", width=2)),
                textfont=dict(color="#e2eaf5"),
            ))
            fig4.update_layout(title=dict(text="Exit Reasons", font=dict(color="#e2eaf5")),
                               showlegend=True,
                               legend=dict(font=dict(color="#e2eaf5")),
                               margin=dict(t=40,b=20,l=0,r=0),
                               paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig4, use_container_width=True)
    else:
        st.markdown("""
        <div style="background:var(--bg2);border:1px solid var(--border);border-radius:12px;
                    padding:80px;text-align:center;margin:20px 0;">
          <div style="font-size:48px;margin-bottom:16px;">📈</div>
          <div style="font-family:var(--mono);color:var(--muted);font-size:14px;">
            Charts appear after your first closed trades
          </div>
        </div>""", unsafe_allow_html=True)

# ── Footer ────────────────────────────────────────────────────────
st.markdown("""
<div style="text-align:center;padding:16px 0 4px;font-size:11px;color:var(--muted);
            font-family:var(--mono);letter-spacing:.06em;">
  AUTOTRADE · PAPER MODE · NO REAL MONEY AT RISK ·
  📊 STOCKS EVERY 15 MIN · 🪙 CRYPTO EVERY 5 MIN · 🔄 UI EVERY 60 SEC
</div>""", unsafe_allow_html=True)
