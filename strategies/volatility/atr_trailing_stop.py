# ============================================================================
# 策略名称：ATR Trailing Stop / ATR 追踪止损
# 分类：    波动率 (volatility)
# 状态：    skeleton
# 作者：    cheristerfer
# 日期：    2026-05-08
# ============================================================================
# 概述：
#   以简单方向入场（阳线做多、阴线做空），然后使用 ATR 倍数构建动态追踪止损
#   来管理持仓。多头持仓时止损从最高价回撤 N×ATR，空头反之。侧重出场逻辑
#   而非入场逻辑。
#
# 数据依赖：N/A（仅需 OHLCV Bar）
#
# 参数：
#   instrument_id — 合约
#   bar_type      — K 线类型
#   trade_size    — 下单数量（默认 100000）
#   atr_period    — ATR 周期（默认 14）
#   atr_mult      — ATR 乘数（默认 3.0）
#
# TODO：
#   - [ ] 入场信号增强（结合趋势/动量指标）
#   - [ ] 支持部分止盈（分批平仓）
#
# 参考：
#   - N/A
# ============================================================================

from decimal import Decimal

from nautilus_trader.common.enums import LogColor
from nautilus_trader.config import PositiveInt, StrategyConfig
from nautilus_trader.indicators import AverageTrueRange
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.trading.strategy import Strategy

from strategies import StrategyMeta, register


class ATRTrailingStopConfig(StrategyConfig, frozen=True):
    instrument_id: InstrumentId
    bar_type: BarType
    trade_size: Decimal
    atr_period: PositiveInt = 14
    atr_mult: Decimal = Decimal("3.0")
    order_time_in_force: TimeInForce = TimeInForce.GTC


class ATRTrailingStop(Strategy):
    def __init__(self, config: ATRTrailingStopConfig) -> None:
        super().__init__(config)
        self.instrument: Instrument = None
        self.atr = AverageTrueRange(config.atr_period)
        self.trailing_stop: float | None = None
        self.highest_since_entry: float = 0.0
        self.lowest_since_entry: float = float("inf")

    def on_start(self) -> None:
        self.instrument = self.cache.instrument(self.config.instrument_id)
        if self.instrument is None:
            self.log.error(f"Could not find instrument for {self.config.instrument_id}")
            self.stop()
            return
        self.register_indicator_for_bars(self.config.bar_type, self.atr)
        self.subscribe_bars(self.config.bar_type)

    def on_bar(self, bar: Bar) -> None:
        if not self.indicators_initialized():
            self.log.info(
                f"Waiting for indicators to warm up [{self.cache.bar_count(self.config.bar_type)}]",
                color=LogColor.BLUE,
            )
            return
        if bar.is_single_price():
            return

        close = float(bar.close)
        atr_val = self.atr.value
        mult = float(self.config.atr_mult)

        if self.portfolio.is_flat(self.config.instrument_id):
            self.trailing_stop = None
            self.highest_since_entry = 0.0
            self.lowest_since_entry = float("inf")

            if close > bar.open:
                self.buy()
            elif close < bar.open:
                self.sell()
            return

        if self.portfolio.is_net_long(self.config.instrument_id):
            self.highest_since_entry = max(self.highest_since_entry, close)
            stop = self.highest_since_entry - atr_val * mult
            if self.trailing_stop is None:
                self.trailing_stop = stop
            else:
                self.trailing_stop = max(self.trailing_stop, stop)
            if close <= self.trailing_stop:
                self.close_all_positions(self.config.instrument_id)
                self.sell()

        elif self.portfolio.is_net_short(self.config.instrument_id):
            self.lowest_since_entry = min(self.lowest_since_entry, close)
            stop = self.lowest_since_entry + atr_val * mult
            if self.trailing_stop is None:
                self.trailing_stop = stop
            else:
                self.trailing_stop = min(self.trailing_stop, stop)
            if close >= self.trailing_stop:
                self.close_all_positions(self.config.instrument_id)
                self.buy()

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
        self.atr.reset()
        self.trailing_stop = None
        self.highest_since_entry = 0.0
        self.lowest_since_entry = float("inf")

    def on_dispose(self) -> None:
        pass


register(
    StrategyMeta(
        key="atr_trailing_stop",
        name="ATR Trailing Stop",
        description="ATR 追踪止损，根据 ATR 动态调整止损线",
        config_cls=ATRTrailingStopConfig,
        strategy_cls=ATRTrailingStop,
        default_params={
            "atr_period": 14,
            "atr_mult": 3.0,
            "trade_size": 100000,
        },
    )
)
