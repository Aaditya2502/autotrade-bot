"""
run_risk_demo.py
─────────────────
Demo of the Risk Manager working with real strategy signals.
Shows how every signal gets evaluated before any trade is allowed.

Run with:
    python run_risk_demo.py
"""

from src.strategy.engine import StrategyEngine
from src.risk.manager import RiskManager
from src.utils.logger import logger

CAPITAL = 100_000  # ₹1 lakh starting capital

def main():
    print("\n" + "━" * 60)
    print("  AutoTrade — Risk Management Demo")
    print(f"  Starting Capital: ₹{CAPITAL:,.0f}")
    print("━" * 60)

    engine = StrategyEngine()
    risk   = RiskManager(capital=CAPITAL)

    # ── Scan for signals ─────────────────────────────────────────
    print("\n📡  Getting live signals...\n")
    signals = engine.scan_watchlist(
        stocks=["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS"],
        crypto=["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
        timeframe="1h",
        min_confidence=0.0,  # Get all signals for demo
    )

    if not signals:
        # Fallback — use daily
        signals = engine.scan_watchlist(
            stocks=["RELIANCE.NS", "TCS.NS"],
            crypto=[],
            timeframe="1d",
            min_confidence=0.0,
        )

    # ── Evaluate each signal through risk manager ─────────────────
    print("\n🛡️  Risk Manager Evaluation:\n")
    approved_trades = []
    open_positions  = 0
    total_exposure  = 0.0

    for signal in signals[:8]:  # Check first 8 signals
        print(f"  Signal: {signal.action} {signal.symbol} @ ₹{signal.price:,.2f} conf={signal.confidence:.0%}")

        decision = risk.evaluate_signal(
            signal,
            open_positions=open_positions,
            total_exposure=total_exposure,
        )

        if decision.approved:
            print(f"  ✅ APPROVED")
            print(f"     Qty:        {decision.quantity} units")
            print(f"     Value:      ₹{decision.position_value:,.2f}")
            print(f"     Stop Loss:  ₹{decision.stop_loss:,.2f}")
            print(f"     Take Profit:₹{decision.take_profit:,.2f}")
            print(f"     Risk:       ₹{decision.risk_amount:,.2f} ({decision.risk_pct:.1f}% of capital)")
            approved_trades.append(decision)
            open_positions += 1
            total_exposure += decision.position_value
        else:
            print(f"  ❌ REJECTED: {decision.rejection_reason}")
        print()

    # ── Risk Report ───────────────────────────────────────────────
    print("━" * 60)
    print("  📊 Risk Status Report:")
    print("━" * 60)
    report = risk.get_risk_report()
    cb = report["circuit_breaker"]
    print(f"  Status:           {cb['status'].upper()}")
    print(f"  Capital:          ₹{report['capital']:,.2f}")
    print(f"  Daily Loss So Far:{cb['daily_loss_pct']:.2f}% (limit: {cb['max_daily_loss_pct']}%)")
    print(f"  Trades Today:     {cb['trades_today']}")
    print(f"  Max Risk/Trade:   {report['max_risk_per_trade_pct']}%")
    print(f"  Max Daily Loss:   {report['max_daily_loss_pct']}%")
    print(f"  Max Positions:    {report['max_open_positions']}")

    if approved_trades:
        print(f"\n  Approved Trades:  {len(approved_trades)}")
        print(f"  Total Exposure:   ₹{total_exposure:,.2f} ({total_exposure/CAPITAL*100:.1f}% of capital)")
        max_possible_loss = sum(d.risk_amount for d in approved_trades)
        print(f"  Max Possible Loss:₹{max_possible_loss:,.2f} ({max_possible_loss/CAPITAL*100:.1f}% of capital)")

    print("\n" + "━" * 60)
    print("  Phase 4 Risk Management working! 🛡️")
    print("━" * 60 + "\n")


if __name__ == "__main__":
    main()
