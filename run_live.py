"""
实盘启动脚本

用法:
    1. 将策略文件放入 strategies/ 目录
    2. 修改下方 "=== 仅需修改此处 ===" 部分的配置（策略 + 交易所网关）
    3. 运行: python run_live.py
    4. Ctrl+C 优雅退出
"""

import signal
import sys
from decimal import Decimal

from nautilus_trader.config import ImportableStrategyConfig, LiveExecEngineConfig
from nautilus_trader.live.config import TradingNodeConfig
from nautilus_trader.live.node import TradingNode

# ============================================================================
# === 仅需修改此处 ===
# ============================================================================

# 策略配置（替换 strategy_path / config_path 即可切换策略）
STRATEGY = ImportableStrategyConfig(
    strategy_path="strategies.ema_cross:EMACross",
    config_path="strategies.ema_cross:EMACrossConfig",
    config={
        "instrument_id": "BTCUSDT.BINANCE",
        "bar_type": "BTCUSDT.BINANCE-1-HOUR-LAST-EXTERNAL",
        "trade_size": Decimal("0.01"),
        "fast_ema_period": 10,
        "slow_ema_period": 20,
    },
)

# 执行引擎配置
EXEC_ENGINE = LiveExecEngineConfig(
    reconciliation=True,  # 启动时与交易所对账
    inflight_check_interval_ms=5000,  # 待确认订单检查间隔
)

# 交易所网关配置（根据实际交易所取消注释并填写）
# ---------------------------------------------------------------------------
# 示例：Binance
#
# NautilusTrader Binance 适配器已封装的数据源：
#   - K 线 (klines)            -> Bar
#   - 订单簿深度 (depth)       -> OrderBook
#   - 逐笔/聚合成交 (trades)   -> TradeTick / QuoteTick
#   - 24h 统计 (ticker/24hr)   -> 涨跌幅、成交量、加权均价 (Bar 附带)
#   - 资金费率 (fundingRate)   -> 仅 U 本位/币本位合约
#   - 持仓量 (openInterest)    -> 仅合约
#
# account_type 可选值：
#   "SPOT"          现货
#   "MARGIN"        杠杆账户
#   "FUTURES_USDT"  U 本位合约 (fapi)
#   "FUTURES_COIN"  币本位合约 (dapi)
#
# 多因子策略替代指标：
#   换手率  -> 24h 成交量 / N 日均量  (ticker/24hr.volume)
#   动量    -> 24h priceChangePercent (ticker/24hr.priceChangePercent)
#   拥挤度  -> 持仓量变化率 / 资金费率极端值 (仅合约)
#   市值    -> 需调外部 API (CoinGecko / CoinMarketCap)，示例如下：
#
#   import requests
#   caps = requests.get(
#       "https://api.coingecko.com/api/v3/coins/markets",
#       params={"vs_currency": "usd", "order": "market_cap_desc", "per_page": 100}
#   ).json()
#
# from nautilus_trader.adapters.binance import (
#     BinanceLiveExecClientConfig,
#     BinanceLiveDataClientConfig,
# )
# DATA_CLIENT = {"BINANCE": BinanceLiveDataClientConfig(
#     api_key="YOUR_API_KEY",
#     api_secret="YOUR_SECRET",
#     account_type="SPOT",   # <-- 根据需求切换
# )}
# EXEC_CLIENT = {"BINANCE": BinanceLiveExecClientConfig(
#     api_key="YOUR_API_KEY",
#     api_secret="YOUR_SECRET",
#     account_type="SPOT",
# )}
# ---------------------------------------------------------------------------

DATA_CLIENTS = {}
EXEC_CLIENTS = {}

# ============================================================================


def main():
    config = TradingNodeConfig(
        exec_engine=EXEC_ENGINE,
        strategies=[STRATEGY],
        data_clients=DATA_CLIENTS,
        exec_clients=EXEC_CLIENTS,
    )

    node = TradingNode(config=config)

    def shutdown(_signum, _frame):
        print("\n[shutdown] Stopping trading node...")
        node.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print("[main] Trading node starting... (Ctrl+C to stop)")
    node.run()
    print("[main] Trading node stopped.")


if __name__ == "__main__":
    main()
