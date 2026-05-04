"""
src/strategy/rsi_macd.py
─────────────────────────
Strategy 2: RSI + MACD Confluence

Logic:
  BUY  when RSI is oversold (<35) AND MACD crosses up   → strong buy
  BUY  when RSI is oversold (<35) OR  MACD crosses up   → weak buy
  SELL when RSI is overbought (>65) AND MACD crosses down → strong sell
  SELL when RSI is overbought (>65) OR  MACD crosses down → weak sell
  HOLD otherwise

The key insight: requiring BOTH indicators to agree reduces false signals
dramatically compared to using either one alone.

Best for: 1h / 4h / Daily timeframes
Risk    : Can miss strong trending moves where RSI stays overbought
"""

import pandas as pd
from src.strategy.signals import Signal, Action
from src.utils.logger import logger


class RSIMACDStrategy:
    """RSI + MACD confluence — requires both to agree for high confidence."""

    NAME = "RSI_MACD"

    def generate(self, df: pd.DataFrame, symbol: str) -> Signal:
        if len(df) < 2:
            return self._hold(symbol, df, ["Insufficient data"])

        latest = df.iloc[-1]
        price  = float(latest["close"])
        reasons = []

        rsi  = float(latest["rsi"])  if not pd.isna(latest.get("rsi"))  else 50.0
        macd = float(latest["macd"]) if not pd.isna(latest.get("macd")) else 0.0
        macd_sig = float(latest["macd_signal"]) if not pd.isna(latest.get("macd_signal")) else 0.0

        macd_cross_up   = bool(latest.get("macd_cross_up",   False))
        macd_cross_down = bool(latest.get("macd_cross_down", False))
        macd_bullish    = macd > macd_sig

        rsi_oversold    = rsi < 35
        rsi_overbought  = rsi > 65

        # ── Score each direction independently ───────────────────
        buy_score  = 0.0
        sell_score = 0.0

        # RSI signals
        if rsi < 25:
            buy_score += 0.40
            reasons.append(f"RSI={rsi:.1f} — extremely oversold 🟢🟢")
        elif rsi_oversold:
            buy_score += 0.25
            reasons.append(f"RSI={rsi:.1f} — oversold 🟢")

        if rsi > 75:
            sell_score += 0.40
            reasons.append(f"RSI={rsi:.1f} — extremely overbought 🔴🔴")
        elif rsi_overbought:
            sell_score += 0.25
            reasons.append(f"RSI={rsi:.1f} — overbought 🔴")

        # MACD signals
        if macd_cross_up:
            buy_score += 0.35
            reasons.append("MACD crossed above signal line 🟢")
        elif macd_bullish:
            buy_score += 0.15
            reasons.append("MACD above signal (bullish momentum)")

        if macd_cross_down:
            sell_score += 0.35
            reasons.append("MACD crossed below signal line 🔴")
        elif not macd_bullish:
            sell_score += 0.15
            reasons.append("MACD below signal (bearish momentum)")

        # MACD histogram acceleration
        if "macd_histogram" in df.columns and len(df) >= 2:
            hist_now  = float(latest["macd_histogram"]) if not pd.isna(latest.get("macd_histogram")) else 0
            hist_prev = float(df.iloc[-2]["macd_histogram"]) if not pd.isna(df.iloc[-2].get("macd_histogram")) else 0
            if hist_now > hist_prev > 0:
                buy_score += 0.10
                reasons.append("MACD histogram growing — momentum increasing")
            elif hist_now < hist_prev < 0:
                sell_score += 0.10
                reasons.append("MACD histogram falling — selling pressure")

        # Volume confirmation
        if "volume_ratio" in df.columns and not pd.isna(latest.get("volume_ratio")):
            vol_ratio = float(latest["volume_ratio"])
            if vol_ratio > 1.5:
                if buy_score > sell_score:
                    buy_score += 0.10
                    reasons.append(f"Volume surge ({vol_ratio:.1f}x) confirms signal")
                else:
                    sell_score += 0.10
                    reasons.append(f"Volume surge ({vol_ratio:.1f}x) confirms signal")

        # ── Decide action ─────────────────────────────────────────
        if buy_score >= 0.40 and buy_score > sell_score:
            action     = Action.BUY
            confidence = min(buy_score, 1.0)
        elif sell_score >= 0.40 and sell_score > buy_score:
            action     = Action.SELL
            confidence = min(sell_score, 1.0)
        else:
            action     = Action.HOLD
            confidence = 0.0
            if not reasons:
                reasons.append(f"RSI={rsi:.1f} neutral, no clear MACD signal")

        # ── Stop loss / take profit via ATR ───────────────────────
        stop_loss = take_profit = None
        if "atr" in df.columns and not pd.isna(latest.get("atr")):
            atr = float(latest["atr"])
            if action == Action.BUY:
                stop_loss   = round(price - 2.0 * atr, 2)
                take_profit = round(price + 2.5 * atr, 2)
            elif action == Action.SELL:
                stop_loss   = round(price + 2.0 * atr, 2)
                take_profit = round(price - 2.5 * atr, 2)

        signal = Signal(
            symbol=symbol, action=action, confidence=confidence,
            strategy=self.NAME, price=price, reasons=reasons,
            stop_loss=stop_loss, take_profit=take_profit,
        )
        logger.info(str(signal))
        return signal

    def _hold(self, symbol, df, reasons):
        price = float(df.iloc[-1]["close"]) if not df.empty else 0.0
        return Signal(symbol=symbol, action=Action.HOLD, confidence=0.0,
                      strategy=self.NAME, price=price, reasons=reasons)
