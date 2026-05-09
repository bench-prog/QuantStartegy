"""
回测启动脚本（BacktestEngine 直接加载数据）

用法:
    1. 将策略文件放入 strategies/ 目录
    2. 修改下方 "=== 仅需修改此处 ===" 部分的配置
    3. 运行: python run_backtest.py
"""

from decimal import Decimal

import pandas as pd
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.config import BacktestEngineConfig, LoggingConfig
from nautilus_trader.model import TraderId
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.data import BarType
from nautilus_trader.model.enums import AccountType, OmsType
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.objects import Money
from nautilus_trader.persistence.wranglers import BarDataWrangler
from nautilus_trader.test_kit.providers import TestInstrumentProvider

from strategies.trend_following.ema_cross import EMACross, EMACrossConfig

# --- 趋势跟踪 (Trend Following) ---
# from strategies.trend_following.supertrend import SuperTrend, SuperTrendConfig

# --- 均值回归 (Mean Reversion) ---
# from strategies.mean_reversion.grid_trading import GridTrading, GridTradingConfig

# --- 聪明钱策略 (Smart Money) ---
# from strategies.smart_money.order_block import OrderBlock, OrderBlockConfig
# from strategies.smart_money.fvg_gap import FVGGap, FVGConfig
# from strategies.smart_money.liquidity_sweep import LiquiditySweep, LiquiditySweepConfig
# from strategies.smart_money.on_chain_analysis import OnChainAnalysis, OnChainAnalysisConfig  # 需链上数据

# --- 跨品种策略 (Cross-Sectional) ---
# from strategies.cross_sectional.funding_rate_arbitrage import FundingRateArbitrage, FundingRateArbitrageConfig  # 需资金费率
# from strategies.cross_sectional.basis_trading import BasisTrading, BasisTradingConfig  # 需期货+现货
# from strategies.cross_sectional.triangular_arbitrage import TriangularArbitrage, TriangularArbitrageConfig  # 需三对行情

# --- 波动率策略 (Volatility) ---
# from strategies.volatility.volatility_cone import VolatilityCone, VolatilityConeConfig  # 需期权IV

# --- 形态识别 (Pattern Recognition) ---
# from strategies.pattern_recognition.event_driven import EventDriven, EventDrivenConfig  # 需事件日历

# --- 订单簿深度 (Orderbook Depth) ---
# from strategies.orderbook_depth.market_maker import MarketMaker, MarketMakerConfig  # 需L2订单簿


# ============================================================================
# === 仅需修改此处 ===
# ============================================================================

# 数据源配置
DATA_CSV = "data/fxcm/gbpusd-m1-ask-2012.csv"  # CSV 文件路径
CURRENCY_PAIR = "GBP/USD"  # 货币对
VENUE_NAME = "SIM"  # 交易所名称

# 策略配置（替换导入即可切换策略）
STRATEGY_CLS = EMACross
CONFIG_CLS = EMACrossConfig
STRATEGY_PARAMS = {
    "trade_size": Decimal("100000"),
    "fast_ema_period": 10,
    "slow_ema_period": 20,
}

# ============================================================================


def main():
    # 1. 配置引擎
    engine_config = BacktestEngineConfig(
        trader_id=TraderId("BACKTEST-001"),
        logging=LoggingConfig(log_level="INFO"),
    )
    engine = BacktestEngine(config=engine_config)

    # 2. 配置交易所
    venue = Venue(VENUE_NAME)
    engine.add_venue(
        venue=venue,
        oms_type=OmsType.HEDGING,
        account_type=AccountType.MARGIN,
        starting_balances=[Money(1_000_000, USD)],
        base_currency=USD,
    )

    # 3. 创建合约
    instrument = TestInstrumentProvider.default_fx_ccy(
        CURRENCY_PAIR,
        venue=venue,
    )
    engine.add_instrument(instrument)

    # 4. 加载数据
    df = pd.read_csv(DATA_CSV, index_col="timestamp", parse_dates=True)
    bar_type = BarType.from_str(f"{instrument.id}-1-MINUTE-LAST-EXTERNAL")
    wrangler = BarDataWrangler(bar_type, instrument)
    bars = wrangler.process(df)
    engine.add_data(bars)

    print(f"Loaded {len(bars)} bars from {DATA_CSV}")

    # 5. 创建策略
    config = CONFIG_CLS(
        instrument_id=instrument.id,
        bar_type=bar_type,
        **STRATEGY_PARAMS,
    )
    strategy = STRATEGY_CLS(config)
    engine.add_strategy(strategy)

    # 6. 运行回测
    engine.run()

    # 7. 打印结果
    print("\n" + "=" * 60)
    print("Backtest completed")
    print(f"Iterations    : {engine.iteration}")
    print(f"Total orders  : {len(engine.cache.orders())}")
    print(f"Total positions: {len(engine.cache.positions())}")
    print(f"Account       : {engine.portfolio.account(venue)}")
    print("=" * 60)

    # 8. 释放资源
    engine.dispose()


if __name__ == "__main__":
    main()
