"""
run_paper_trader.py
────────────────────
Start the paper trading bot.
Runs continuously, scanning markets every hour.

Usage:
    python run_paper_trader.py           # Run every 60 minutes
    python run_paper_trader.py --once    # Run just one cycle
    python run_paper_trader.py --report  # Show performance report

Press Ctrl+C at any time to stop and see your performance report.
"""

import argparse
import sys
from src.execution.paper_trader import PaperTrader
from src.data.fetcher import DataFetcher
from src.utils.logger import logger

CAPITAL = 100_000  # Starting capital in ₹


def main():
    parser = argparse.ArgumentParser(description="AutoTrade Paper Trading Bot")
    parser.add_argument("--once",   action="store_true", help="Run a single cycle and exit")
    parser.add_argument("--report", action="store_true", help="Show performance report only")
    parser.add_argument("--interval", type=int, default=60, help="Minutes between cycles (default: 60)")
    args = parser.parse_args()

    print("\n" + "━" * 60)
    print("  🤖 AutoTrade — Paper Trading Bot")
    print(f"  Capital: ₹{CAPITAL:,.0f} | Mode: PAPER (no real money)")
    print("━" * 60)

    # Ensure DB has data
    print("\n📡  Checking database...")
    fetcher = DataFetcher()
    log = fetcher.get_fetch_log()
    if log.empty:
        print("  DB is empty — fetching data first...")
        from src.data.scheduler import DataScheduler
        scheduler = DataScheduler()
        scheduler.run_initial_fetch()
    else:
        print(f"  DB has data for {len(log)} symbol/timeframe pairs ✅")

    # Create trader
    trader = PaperTrader(capital=CAPITAL)

    if args.report:
        # Just show the report
        trader.get_report()
        from src.execution.trade_logger import TradeLogger
        tl = TradeLogger()
        df = tl.get_all_trades()
        if not df.empty:
            print("\n📋 Recent Trades:")
            print(df[["symbol", "side", "entry", "exit", "pnl", "pnl_pct", "exit_reason", "closed_at"]].head(20).to_string(index=False))
        return

    if args.once:
        # Single cycle
        print("\n🔄 Running single cycle...\n")
        trader.run_cycle()
        trader.get_report()
        return

    # Continuous loop
    print(f"\n⏱️  Starting continuous loop every {args.interval} minutes")
    print("   Press Ctrl+C to stop and see your report\n")
    trader.start_loop(interval_minutes=args.interval, run_now=True)


if __name__ == "__main__":
    main()
