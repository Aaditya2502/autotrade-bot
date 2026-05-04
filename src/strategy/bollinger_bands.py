"""
src/strategy/bollinger_bands.py
────────────────────────────────
Strategy 3: Bollinger Bands Mean Reversion + Breakout

Two modes:
  MEAN REVERSION (default, lower risk):
    BUY  when price touches/breaks below lower band (expect bounce back up)
    SELL when price touches/breaks above upper band (expect drop back down)

  BREAKOUT (higher risk, higher reward):
    BUY  when price breaks above upper band WITH high volume (strong uptrend)
    SELL when price breaks below lower band WITH high volume (strong downtrend)

The strategy auto-detects which mode to use based on BB squeeze:
  - During a squeeze (bands narrow) → breakout mode (big move coming)
  - During normal/wide bands        → mean reversion mode

Best for: Volatile assets like crypto, and range-bound stocks
Risk    : Mean reversion fails badly in strong trends
"""

import pandas as pd
from src.strategy.signals import Signal, Action
from src.utils.logger import logger


class BollingerBandsStrategy:
    """Bollinger Bands — mean reversion + breakout hybrid."""

    NAME = "Bollinger_Bands"

    def generate(self, df: pd.DataFrame, symbol: str) -> Signal:
        if len(df) < 2:
            return self._hold(symbol, df, ["Insufficient data"])

        latest = df.iloc[-1]
        price  = float(latest["close"])
        reasons = []
        confidence = 0.0
        action = Action.HOLD

        # Pull band values
        bb_upper  = float(latest["bb_upper"])  if not pd.isna(latest.get("bb_upper"))  else None
        bb_lower  = float(latest["bb_lower"])  if not pd.isna(latest.get("bb_lower"))  else None
        bb_middle = float(latest["bb_middle"]) if not pd.isna(latest.get("bb_middle")) else None
        bb_width  = float(latest["bb_width"])  if not pd.isna(latest.get("bb_width"))  else None

        if not all([bb_upper, bb_lower, bb_middle]):
            return self._hold(symbol, df, ["Bollinger Bands not ready"])

        # BB position: where is price within the bands?
        band_range = bb_upper - bb_lower
        bb_position = (price - bb_lower) / band_range if band_range > 0 else 0.5
        # 0.0 = at lower band, 0.5 = at middle, 1.0 = at upper band

        squeeze = bool(latest.get("bb_squeeze", False))
        vol_ratio = float(latest.get("volume_ratio", 1.0)) if not pd.isna(latest.get("volume_ratio")) else 1.0
        rsi = float(latest.get("rsi", 50)) if not pd.isna(latest.get("rsi")) else 50.0

        # ── Mode detection ────────────────────────────────────────
        if squeeze:
            reasons.append("⚡ BB Squeeze detected — breakout mode active")
            mode = "breakout"
        else:
            mode = "mean_reversion"

        # ── Mean Reversion Mode ───────────────────────────────────
        if mode == "mean_reversion":
            if bb_position <= 0.05:  # Price at or below lower band
                action = Action.BUY
                confidence = 0.50
                reasons.append(f"Price at lower BB band — expect bounce up")

                # RSI confirmation
                if rsi < 35:
                    confidence += 0.20
                    reasons.append(f"RSI={rsi:.1f} confirms oversold")

                # How far below the band?
                pct_below = (bb_lower - price) / bb_lower * 100
                if pct_below > 1.0:
                    confidence += 0.10
                    reasons.append(f"Price {pct_below:.1f}% below lower band — extreme")

            elif bb_position >= 0.95:  # Price at or above upper band
                action = Action.SELL
                confidence = 0.50
                reasons.append(f"Price at upper BB band — expect pullback")

                if rsi > 65:
                    confidence += 0.20
                    reasons.append(f"RSI={rsi:.1f} confirms overbought")

                pct_above = (price - bb_upper) / bb_upper * 100
                if pct_above > 1.0:
                    confidence += 0.10
                    reasons.append(f"Price {pct_above:.1f}% above upper band — extreme")

            elif bb_position < 0.35:
                # Below middle — mild buy
                action = Action.BUY
                confidence = 0.20
                reasons.append("Price below BB midline — mild bullish bias")
            else:
                reasons.append(f"Price in middle of bands (pos={bb_position:.2f}) — no signal")

        # ── Breakout Mode ─────────────────────────────────────────
        else:
            if bool(latest.get("bb_breakout_up", False)):
                if vol_ratio > 1.5:
                    action = Action.BUY
                    confidence = 0.65
                    reasons.append(f"Breakout above upper BB with {vol_ratio:.1f}x volume! 🚀")
                else:
                    action = Action.BUY
                    confidence = 0.40
                    reasons.append("Breakout above upper BB (low volume — watch carefully)")

            elif bool(latest.get("bb_breakout_down", False)):
                if vol_ratio > 1.5:
                    action = Action.SELL
                    confidence = 0.65
                    reasons.append(f"Breakdown below lower BB with {vol_ratio:.1f}x volume! 📉")
                else:
                    action = Action.SELL
                    confidence = 0.40
                    reasons.append("Breakdown below lower BB (low volume — watch carefully)")
            else:
                reasons.append("Squeeze active but no breakout yet — waiting")

        # ── EMA trend filter ──────────────────────────────────────
        # Don't buy if long-term trend is down, don't sell if trend is up
        if "ema_200" in df.columns and not pd.isna(latest.get("ema_200")):
            ema200 = float(latest["ema_200"])
            if action == Action.BUY and price < ema200 * 0.95:
                confidence *= 0.7  # Reduce confidence — buying into downtrend
                reasons.append("⚠️ Price below EMA200 — counter-trend buy, reduce size")
            elif action == Action.SELL and price > ema200 * 1.05:
                confidence *= 0.7
                reasons.append("⚠️ Price above EMA200 — counter-trend sell, reduce size")

        confidence = min(confidence, 1.0)

        # ── Stop loss / take profit ───────────────────────────────
        stop_loss = take_profit = None
        if "atr" in df.columns and not pd.isna(latest.get("atr")):
            atr = float(latest["atr"])
            if action == Action.BUY:
                stop_loss   = round(price - 1.5 * atr, 2)
                take_profit = round(bb_middle, 2)  # Target: mean reversion to middle
            elif action == Action.SELL:
                stop_loss   = round(price + 1.5 * atr, 2)
                take_profit = round(bb_middle, 2)

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
