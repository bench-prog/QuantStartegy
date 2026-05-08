"""
单策略回测脚本 — 由 batch_backtest.py 通过 subprocess 调用
用法: python backtest_one.py <strategy_key>
"""

import json
import sys
import time
from decimal import Decimal

import pandas as pd
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.config import BacktestEngineConfig, LoggingConfig
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.data import BarType
from nautilus_trader.model import TraderId
from nautilus_trader.model.enums import AccountType, OmsType
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.objects import Money
from nautilus_trader.persistence.wranglers import BarDataWrangler
from nautilus_trader.test_kit.providers import TestInstrumentProvider

# ── 趋势跟踪 ──
from strategies.trend_following.ema_cross import EMACross, EMACrossConfig
from strategies.trend_following.donchian_breakout import DonchianBreakout, DonchianBreakoutConfig
from strategies.trend_following.roc_momentum import ROCMomentum, ROCMomentumConfig
from strategies.trend_following.supertrend import SuperTrend, SuperTrendConfig

# ── 均值回归 ──
from strategies.mean_reversion.bollinger_reversion import BollingerReversion, BollingerReversionConfig
from strategies.mean_reversion.grid_trading import GridTrading, GridTradingConfig
from strategies.mean_reversion.rsi_reversion import RSIReversion, RSIReversionConfig

# ── 波动率 ──
from strategies.volatility.atr_trailing_stop import ATRTrailingStop, ATRTrailingStopConfig
from strategies.volatility.keltner_breakout import KeltnerBreakout, KeltnerBreakoutConfig

# ── 形态识别 ──
from strategies.pattern_recognition.engulfing_pattern import EngulfingPattern, EngulfingPatternConfig


DATA_CSV = "data/fxcm/gbpusd-m1-ask-2012.csv"
CURRENCY_PAIR = "GBP/USD"
VENUE_NAME = "SIM"
STARTING_CAPITAL = 1_000_000
DEFAULT_TRADE_SIZE = Decimal("100000")

STRATEGIES = {
    "ema_cross": (EMACross, EMACrossConfig, {"trade_size": DEFAULT_TRADE_SIZE, "fast_ema_period": 10, "slow_ema_period": 20}),
    "donchian_breakout": (DonchianBreakout, DonchianBreakoutConfig, {"trade_size": DEFAULT_TRADE_SIZE, "period": 20}),
    "roc_momentum": (ROCMomentum, ROCMomentumConfig, {"trade_size": DEFAULT_TRADE_SIZE, "roc_period": 10, "threshold": Decimal("0.0")}),
    "supertrend": (SuperTrend, SuperTrendConfig, {"trade_size": DEFAULT_TRADE_SIZE, "atr_period": 10, "multiplier": Decimal("3.0")}),
    "bollinger_reversion": (BollingerReversion, BollingerReversionConfig, {"trade_size": DEFAULT_TRADE_SIZE, "period": 20, "std_dev": Decimal("2.0")}),
    "grid_trading": (GridTrading, GridTradingConfig, {"trade_size": DEFAULT_TRADE_SIZE, "grid_lower": Decimal("1.55"), "grid_upper": Decimal("1.60"), "grid_count": 10, "max_position_grids": 5}),
    "rsi_reversion": (RSIReversion, RSIReversionConfig, {"trade_size": DEFAULT_TRADE_SIZE, "period": 14, "overbought": Decimal("70"), "oversold": Decimal("30")}),
    "atr_trailing_stop": (ATRTrailingStop, ATRTrailingStopConfig, {"trade_size": DEFAULT_TRADE_SIZE, "atr_period": 14, "atr_mult": Decimal("3.0")}),
    "keltner_breakout": (KeltnerBreakout, KeltnerBreakoutConfig, {"trade_size": DEFAULT_TRADE_SIZE, "ema_period": 20, "atr_period": 14, "atr_mult": Decimal("2.0")}),
    "engulfing_pattern": (EngulfingPattern, EngulfingPatternConfig, {"trade_size": DEFAULT_TRADE_SIZE, "use_trend_filter": True}),
}


def main():
    key = sys.argv[1]
    name = sys.argv[2] if len(sys.argv) > 2 else key
    strategy_cls, config_cls, params = STRATEGIES[key]

    t0 = time.perf_counter()

    engine_config = BacktestEngineConfig(
        trader_id=TraderId(f"BT-{key[:8].upper()}"),
        logging=LoggingConfig(log_level="WARNING"),
    )
    engine = BacktestEngine(config=engine_config)

    venue = Venue(VENUE_NAME)
    engine.add_venue(
        venue=venue,
        oms_type=OmsType.HEDGING,
        account_type=AccountType.MARGIN,
        starting_balances=[Money(STARTING_CAPITAL, USD)],
        base_currency=USD,
    )

    instrument = TestInstrumentProvider.default_fx_ccy(CURRENCY_PAIR, venue=venue)
    engine.add_instrument(instrument)

    df = pd.read_csv(DATA_CSV, index_col="timestamp", parse_dates=True)
    bar_type = BarType.from_str(f"{instrument.id}-1-MINUTE-LAST-EXTERNAL")
    wrangler = BarDataWrangler(bar_type, instrument)
    bars = wrangler.process(df)
    engine.add_data(bars)

    config = config_cls(instrument_id=instrument.id, bar_type=bar_type, **params)
    strategy = strategy_cls(config)
    engine.add_strategy(strategy)

    try:
        engine.run()
        account = engine.portfolio.account(venue)
        balances = account.balances()  # dict[Currency, AccountBalance]
        total = float(sum(b.total.as_double() for b in balances.values())) if balances else 0.0
        result = {
            "name": name,
            "bars": len(bars),
            "orders": len(engine.cache.orders()),
            "positions": len(engine.cache.positions()),
            "pnl": total - STARTING_CAPITAL,
            "elapsed": round(time.perf_counter() - t0, 2),
            "status": "ok",
        }
    except Exception as e:
        result = {
            "name": name,
            "bars": len(bars),
            "orders": 0,
            "positions": 0,
            "pnl": None,
            "elapsed": round(time.perf_counter() - t0, 2),
            "status": "error",
            "note": str(e)[:200],
        }
    finally:
        engine.dispose()

    print(json.dumps(result))


if __name__ == "__main__":
    main()
