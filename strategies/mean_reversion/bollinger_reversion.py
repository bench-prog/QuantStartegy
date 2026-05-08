# ============================================================================
# 策略名称：Bollinger Bands Mean Reversion / 布林带均值回归
# 分类：    均值回归 (mean_reversion)
# 状态：    skeleton
# 作者：    cheristerfer
# 日期：    2026-05-08
# ============================================================================
# 概述：
#   价格触及布林带下轨时做多、触及上轨时做空，回归中轨时平仓。假定价格在
#   布林带区间内均值回归，极端偏离后反向交易。
#
# 数据依赖：N/A（仅需 OHLCV Bar）
#
# 参数：
#   instrument_id — 合约
#   bar_type      — K 线类型
#   trade_size    — 下单数量（默认 100000）
#   period        — 布林带周期（默认 20）
#   std_dev       — 标准差倍数（默认 2.0）
#
# TODO：
#   - [ ] 添加止损逻辑（突破布林带继续趋势运行的风险）
#   - [ ] 支持持仓加仓（Pyramid）
#
# 参考：
#   - N/A
# ============================================================================

from decimal import Decimal

from nautilus_trader.common.enums import LogColor
from nautilus_trader.config import PositiveInt, StrategyConfig
from nautilus_trader.indicators import BollingerBands
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.trading.strategy import Strategy

from strategies import StrategyMeta, register


class BollingerReversionConfig(StrategyConfig, frozen=True):
    instrument_id: InstrumentId
    bar_type: BarType
    trade_size: Decimal
    period: PositiveInt = 20
    std_dev: Decimal = Decimal("2.0")
    order_time_in_force: TimeInForce = TimeInForce.GTC


class BollingerReversion(Strategy):
    def __init__(self, config: BollingerReversionConfig) -> None:
        super().__init__(config)
        self.instrument: Instrument = None
        self.bb = BollingerBands(config.period, float(config.std_dev))

    def on_start(self) -> None:
        self.instrument = self.cache.instrument(self.config.instrument_id)
        if self.instrument is None:
            self.log.error(f"Could not find instrument for {self.config.instrument_id}")
            self.stop()
            return
        self.register_indicator_for_bars(self.config.bar_type, self.bb)
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

        if close <= self.bb.lower:
            if self.portfolio.is_flat(self.config.instrument_id):
                self.buy()
            elif self.portfolio.is_net_short(self.config.instrument_id):
                self.close_all_positions(self.config.instrument_id)
                self.buy()
        elif close >= self.bb.upper:
            if self.portfolio.is_flat(self.config.instrument_id):
                self.sell()
            elif self.portfolio.is_net_long(self.config.instrument_id):
                self.close_all_positions(self.config.instrument_id)
                self.sell()
        elif self.bb.lower < close < self.bb.upper and not self.portfolio.is_flat(self.config.instrument_id):
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
        self.bb.reset()

    def on_dispose(self) -> None:
        pass


register(
    StrategyMeta(
        key="bollinger_reversion",
        name="Bollinger Bands Mean Reversion",
        description="布林带均值回归，触及下轨做多、触及上轨做空，回归中轨平仓",
        config_cls=BollingerReversionConfig,
        strategy_cls=BollingerReversion,
        default_params={
            "period": 20,
            "std_dev": 2.0,
            "trade_size": 100000,
        },
    )
)
