"""
src/risk/position_sizer.py
───────────────────────────
Position sizing module.
Answers the question: "How many shares/units should I buy?"

Rule: Never risk more than MAX_POSITION_SIZE_PCT% of capital on a single trade.
Risk = distance from entry to stop-loss × quantity.

Example:
  Capital       = ₹100,000
  Max risk/trade = 2% = ₹2,000
  Entry price   = ₹1,500
  Stop loss     = ₹1,440  (₹60 below entry)
  
  Max quantity  = ₹2,000 / ₹60 = 33 shares
  Position size = 33 × ₹1,500  = ₹49,500 (49.5% of capital)

This ensures even if stop loss is hit, you only lose 2% of capital.
"""

from dataclasses import dataclass
from config.settings import settings
from src.utils.logger import logger


@dataclass
class PositionSize:
    """Result of position sizing calculation."""
    symbol          : str
    entry_price     : float
    stop_loss       : float
    quantity        : float        # shares / units to buy
    position_value  : float        # total ₹ value of position
    risk_amount     : float        # max ₹ you can lose on this trade
    risk_pct        : float        # % of capital at risk
    capital_used_pct: float        # % of capital used for position

    def __str__(self):
        return (
            f"Position({self.symbol}): "
            f"qty={self.quantity:.4f} @ ₹{self.entry_price:,.2f} "
            f"= ₹{self.position_value:,.2f} | "
            f"risk=₹{self.risk_amount:,.2f} ({self.risk_pct:.1f}%) | "
            f"SL=₹{self.stop_loss:,.2f}"
        )


class PositionSizer:
    """
    Calculates safe position sizes based on risk parameters.
    Uses the fixed-fractional position sizing method.
    """

    def __init__(self):
        self.max_risk_pct      = settings.risk.max_position_size_pct / 100  # e.g. 0.02
        self.max_open_positions= settings.risk.max_open_positions

    def calculate(
        self,
        symbol      : str,
        entry_price : float,
        stop_loss   : float,
        capital     : float,
        confidence  : float = 1.0,
    ) -> PositionSize:
        """
        Calculate position size using fixed-fractional risk management.

        Args:
            symbol      : trading symbol
            entry_price : price to enter the trade
            stop_loss   : price at which we exit if wrong
            capital     : total available capital
            confidence  : signal confidence 0-1 (scales position size down for low confidence)

        Returns:
            PositionSize with recommended quantity
        """
        if entry_price <= 0 or stop_loss <= 0 or capital <= 0:
            raise ValueError(f"Invalid inputs: entry={entry_price}, sl={stop_loss}, capital={capital}")

        risk_per_unit = abs(entry_price - stop_loss)
        if risk_per_unit == 0:
            raise ValueError("Stop loss equals entry price — cannot calculate position size")

        # Scale risk by confidence (low confidence = smaller position)
        # confidence=1.0 → full risk%, confidence=0.5 → half risk%
        scaled_risk_pct = self.max_risk_pct * max(confidence, 0.3)  # minimum 30% of max risk
        max_risk_amount = capital * scaled_risk_pct

        # Core calculation: how many units can we buy within our risk budget?
        quantity = max_risk_amount / risk_per_unit

        # Round down to avoid overspending (stocks need whole numbers)
        if entry_price > 100:  # Stocks — whole shares only
            quantity = int(quantity)
        else:
            quantity = round(quantity, 4)  # Crypto — fractional units ok

        # Ensure minimum 1 unit
        quantity = max(quantity, 1) if entry_price > 100 else max(quantity, 0.0001)

        position_value   = quantity * entry_price
        actual_risk      = quantity * risk_per_unit
        actual_risk_pct  = (actual_risk / capital) * 100
        capital_used_pct = (position_value / capital) * 100

        result = PositionSize(
            symbol=symbol,
            entry_price=entry_price,
            stop_loss=stop_loss,
            quantity=quantity,
            position_value=round(position_value, 2),
            risk_amount=round(actual_risk, 2),
            risk_pct=round(actual_risk_pct, 2),
            capital_used_pct=round(capital_used_pct, 2),
        )

        logger.info(f"Position size: {result}")
        return result

    def max_affordable_quantity(
        self,
        entry_price : float,
        capital     : float,
        max_pct     : float = 0.20,  # Never use more than 20% of capital on one trade
    ) -> float:
        """
        Fallback: if no stop loss available, limit position to max_pct of capital.
        """
        max_spend = capital * max_pct
        quantity = max_spend / entry_price
        return int(quantity) if entry_price > 100 else round(quantity, 4)
