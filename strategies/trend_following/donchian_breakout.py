# ============================================================================
# 策略名称：Donchian Channel Breakout / 唐奇安通道突破
# 分类：    趋势跟踪 (trend_following)
# 状态：    skeleton
# 作者：    cheristerfer
# 日期：    2026-05-08
# ============================================================================
# 概述：
#   基于 N 周期最高/最低价构建 Donchian Channel，价格突破上轨做多、突破下轨
#   做空。经典趋势跟踪策略，海龟交易法则的核心组件。
#
# 数据依赖：N/A（仅需 OHLCV Bar）
#
# 参数：
#   instrument_id — 合约
#   bar_type      — K 线类型
#   trade_size    — 下单数量（默认 100000）
#   period        — 通道周期（默认 20）
#
# TODO：
#   - [ ] 添加突破后的回踩确认（Pullback Entry）
#   - [ ] 组合短期和长期通道（双 Donchian）
#
# 参考：
#   - N/A
# ============================================================================

from decimal import Decimal

from nautilus_trader.common.enums import LogColor
from nautilus_trader.config import PositiveInt, StrategyConfig
from nautilus_trader.indicators import DonchianChannel
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.trading.strategy import Strategy

from strategies import StrategyMeta, register


class DonchianBreakoutConfig(StrategyConfig, frozen=True):
    instrument_id: InstrumentId
    bar_type: BarType
    trade_size: Decimal
    period: PositiveInt = 20
    order_time_in_force: TimeInForce = TimeInForce.GTC


class DonchianBreakout(Strategy):
    def __init__(self, config: DonchianBreakoutConfig) -> None:
        super().__init__(config)
        self.instrument: Instrument = None
        self.dc = DonchianChannel(config.period)

    def on_start(self) -> None:
        self.instrument = self.cache.instrument(self.config.instrument_id)
        if self.instrument is None:
            self.log.error(f"Could not find instrument for {self.config.instrument_id}")
            self.stop()
            return
        self.register_indicator_for_bars(self.config.bar_type, self.dc)
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

        if bar.close >= self.dc.upper:
            if self.portfolio.is_flat(self.config.instrument_id):
                self.buy()
            elif self.portfolio.is_net_short(self.config.instrument_id):
                self.close_all_positions(self.config.instrument_id)
                self.buy()
        elif bar.close <= self.dc.lower:
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
        self.dc.reset()

    def on_dispose(self) -> None:
        pass


register(
    StrategyMeta(
        key="donchian_breakout",
        name="Donchian Channel Breakout",
        description="唐奇安通道突破，价格上破上轨做多、下破下轨做空",
        config_cls=DonchianBreakoutConfig,
        strategy_cls=DonchianBreakout,
        default_params={
            "period": 20,
            "trade_size": 100000,
        },
    )
)
