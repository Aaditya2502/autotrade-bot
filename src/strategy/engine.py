"""
src/strategy/engine.py
───────────────────────
Master Strategy Engine.
Runs all 3 strategies on a symbol, combines their signals,
and outputs a final consensus signal.

Usage:
    from src.strategy.engine import StrategyEngine
    engine = StrategyEngine()

    # Get signal for one symbol
    signal = engine.analyse("RELIANCE.NS", timeframe="1d")
    print(signal)

    # Scan entire watchlist
    signals = engine.scan_watchlist(timeframe="1d")
    for s in signals:
        print(s)
"""

import pandas as pd
from src.strategy.indicators import add_indicators
from src.strategy.ema_crossover import EMACrossoverStrategy
from src.strategy.rsi_macd import RSIMACDStrategy
from src.strategy.bollinger_bands import BollingerBandsStrategy
from src.strategy.signals import Signal, Action
from src.data.fetcher import DataFetcher
from src.utils.logger import logger


# Default watchlists
STOCK_WATCHLIST = [
    "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS",
]
CRYPTO_WATCHLIST = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT",
]


class StrategyEngine:
    """
    Runs all strategies on a symbol and returns a consensus signal.
    Higher confidence = more strategies agree.
    """

    def __init__(self):
        self.fetcher   = DataFetcher()
        self.strategies = [
            EMACrossoverStrategy(),
            RSIMACDStrategy(),
            BollingerBandsStrategy(),
        ]

    def analyse(
        self,
        symbol: str,
        timeframe: str = "1d",
        candle_limit: int = 300,
    ) -> Signal:
        """
        Run all strategies on a symbol and return a consensus signal.

        Args:
            symbol       : e.g. "RELIANCE.NS" or "BTCUSDT"
            timeframe    : "1d", "1h", "15m" etc.
            candle_limit : how many recent candles to use

        Returns:
            Final consensus Signal
        """
        # Load candles from DB
        df_raw = self.fetcher.get_candles(symbol, timeframe=timeframe, limit=candle_limit)
        if df_raw.empty:
            logger.warning(f"No candles in DB for {symbol} [{timeframe}] — fetching now")
            self.fetcher.fetch_and_store(symbol, timeframe=timeframe, days=365)
            df_raw = self.fetcher.get_candles(symbol, timeframe=timeframe, limit=candle_limit)

        if df_raw.empty:
            logger.error(f"Still no data for {symbol} — cannot analyse")
            return Signal(symbol=symbol, action=Action.HOLD, confidence=0.0,
                         strategy="None", price=0.0, reasons=["No data available"])

        # Add indicators
        df = add_indicators(df_raw.reset_index())

        if df.empty:
            return Signal(symbol=symbol, action=Action.HOLD, confidence=0.0,
                         strategy="None", price=0.0, reasons=["Insufficient history for indicators"])

        # Run all strategies
        signals = []
        for strategy in self.strategies:
            try:
                sig = strategy.generate(df, symbol)
                signals.append(sig)
            except Exception as e:
                logger.error(f"Strategy {strategy.NAME} failed on {symbol}: {e}")

        # Build consensus
        return self._consensus(signals, symbol)

    def scan_watchlist(
        self,
        stocks: list = None,
        crypto: list = None,
        timeframe: str = "1d",
        min_confidence: float = 0.4,
    ) -> list[Signal]:
        """
        Scan all watchlist symbols and return actionable signals.

        Args:
            min_confidence: only return signals above this threshold

        Returns:
            List of Signals sorted by confidence descending
        """
        stocks = stocks or STOCK_WATCHLIST
        crypto = crypto or CRYPTO_WATCHLIST
        all_symbols = stocks + crypto

        logger.info(f"Scanning {len(all_symbols)} symbols [{timeframe}]...")
        signals = []

        for symbol in all_symbols:
            try:
                signal = self.analyse(symbol, timeframe=timeframe)
                if signal.action != Action.HOLD and signal.confidence >= min_confidence:
                    signals.append(signal)
            except Exception as e:
                logger.error(f"Failed to analyse {symbol}: {e}")

        # Sort by confidence descending
        signals.sort(key=lambda s: s.confidence, reverse=True)

        buys  = [s for s in signals if s.action == Action.BUY]
        sells = [s for s in signals if s.action == Action.SELL]
        logger.success(
            f"Scan complete — {len(buys)} BUY signals, {len(sells)} SELL signals "
            f"(min confidence {min_confidence:.0%})"
        )
        return signals

    def get_summary_table(
        self,
        stocks: list = None,
        crypto: list = None,
        timeframe: str = "1d",
    ) -> pd.DataFrame:
        """
        Return a DataFrame table of all signals — good for the dashboard.
        """
        stocks = stocks or STOCK_WATCHLIST
        crypto = crypto or CRYPTO_WATCHLIST
        all_symbols = stocks + crypto

        rows = []
        for symbol in all_symbols:
            try:
                signal = self.analyse(symbol, timeframe=timeframe)
                rows.append({
                    "symbol":     signal.symbol,
                    "action":     signal.action.value,
                    "confidence": f"{signal.confidence:.0%}",
                    "price":      signal.price,
                    "strategy":   signal.strategy,
                    "stop_loss":  signal.stop_loss,
                    "take_profit":signal.take_profit,
                    "reason":     signal.reasons[0] if signal.reasons else "",
                })
            except Exception as e:
                logger.error(f"Error analysing {symbol}: {e}")

        return pd.DataFrame(rows)

    # ── Private ───────────────────────────────────────────────────

    def _consensus(self, signals: list[Signal], symbol: str) -> Signal:
        """
        Combine multiple strategy signals into one consensus signal.

        Voting rules:
          - Each strategy votes BUY, SELL, or HOLD
          - Confidence-weighted voting
          - If votes are split 2:1, winner gets boosted confidence
          - If all agree, maximum confidence boost
        """
        if not signals:
            return Signal(symbol=symbol, action=Action.HOLD, confidence=0.0,
                         strategy="Consensus", price=0.0, reasons=["No strategies ran"])

        price = signals[0].price

        # Tally weighted votes
        buy_weight  = sum(s.confidence for s in signals if s.action == Action.BUY)
        sell_weight = sum(s.confidence for s in signals if s.action == Action.SELL)
        hold_count  = sum(1 for s in signals if s.action == Action.HOLD)

        buy_votes  = sum(1 for s in signals if s.action == Action.BUY)
        sell_votes = sum(1 for s in signals if s.action == Action.SELL)
        total      = len(signals)

        # Collect all reasons
        all_reasons = []
        for s in signals:
            all_reasons.extend([f"[{s.strategy}] {r}" for r in s.reasons[:2]])

        # Determine consensus
        if buy_weight > sell_weight and buy_votes > 0:
            action = Action.BUY
            base_confidence = buy_weight / total

            # Bonus if multiple strategies agree
            if buy_votes == total:
                base_confidence = min(base_confidence * 1.3, 1.0)
                all_reasons.insert(0, f"✅ ALL {total} strategies say BUY")
            elif buy_votes > total / 2:
                base_confidence = min(base_confidence * 1.1, 1.0)
                all_reasons.insert(0, f"✅ {buy_votes}/{total} strategies say BUY")

        elif sell_weight > buy_weight and sell_votes > 0:
            action = Action.SELL
            base_confidence = sell_weight / total

            if sell_votes == total:
                base_confidence = min(base_confidence * 1.3, 1.0)
                all_reasons.insert(0, f"🔴 ALL {total} strategies say SELL")
            elif sell_votes > total / 2:
                base_confidence = min(base_confidence * 1.1, 1.0)
                all_reasons.insert(0, f"🔴 {sell_votes}/{total} strategies say SELL")

        else:
            action = Action.HOLD
            base_confidence = 0.0
            all_reasons.insert(0, f"Strategies disagree — HOLD is safest")

        # Use best stop_loss / take_profit from highest confidence signal
        best = max(signals, key=lambda s: s.confidence)

        final = Signal(
            symbol=symbol,
            action=action,
            confidence=round(base_confidence, 3),
            strategy="Consensus",
            price=price,
            reasons=all_reasons[:6],  # Keep top 6 reasons
            stop_loss=best.stop_loss,
            take_profit=best.take_profit,
        )

        logger.info(f"\n{'='*55}")
        logger.info(f"CONSENSUS: {final}")
        logger.info(f"{'='*55}")
        return final
