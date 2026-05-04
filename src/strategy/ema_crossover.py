"""
src/strategy/ema_crossover.py
──────────────────────────────
Strategy 1: EMA Crossover (Golden Cross / Death Cross)

Logic:
  BUY  when EMA20 crosses ABOVE EMA50 (Golden Cross) — uptrend starting
  SELL when EMA20 crosses BELOW EMA50 (Death Cross)  — downtrend starting
  HOLD otherwise

Confidence boosters:
  + High volume on crossover day     → +0.15
  + RSI not overbought/oversold      → +0.10
  + Price above EMA200 (bull market) → +0.10
  + MACD agrees with direction       → +0.15

Best for: Daily / Weekly timeframes, trending markets
Risk    : Lags — gives signal after trend has started, not at the exact turn
"""

import pandas as pd
from src.strategy.signals import Signal, Action
from src.utils.logger import logger


class EMACrossoverStrategy:
    """EMA 20/50 crossover with confluence filters."""

    NAME = "EMA_Crossover"

    def generate(self, df: pd.DataFrame, symbol: str) -> Signal:
        """
        Analyse the latest candle and return a Signal.

        Args:
            df    : DataFrame with indicators already added (via add_indicators)
            symbol: symbol name for the signal

        Returns:
            Signal object with BUY / SELL / HOLD
        """
        if len(df) < 2:
            return self._hold(symbol, 0.0, df, ["Insufficient data"])

        latest = df.iloc[-1]
        prev   = df.iloc[-2]
        price  = float(latest["close"])
        reasons = []
        confidence = 0.0

        # ── Core signal ───────────────────────────────────────────
        golden_cross = bool(latest["ema_cross_up"])
        death_cross  = bool(latest["ema_cross_down"])
        ema_bullish  = bool(latest["ema_bullish"])

        if golden_cross:
            action = Action.BUY
            confidence = 0.50
            reasons.append("Golden Cross: EMA20 crossed above EMA50 🟢")
        elif death_cross:
            action = Action.SELL
            confidence = 0.50
            reasons.append("Death Cross: EMA20 crossed below EMA50 🔴")
        elif ema_bullish:
            # No crossover today but still in uptrend — weak buy
            action = Action.BUY
            confidence = 0.25
            reasons.append("EMA20 above EMA50 — uptrend continues")
        else:
            action = Action.SELL
            confidence = 0.25
            reasons.append("EMA20 below EMA50 — downtrend continues")

        # ── Confluence boosters ───────────────────────────────────

        # Volume confirmation
        if "volume_ratio" in df.columns and not pd.isna(latest["volume_ratio"]):
            if float(latest["volume_ratio"]) > 1.5:
                confidence += 0.15
                reasons.append(f"High volume ({latest['volume_ratio']:.1f}x average)")

        # RSI not extreme
        if "rsi" in df.columns and not pd.isna(latest["rsi"]):
            rsi = float(latest["rsi"])
            if action == Action.BUY and rsi < 70:
                confidence += 0.10
                reasons.append(f"RSI={rsi:.1f} — not overbought")
            elif action == Action.SELL and rsi > 30:
                confidence += 0.10
                reasons.append(f"RSI={rsi:.1f} — not oversold")
            elif action == Action.BUY and rsi >= 70:
                confidence -= 0.10
                reasons.append(f"RSI={rsi:.1f} — WARNING: overbought")

        # Long-term trend (EMA200)
        if "ema_200" in df.columns and not pd.isna(latest.get("ema_200")):
            if action == Action.BUY and price > float(latest["ema_200"]):
                confidence += 0.10
                reasons.append("Price above EMA200 — long-term bull market")
            elif action == Action.SELL and price < float(latest["ema_200"]):
                confidence += 0.10
                reasons.append("Price below EMA200 — long-term bear market")

        # MACD agreement
        if "macd_cross_up" in df.columns:
            if action == Action.BUY and bool(latest.get("macd_cross_up", False)):
                confidence += 0.15
                reasons.append("MACD also crossed up — double confirmation!")
            elif action == Action.SELL and bool(latest.get("macd_cross_down", False)):
                confidence += 0.15
                reasons.append("MACD also crossed down — double confirmation!")

        # Cap confidence at 1.0
        confidence = min(confidence, 1.0)

        # ── Stop loss / take profit ───────────────────────────────
        stop_loss = take_profit = None
        if "atr" in df.columns and not pd.isna(latest.get("atr")):
            atr = float(latest["atr"])
            if action == Action.BUY:
                stop_loss   = round(price - 2 * atr, 2)
                take_profit = round(price + 3 * atr, 2)
            elif action == Action.SELL:
                stop_loss   = round(price + 2 * atr, 2)
                take_profit = round(price - 3 * atr, 2)

        signal = Signal(
            symbol=symbol, action=action, confidence=confidence,
            strategy=self.NAME, price=price, reasons=reasons,
            stop_loss=stop_loss, take_profit=take_profit,
        )
        logger.info(str(signal))
        return signal

    def _hold(self, symbol, conf, df, reasons):
        price = float(df.iloc[-1]["close"]) if not df.empty else 0.0
        return Signal(symbol=symbol, action=Action.HOLD, confidence=conf,
                      strategy=self.NAME, price=price, reasons=reasons)
