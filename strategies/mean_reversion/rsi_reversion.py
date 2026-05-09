# ============================================================================
# 策略名称：RSI Overbought/Oversold / RSI 超买超卖反转
# 分类：    均值回归 (mean_reversion)
# 状态：    skeleton
# 作者：    cheristerfer
# 日期：    2026-05-08
# ============================================================================
# 概述：
#   RSI 进入超卖区（< 30）做多、进入超买区（> 70）做空，RSI 回归中性区时
#   平仓。利用极端情绪后的价格反转获利。
#
# 数据依赖：N/A（仅需 OHLCV Bar）
#
# 参数：
#   instrument_id — 合约
#   bar_type      — K 线类型
#   trade_size    — 下单数量（默认 100000）
#   period        — RSI 周期（默认 14）
#   overbought    — 超买阈值（默认 70）
#   oversold      — 超卖阈值（默认 30）
#
# TODO：
#   - [ ] 趋势过滤：强趋势中 RSI 可长期停留在超买/超卖区
#   - [ ] 添加 RSI 背离检测增强信号
#
# 参考：
#   - N/A
# ============================================================================

from decimal import Decimal

from nautilus_trader.common.enums import LogColor
from nautilus_trader.config import PositiveInt, StrategyConfig
from nautilus_trader.indicators import RelativeStrengthIndex
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.trading.strategy import Strategy

from strategies import StrategyMeta, register


class RSIReversionConfig(StrategyConfig, frozen=True):
    instrument_id: InstrumentId
    bar_type: BarType
    trade_size: Decimal
    period: PositiveInt = 14
    overbought: Decimal = Decimal("70")
    oversold: Decimal = Decimal("30")
    order_time_in_force: TimeInForce = TimeInForce.GTC


class RSIReversion(Strategy):
    def __init__(self, config: RSIReversionConfig) -> None:
        super().__init__(config)
        self.instrument: Instrument = None
        self.rsi = RelativeStrengthIndex(config.period)

    def on_start(self) -> None:
        self.instrument = self.cache.instrument(self.config.instrument_id)
        if self.instrument is None:
            self.log.error(f"Could not find instrument for {self.config.instrument_id}")
            self.stop()
            return
        self.register_indicator_for_bars(self.config.bar_type, self.rsi)
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

        rsi_val = self.rsi.value
        overbought = float(self.config.overbought)
        oversold = float(self.config.oversold)

        if rsi_val <= oversold:
            if self.portfolio.is_flat(self.config.instrument_id):
                self.buy()
            elif self.portfolio.is_net_short(self.config.instrument_id):
                self.close_all_positions(self.config.instrument_id)
                self.buy()
        elif rsi_val >= overbought:
            if self.portfolio.is_flat(self.config.instrument_id):
                self.sell()
            elif self.portfolio.is_net_long(self.config.instrument_id):
                self.close_all_positions(self.config.instrument_id)
                self.sell()
        elif oversold < rsi_val < overbought and not self.portfolio.is_flat(
            self.config.instrument_id
        ):
            self.close_all_positions(self.config.instrument_id)

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
        self.rsi.reset()

    def on_dispose(self) -> None:
        pass


register(
    StrategyMeta(
        key="rsi_reversion",
        name="RSI Overbought/Oversold",
        description="RSI 超买超卖反转，RSI < 30 做多、RSI > 70 做空，回归中性区平仓",
        config_cls=RSIReversionConfig,
        strategy_cls=RSIReversion,
        default_params={
            "period": 14,
            "overbought": 70,
            "oversold": 30,
            "trade_size": 100000,
        },
    )
)
