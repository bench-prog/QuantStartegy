# ============================================================================
# 策略名称：Keltner Channel Breakout / 凯尔特纳通道突破
# 分类：    波动率 (volatility)
# 状态：    skeleton
# 作者：    cheristerfer
# 日期：    2026-05-08
# ============================================================================
# 概述：
#   基于 EMA + ATR 构建 Keltner Channel，价格突破上轨做多、突破下轨做空。
#   相比 Bollinger Bands 使用 ATR 而非标准差，对极端价格敏感度不同。
#
# 数据依赖：N/A（仅需 OHLCV Bar）
#
# 参数：
#   instrument_id — 合约
#   bar_type      — K 线类型
#   trade_size    — 下单数量（默认 100000）
#   ema_period    — EMA 周期（默认 20）
#   atr_period    — ATR 周期（默认 14）
#   atr_mult      — ATR 乘数（默认 2.0）
#
# TODO：
#   - [ ] 添加突破后回踩确认
#   - [ ] 与 Bollinger Bands 组合使用（双通道确认）
#
# 参考：
#   - N/A
# ============================================================================

from decimal import Decimal

from nautilus_trader.common.enums import LogColor
from nautilus_trader.config import PositiveInt, StrategyConfig
from nautilus_trader.indicators import KeltnerChannel
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.trading.strategy import Strategy

from strategies import StrategyMeta, register


class KeltnerBreakoutConfig(StrategyConfig, frozen=True):
    instrument_id: InstrumentId
    bar_type: BarType
    trade_size: Decimal
    ema_period: PositiveInt = 20
    atr_period: PositiveInt = 14
    atr_mult: Decimal = Decimal("2.0")
    order_time_in_force: TimeInForce = TimeInForce.GTC


class KeltnerBreakout(Strategy):
    def __init__(self, config: KeltnerBreakoutConfig) -> None:
        super().__init__(config)
        self.instrument: Instrument = None
        self.kc = KeltnerChannel(config.ema_period, float(config.atr_mult))

    def on_start(self) -> None:
        self.instrument = self.cache.instrument(self.config.instrument_id)
        if self.instrument is None:
            self.log.error(f"Could not find instrument for {self.config.instrument_id}")
            self.stop()
            return
        self.register_indicator_for_bars(self.config.bar_type, self.kc)
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

        if close >= self.kc.upper:
            if self.portfolio.is_flat(self.config.instrument_id):
                self.buy()
            elif self.portfolio.is_net_short(self.config.instrument_id):
                self.close_all_positions(self.config.instrument_id)
                self.buy()
        elif close <= self.kc.lower:
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
        self.kc.reset()

    def on_dispose(self) -> None:
        pass


register(
    StrategyMeta(
        key="keltner_breakout",
        name="Keltner Channel Breakout",
        description="凯尔特纳通道突破，价格上破上轨做多、下破下轨做空",
        config_cls=KeltnerBreakoutConfig,
        strategy_cls=KeltnerBreakout,
        default_params={
            "ema_period": 20,
            "atr_period": 14,
            "atr_mult": 2.0,
            "trade_size": 100000,
        },
    )
)
