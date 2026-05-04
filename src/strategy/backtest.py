"""
src/strategy/backtest.py
─────────────────────────
Backtesting engine using Backtrader.
Tests each strategy against 1 year of historical data
and produces performance metrics.

Metrics reported:
  - Total Return %
  - Win Rate %
  - Max Drawdown %
  - Sharpe Ratio
  - Total Trades
  - Avg Profit per Trade

Usage:
    from src.strategy.backtest import run_backtest
    results = run_backtest("RELIANCE.NS", strategy="EMA_Crossover", timeframe="1d")
    print(results)
"""

import backtrader as bt
import pandas as pd
import numpy as np
from datetime import datetime

from src.strategy.indicators import add_indicators
from src.data.fetcher import DataFetcher
from src.utils.logger import logger


# ── Backtrader Strategy Wrappers ──────────────────────────────────

class BTEMACrossover(bt.Strategy):
    """Backtrader wrapper for EMA Crossover strategy."""
    params = dict(ema_fast=20, ema_slow=50, atr_mult_sl=2.0, atr_mult_tp=3.0)

    def __init__(self):
        self.ema_fast = bt.indicators.EMA(period=self.p.ema_fast)
        self.ema_slow = bt.indicators.EMA(period=self.p.ema_slow)
        self.atr      = bt.indicators.ATR(period=14)
        self.crossup  = bt.indicators.CrossUp(self.ema_fast, self.ema_slow)
        self.crossdn  = bt.indicators.CrossDown(self.ema_fast, self.ema_slow)
        self.order    = None
        self.stop_price = None
        self.trades   = []

    def next(self):
        if self.order:
            return

        if not self.position:
            if self.crossup[0]:
                self.order = self.buy()
                self.stop_price = self.data.close[0] - self.p.atr_mult_sl * self.atr[0]
        else:
            # Exit: death cross or stop loss hit
            if self.crossdn[0] or self.data.close[0] < self.stop_price:
                self.order = self.sell()

    def notify_order(self, order):
        if order.status in [order.Completed]:
            self.order = None

    def notify_trade(self, trade):
        if trade.isclosed:
            self.trades.append({
                "pnl": trade.pnl,
                "pnlcomm": trade.pnlcomm,
                "entry": trade.price,
            })


class BTRSIMACDStrategy(bt.Strategy):
    """Backtrader wrapper for RSI + MACD strategy."""
    params = dict(rsi_period=14, rsi_buy=35, rsi_sell=65,
                  macd_fast=12, macd_slow=26, macd_signal=9)

    def __init__(self):
        self.rsi       = bt.indicators.RSI(period=self.p.rsi_period)
        self.macd      = bt.indicators.MACD(
            period_me1=self.p.macd_fast,
            period_me2=self.p.macd_slow,
            period_signal=self.p.macd_signal,
        )
        self.atr       = bt.indicators.ATR(period=14)
        self.order     = None
        self.trades    = []

    def next(self):
        if self.order:
            return

        macd_cross_up = (self.macd.macd[0] > self.macd.signal[0] and
                         self.macd.macd[-1] <= self.macd.signal[-1])
        macd_cross_dn = (self.macd.macd[0] < self.macd.signal[0] and
                         self.macd.macd[-1] >= self.macd.signal[-1])

        if not self.position:
            if self.rsi[0] < self.p.rsi_buy and macd_cross_up:
                self.order = self.buy()
        else:
            if self.rsi[0] > self.p.rsi_sell or macd_cross_dn:
                self.order = self.sell()

    def notify_order(self, order):
        if order.status in [order.Completed]:
            self.order = None

    def notify_trade(self, trade):
        if trade.isclosed:
            self.trades.append({"pnl": trade.pnl, "pnlcomm": trade.pnlcomm})


# ── Main backtest runner ──────────────────────────────────────────

STRATEGY_MAP = {
    "EMA_Crossover": BTEMACrossover,
    "RSI_MACD":      BTRSIMACDStrategy,
}


