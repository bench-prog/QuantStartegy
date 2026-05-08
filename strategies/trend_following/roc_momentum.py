# ============================================================================
# 策略名称：ROC Momentum / 动量策略
# 分类：    趋势跟踪 (trend_following)
# 状态：    skeleton
# 作者：    cheristerfer
# 日期：    2026-05-08
# ============================================================================
# 概述：
#   使用 Rate of Change（ROC）指标衡量价格动量，ROC > 0 做多、ROC < 0 做空。
#   动量策略假定趋势会延续，顺势交易。
#
# 数据依赖：N/A（仅需 OHLCV Bar）
#
# 参数：
#   instrument_id — 合约
#   bar_type      — K 线类型
#   trade_size    — 下单数量（默认 100000）
#   roc_period    — ROC 周期（默认 10）
#   threshold     — 信号阈值（默认 0.0）
#
# TODO：
#   - [ ] 添加动量绝对值过滤（弱动量不交易）
#   - [ ] 结合波动率调整仓位
#
# 参考：
#   - N/A
# ============================================================================

from decimal import Decimal

from nautilus_trader.common.enums import LogColor
from nautilus_trader.config import PositiveInt, StrategyConfig
from nautilus_trader.indicators import RateOfChange
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.trading.strategy import Strategy

from strategies import StrategyMeta, register


class ROCMomentumConfig(StrategyConfig, frozen=True):
    instrument_id: InstrumentId
    bar_type: BarType
    trade_size: Decimal
    roc_period: PositiveInt = 10
    threshold: Decimal = Decimal("0.0")
    order_time_in_force: TimeInForce = TimeInForce.GTC


class ROCMomentum(Strategy):
    def __init__(self, config: ROCMomentumConfig) -> None:
        super().__init__(config)
        self.instrument: Instrument = None
        self.roc = RateOfChange(config.roc_period)

    def on_start(self) -> None:
        self.instrument = self.cache.instrument(self.config.instrument_id)
        if self.instrument is None:
            self.log.error(f"Could not find instrument for {self.config.instrument_id}")
            self.stop()
            return
        self.register_indicator_for_bars(self.config.bar_type, self.roc)
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

        if self.roc.value > float(self.config.threshold):
            if self.portfolio.is_flat(self.config.instrument_id):
                self.buy()
            elif self.portfolio.is_net_short(self.config.instrument_id):
                self.close_all_positions(self.config.instrument_id)
                self.buy()
        elif self.roc.value < float(self.config.threshold):
            if self.portfolio.is_flat(self.config.instrument_id):
                self.sell()
            elif self.portfolio.is_net_long(self.config.instrument_id):
                self.close_all_positions(self.config.instrument_id)
                self.sell()

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
        self.roc.reset()

    def on_dispose(self) -> None:
        pass


register(
    StrategyMeta(
        key="roc_momentum",
        name="ROC Momentum",
        description="动量策略，ROC 大于阈值做多、小于阈值做空",
        config_cls=ROCMomentumConfig,
        strategy_cls=ROCMomentum,
        default_params={
            "roc_period": 10,
            "threshold": 0.0,
            "trade_size": 100000,
        },
    )
)
