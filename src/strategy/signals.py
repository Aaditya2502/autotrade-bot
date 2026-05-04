"""
src/strategy/signals.py
────────────────────────
Signal types and the Signal dataclass.
Every strategy outputs a Signal object.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Action(str, Enum):
    BUY  = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass
class Signal:
    """
    Output of any strategy.

    Attributes:
        symbol      : e.g. "RELIANCE.NS"
        action      : BUY | SELL | HOLD
        confidence  : 0.0 – 1.0  (higher = stronger signal)
        strategy    : name of the strategy that generated this
        price       : price at signal time
        timestamp   : when the signal was generated
        reasons     : list of human-readable reasons (for logging + dashboard)
        stop_loss   : suggested stop-loss price (optional)
        take_profit : suggested take-profit price (optional)
    """
    symbol      : str
    action      : Action
    confidence  : float
    strategy    : str
    price       : float
    timestamp   : datetime = field(default_factory=datetime.now)
    reasons     : list     = field(default_factory=list)
    stop_loss   : float    = None
    take_profit : float    = None

    def __str__(self):
        icon = {"BUY": "🟢", "SELL": "🔴", "HOLD": "🟡"}[self.action]
        reasons_str = " | ".join(self.reasons[:3])
        return (
            f"{icon} {self.action} {self.symbol} "
            f"@ ₹{self.price:,.2f} "
            f"[{self.strategy}] "
            f"conf={self.confidence:.0%} "
            f"— {reasons_str}"
        )