def run_backtest(
    symbol: str,
    strategy_name: str = "EMA_Crossover",
    timeframe: str = "1d",
    initial_cash: float = 100_000,
    commission: float = 0.001,   # 0.1% — typical for Zerodha/Binance
) -> dict:
    """
    Run a backtest for a strategy on a symbol.

    Args:
        symbol        : e.g. "RELIANCE.NS"
        strategy_name : "EMA_Crossover" | "RSI_MACD"
        timeframe     : "1d" | "1h"
        initial_cash  : starting capital in ₹ or $
        commission    : fraction per trade (0.001 = 0.1%)

    Returns:
        Dict with performance metrics
    """
    if strategy_name not in STRATEGY_MAP:
        raise ValueError(f"Unknown strategy '{strategy_name}'. Valid: {list(STRATEGY_MAP)}")

    # Load data
    fetcher = DataFetcher()
    df = fetcher.get_candles(symbol, timeframe=timeframe, limit=500)

    if df.empty or len(df) < 60:
        return {"error": f"Not enough data for {symbol} [{timeframe}]"}

    df = df.reset_index()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df.set_index("timestamp", inplace=True)
    df.sort_index(inplace=True)

    # Convert to Backtrader feed
    data_feed = bt.feeds.PandasData(
        dataname=df,
        datetime=None,   # index is already datetime
        open="open",
        high="high",
        low="low",
        close="close",
        volume="volume",
        openinterest=-1,
    )

    # Set up Cerebro
    cerebro = bt.Cerebro()
    cerebro.adddata(data_feed)
    cerebro.addstrategy(STRATEGY_MAP[strategy_name])
    cerebro.broker.setcash(initial_cash)
    cerebro.broker.setcommission(commission=commission)
    cerebro.addsizer(bt.sizers.PercentSizer, percents=95)  # Use 95% of available cash

    # Add analyser
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe", riskfreerate=0.06)
    cerebro.addanalyzer(bt.analyzers.DrawDown,    _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
    cerebro.addanalyzer(bt.analyzers.Returns,     _name="returns")

    # Run
    logger.info(f"Running backtest: {strategy_name} on {symbol} [{timeframe}]")
    start_value = cerebro.broker.getvalue()

    try:
        results = cerebro.run()
    except Exception as e:
        return {"error": str(e)}

    strat = results[0]
    end_value = cerebro.broker.getvalue()

    # Extract metrics
    total_return_pct = ((end_value - start_value) / start_value) * 100

    try:
        sharpe = strat.analyzers.sharpe.get_analysis().get("sharperatio") or 0.0
    except:
        sharpe = 0.0

    try:
        dd = strat.analyzers.drawdown.get_analysis()
        max_drawdown = dd.get("max", {}).get("drawdown", 0.0)
    except:
        max_drawdown = 0.0

    try:
        trade_analysis = strat.analyzers.trades.get_analysis()
        total_trades = int(trade_analysis.get("total", {}).get("closed", 0))
        won  = int(trade_analysis.get("won",  {}).get("total", 0))
        lost = int(trade_analysis.get("lost", {}).get("total", 0))
        win_rate = (won / total_trades * 100) if total_trades > 0 else 0.0
        avg_win  = float(trade_analysis.get("won",  {}).get("pnl", {}).get("average", 0))
        avg_loss = float(trade_analysis.get("lost", {}).get("pnl", {}).get("average", 0))
    except:
        total_trades = won = lost = 0
        win_rate = avg_win = avg_loss = 0.0

    metrics = {
        "symbol":          symbol,
        "strategy":        strategy_name,
        "timeframe":       timeframe,
        "initial_capital": initial_cash,
        "final_value":     round(end_value, 2),
        "total_return_pct":round(total_return_pct, 2),
        "max_drawdown_pct":round(max_drawdown, 2),
        "sharpe_ratio":    round(float(sharpe or 0), 3),
        "total_trades":    total_trades,
        "winning_trades":  won,
        "losing_trades":   lost,
        "win_rate_pct":    round(win_rate, 1),
        "avg_win":         round(avg_win, 2),
        "avg_loss":        round(avg_loss, 2),
    }

    # Pretty print
    logger.success(f"\n{'─'*45}")
    logger.success(f"  BACKTEST RESULTS: {strategy_name} | {symbol}")
    logger.success(f"{'─'*45}")
    for k, v in metrics.items():
        logger.success(f"  {k:<22}: {v}")
    logger.success(f"{'─'*45}")

    return metrics


def run_all_backtests(
    symbols: list = None,
    strategies: list = None,
    timeframe: str = "1d",
) -> pd.DataFrame:
    """
    Run all strategy/symbol combinations and return a comparison table.

    Returns:
        DataFrame sorted by total_return_pct descending
    """
    symbols    = symbols    or ["RELIANCE.NS", "TCS.NS", "BTCUSDT", "ETHUSDT"]
    strategies = strategies or ["EMA_Crossover", "RSI_MACD"]

    all_results = []
    for symbol in symbols:
        for strategy in strategies:
            result = run_backtest(symbol, strategy, timeframe)
            if "error" not in result:
                all_results.append(result)

    if not all_results:
        return pd.DataFrame()

    df = pd.DataFrame(all_results)
    df.sort_values("total_return_pct", ascending=False, inplace=True)
    return df
