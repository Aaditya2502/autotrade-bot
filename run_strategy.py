"""
run_strategy.py
────────────────
Run the strategy engine right now and see live signals.
Run with:
    python run_strategy.py

Also runs backtests and shows a comparison table.
"""

from src.strategy.engine import StrategyEngine
from src.strategy.backtest import run_all_backtests
from src.utils.logger import logger
import pandas as pd

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 120)


def main():
    print("\n" + "━" * 60)
    print("  AutoTrade — Strategy Engine")
    print("━" * 60)

    engine = StrategyEngine()

    # ── Live Signal Scan ──────────────────────────────────────────
    print("\n📡  Scanning watchlist for signals [Daily timeframe]...\n")
    df_signals = engine.get_summary_table(
        stocks=["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS"],
        crypto=["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
        timeframe="1d",
    )

    if not df_signals.empty:
        print(df_signals[["symbol", "action", "confidence", "price", "stop_loss", "take_profit", "reason"]].to_string(index=False))

    # ── Top actionable signals ────────────────────────────────────
    print("\n\n🎯  Top Actionable Signals (confidence ≥ 40%):\n")
    signals = engine.scan_watchlist(
        stocks=["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS"],
        crypto=["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
        timeframe="1d",
        min_confidence=0.40,
    )

    if signals:
        for s in signals:
            icon = "🟢" if s.action == "BUY" else "🔴"
            print(f"  {icon} {s.action:<4} {s.symbol:<15} "
                  f"conf={s.confidence:.0%}  "
                  f"price={s.price:>10,.2f}  "
                  f"SL={str(s.stop_loss):>10}  "
                  f"TP={str(s.take_profit):>10}")
            for r in s.reasons[:2]:
                print(f"       → {r}")
            print()
    else:
        print("  No high-confidence signals right now — market may be in consolidation.")

    # ── Backtest ──────────────────────────────────────────────────
    print("\n\n📊  Running Backtests (this takes ~30 seconds)...\n")
    bt_results = run_all_backtests(
        symbols=["RELIANCE.NS", "BTCUSDT"],
        strategies=["EMA_Crossover", "RSI_MACD"],
        timeframe="1d",
    )

    if not bt_results.empty:
        print(bt_results[[
            "symbol", "strategy", "total_return_pct",
            "win_rate_pct", "max_drawdown_pct",
            "sharpe_ratio", "total_trades"
        ]].to_string(index=False))

    print("\n" + "━" * 60)
    print("  Done! Phase 3 complete 🚀")
    print("━" * 60 + "\n")


if __name__ == "__main__":
    main()
