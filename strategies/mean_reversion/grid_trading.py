# ============================================================================
# 策略名称：Grid Trading / 网格交易
# 分类：    均值回归 (mean_reversion)
# 状态：    skeleton
# 作者：    cheristerfer
# 日期：    2026-05-08
# ============================================================================
# 概述：
#   在预设价格区间内等距划分网格档位，价格下跌穿越一档时买入、上涨穿越一档时
#   卖出，适合加密货币高波动、长期横盘的震荡行情。
#
# 数据依赖：N/A（仅需 OHLCV Bar）
#
# 参数：
#   instrument_id     — 合约
#   bar_type          — K 线类型
#   trade_size        — 每格下单数量（默认 100000）
#   grid_lower        — 网格下界
#   grid_upper        — 网格上界
#   grid_count        — 网格档位数（默认 20）
#   max_position_grids — 最大持仓档位（默认 5）
#
# TODO：
#   - [ ] 实盘改用限价单挂单价差两侧
#   - [ ] 单边突破区间时自动停止或重置网格
#   - [ ] 动态调整网格间距（基于波动率）
#
# 参考：
#   - N/A
# ============================================================================

from decimal import Decimal

from nautilus_trader.common.enums import LogColor
from nautilus_trader.config import PositiveInt, StrategyConfig
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.trading.strategy import Strategy

from strategies import StrategyMeta, register


class GridTradingConfig(StrategyConfig, frozen=True):
    instrument_id: InstrumentId
    bar_type: BarType
    trade_size: Decimal
    grid_lower: Decimal
    grid_upper: Decimal
    grid_count: PositiveInt = 10
    max_position_grids: PositiveInt = 5
    order_time_in_force: TimeInForce = TimeInForce.GTC


class GridTrading(Strategy):
    """
    网格交易策略。

    核心逻辑：
    -  在 [grid_lower, grid_upper] 区间内等距划分 grid_count 个网格档位。
    -  价格下跌穿越一个档位时买入一档，价格上涨穿越一个档位时卖出一档。
    -  适合加密货币高波动、长期横盘的行情特征。

    参数说明：
    -  grid_lower / grid_upper: 网格区间下界和上界
    -  grid_count: 网格档位数量
    -  max_position_grids: 最大持仓档位数量，控制单边风险敞口

    注意：
    -  本策略使用市价单在 bar 收盘时触发，实盘建议改用限价单挂单价差两侧。
    -  单边突破 grid_upper / grid_lower 时停止开新仓。
    """

    def __init__(self, config: GridTradingConfig) -> None:
        super().__init__(config)
        self.instrument: Instrument = None
        self.grid_step: float = 0.0
        self.grids: list[float] = []
        self.position_grids: dict[int, float] = {}  # grid_idx -> entry_price
        self.prev_bar_close: float | None = None

    def on_start(self) -> None:
        self.instrument = self.cache.instrument(self.config.instrument_id)
        if self.instrument is None:
            self.log.error(f"Could not find instrument for {self.config.instrument_id}")
            self.stop()
            return

        lower = float(self.config.grid_lower)
        upper = float(self.config.grid_upper)
        count = self.config.grid_count

        self.grid_step = (upper - lower) / count
        self.grids = [lower + i * self.grid_step for i in range(count + 1)]

        self.log.info(
            f"Grid initialized: {lower} ~ {upper}, step={self.grid_step:.5f}, grids={len(self.grids)}",
            color=LogColor.BLUE,
        )
        self.subscribe_bars(self.config.bar_type)

    def _nearest_grid_index(self, price: float) -> int:
        lower = float(self.config.grid_lower)
        idx = int((price - lower) / self.grid_step)
        return max(0, min(idx, self.config.grid_count))

    def on_bar(self, bar: Bar) -> None:
        if bar.is_single_price():
            return

        close = float(bar.close)

        if self.prev_bar_close is None:
            self.prev_bar_close = close
            return

        prev_idx = self._nearest_grid_index(self.prev_bar_close)
        curr_idx = self._nearest_grid_index(close)

        # 价格下跌，穿越网格档位 → 买入
        if curr_idx > prev_idx:
            for idx in range(prev_idx + 1, curr_idx + 1):
                if idx >= len(self.grids):
                    break
                if len(self.position_grids) >= self.config.max_position_grids:
                    self.log.info("Max position grids reached, skipping buy", color=LogColor.YELLOW)
                    break
                if idx not in self.position_grids:
                    self.position_grids[idx] = close
                    self.buy()
                    self.log.info(f"Grid buy @ level {idx} ({self.grids[idx]:.5f})", color=LogColor.GREEN)

        # 价格上涨，穿越网格档位 → 卖出（平掉对应档位的买入）
        if curr_idx < prev_idx:
            for idx in range(prev_idx - 1, curr_idx - 1, -1):
                if idx < 0:
                    break
                if idx in self.position_grids:
                    del self.position_grids[idx]
                    self.sell()
                    self.log.info(f"Grid sell @ level {idx} ({self.grids[idx]:.5f})", color=LogColor.RED)

        self.prev_bar_close = close

    def buy(self) -> None:
        order = self.order_factory.market(
            instrument_id=self.config.instrument_id,
            order_side=OrderSide.BUY,
            quantity=self.instrument.make_qty(self.config.trade_size),
            time_in_force=self.config.order_time_in_force,
        )
        self.submit_order(order)

    def sell(self) -> None:
        order = self.order_factory.market(
            instrument_id=self.config.instrument_id,
            order_side=OrderSide.SELL,
            quantity=self.instrument.make_qty(self.config.trade_size),
            time_in_force=self.config.order_time_in_force,
        )
        self.submit_order(order)

    def on_stop(self) -> None:
        self.cancel_all_orders(self.config.instrument_id)
        self.close_all_positions(self.config.instrument_id)

    def on_reset(self) -> None:
        self.position_grids.clear()
        self.prev_bar_close = None

    def on_dispose(self) -> None:
        pass


register(
    StrategyMeta(
        key="grid_trading",
        name="Grid Trading",
        description="网格交易策略：在预设区间内低买高卖，适合加密货币高波动横盘行情",
        config_cls=GridTradingConfig,
        strategy_cls=GridTrading,
        default_params={
            "grid_lower": 20000,
            "grid_upper": 40000,
            "grid_count": 20,
            "max_position_grids": 5,
            "trade_size": 100000,
        },
    )
)
