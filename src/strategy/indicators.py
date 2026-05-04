"""
src/strategy/indicators.py
───────────────────────────
Technical indicator calculator.
Takes a raw OHLCV DataFrame and adds indicator columns.

Indicators included:
  - EMA   (Exponential Moving Average) — trend direction
  - RSI   (Relative Strength Index)    — overbought/oversold
  - MACD  (Moving Avg Convergence Div) — momentum + trend
  - BB    (Bollinger Bands)            — volatility + breakout
  - ATR   (Average True Range)         — volatility measure (used in risk mgmt)
  - Volume MA                          — volume trend

Usage:
    from src.strategy.indicators import add_indicators
    df = add_indicators(df)
    # df now has columns: ema_20, ema_50, rsi, macd, macd_signal, bb_upper, etc.
"""

import pandas as pd
import pandas_ta as ta
from src.utils.logger import logger


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add all technical indicators to a candle DataFrame.

    Args:
        df: DataFrame with columns open, high, low, close, volume
            (index should be timestamp or a timestamp column present)

    Returns:
        Same DataFrame with indicator columns added.
        Rows with insufficient history (NaN indicators) are dropped.
    """
    if df.empty:
        logger.warning("add_indicators called on empty DataFrame")
        return df

    df = df.copy()

    # Ensure we have a clean numeric index for pandas-ta
    if "timestamp" in df.columns:
        df = df.set_index("timestamp")
    df.index = pd.to_datetime(df.index)
    df.sort_index(inplace=True)

    # ── Trend: EMA ────────────────────────────────────────────────
    # EMA 20  — short-term trend
    # EMA 50  — medium-term trend
    # EMA 200 — long-term trend (golden/death cross)
    df["ema_20"]  = ta.ema(df["close"], length=20)
    df["ema_50"]  = ta.ema(df["close"], length=50)
    df["ema_200"] = ta.ema(df["close"], length=200)

    # ── Momentum: RSI ─────────────────────────────────────────────
    # RSI 14 — standard period
    # < 30 = oversold (potential buy)
    # > 70 = overbought (potential sell)
    df["rsi"] = ta.rsi(df["close"], length=14)

    # ── Momentum + Trend: MACD ────────────────────────────────────
    # MACD line    = EMA12 - EMA26
    # Signal line  = EMA9 of MACD
    # Histogram    = MACD - Signal (shows momentum direction)
    macd = ta.macd(df["close"], fast=12, slow=26, signal=9)
    if macd is not None and not macd.empty:
        df["macd"]          = macd["MACD_12_26_9"]
        df["macd_signal"]   = macd["MACDs_12_26_9"]
        df["macd_histogram"]= macd["MACDh_12_26_9"]

    # ── Volatility: Bollinger Bands ───────────────────────────────
    # Middle band  = SMA 20
    # Upper band   = SMA20 + 2 * std
    # Lower band   = SMA20 - 2 * std
    # Price touching upper = overbought, lower = oversold
    bb = ta.bbands(df["close"], length=20, std=2)
    if bb is not None and not bb.empty:
        bb_col = [c for c in bb.columns if c.startswith("BBU")][0]
        bc_col = [c for c in bb.columns if c.startswith("BBM")][0]
        bl_col = [c for c in bb.columns if c.startswith("BBL")][0]
        df["bb_upper"]  = bb[bb_col]
        df["bb_middle"] = bb[bc_col]
        df["bb_lower"]  = bb[bl_col]
        df["bb_width"]  = (df["bb_upper"] - df["bb_lower"]) / df["bb_middle"]

    # ── Volatility: ATR ───────────────────────────────────────────
    # Average True Range — used for stop-loss sizing
    df["atr"] = ta.atr(df["high"], df["low"], df["close"], length=14)

    # ── Volume: Moving Average ────────────────────────────────────
    df["volume_ma_20"] = ta.sma(df["volume"], length=20)
    df["volume_ratio"] = df["volume"] / df["volume_ma_20"]  # >1.5 = high volume

    # ── Derived signals (used by strategies) ─────────────────────
    # EMA crossover flags
    df["ema_bullish"] = df["ema_20"] > df["ema_50"]   # short above long = uptrend
    df["ema_cross_up"]   = (df["ema_20"] > df["ema_50"]) & (df["ema_20"].shift(1) <= df["ema_50"].shift(1))
    df["ema_cross_down"] = (df["ema_20"] < df["ema_50"]) & (df["ema_20"].shift(1) >= df["ema_50"].shift(1))

    # MACD crossover flags
    df["macd_cross_up"]   = (df["macd"] > df["macd_signal"]) & (df["macd"].shift(1) <= df["macd_signal"].shift(1))
    df["macd_cross_down"] = (df["macd"] < df["macd_signal"]) & (df["macd"].shift(1) >= df["macd_signal"].shift(1))

    # RSI zones
    df["rsi_oversold"]   = df["rsi"] < 30
    df["rsi_overbought"] = df["rsi"] > 70
    df["rsi_neutral"]    = (df["rsi"] >= 30) & (df["rsi"] <= 70)

    # BB breakout flags
    df["bb_breakout_up"]   = df["close"] > df["bb_upper"]
    df["bb_breakout_down"] = df["close"] < df["bb_lower"]
    _bb_rolling = df["bb_width"].rolling(50).mean()
    df["bb_squeeze"] = df["bb_width"].lt(_bb_rolling * 0.5).fillna(False)

    # Drop rows where core indicators are NaN (not enough history yet)
    core_cols = ["ema_20", "ema_50", "rsi", "macd"]
    existing = [c for c in core_cols if c in df.columns]
    before = len(df)
    df.dropna(subset=existing, inplace=True)
    dropped = before - len(df)
    if dropped:
        logger.debug(f"Dropped {dropped} rows (insufficient indicator history)")

    df.reset_index(inplace=True)
    return df
