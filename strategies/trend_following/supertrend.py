# ============================================================================
# 策略名称：SuperTrend / 超级趋势
# 分类：    趋势跟踪 (trend_following)
# 状态：    skeleton
# 作者：    cheristerfer
# 日期：    2026-05-08
# ============================================================================
# 概述：
#   基于 ATR 构建动态跟踪止损线（Upper/Lower Band），价格在线上为多头、线下
#   为空头。方向翻转时发出交易信号，相比固定止损更能自适应波动率变化。
#
# 数据依赖：N/A（仅需 OHLCV Bar）
#
# 参数：
#   instrument_id — 合约
#   bar_type      — K 线类型
#   trade_size    — 下单数量（默认 100000）
#   atr_period    — ATR 周期（默认 10）
#   multiplier    — ATR 乘数（默认 3.0）
#
# TODO：
#   - [ ] 添加中轨过滤避免震荡市反复翻转
#   - [ ] 支持金字塔加仓
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


class SuperTrendConfig(StrategyConfig, frozen=True):
    instrument_id: InstrumentId
    bar_type: BarType
    trade_size: Decimal
    atr_period: PositiveInt = 10
    multiplier: Decimal = Decimal("3.0")
    order_time_in_force: TimeInForce = TimeInForce.GTC


class SuperTrend(Strategy):
    """
    SuperTrend 趋势跟踪策略。

    核心逻辑：
    -  基于 ATR 构建动态跟踪止损线，比固定百分比止损更能适应波动率变化。
    -  Upper Band = (High + Low) / 2 + multiplier × ATR
    -  Lower Band = (High + Low) / 2 - multiplier × ATR
    -  SuperTrend 线在趋势中贴近价格，在震荡中远离价格。
    -  收盘价上穿 SuperTrend → 做多；收盘价下穿 SuperTrend → 做空。

    参数说明：
    -  atr_period: ATR 计算周期，默认 10
    -  multiplier: ATR 乘数，越大则信号越少但假信号越少，默认 3.0
    """

    def __init__(self, config: SuperTrendConfig) -> None:
        super().__init__(config)
        self.instrument: Instrument = None
        self.atr = AverageTrueRange(config.atr_period)
        self.supertrend: float = 0.0
        self.prev_supertrend: float = 0.0
        self.direction: int = 1  # 1 = long, -1 = short
        self.prev_close: float | None = None

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

        hl2 = (float(bar.high) + float(bar.low)) / 2.0
        atr_val = self.atr.value
        multiplier = float(self.config.multiplier)

        upper_band = hl2 + multiplier * atr_val
        lower_band = hl2 - multiplier * atr_val

        close = float(bar.close)

        if self.prev_close is None:
            # 初始化
            self.supertrend = upper_band if close <= upper_band else lower_band
            self.direction = -1 if close <= upper_band else 1
        else:
            # 根据前一根 K 线的方向和价格位置，更新当前 SuperTrend
            if self.direction == 1:
                # 之前是多头，Lower Band 为有效线
                self.supertrend = max(lower_band, self.prev_supertrend)
                if close < self.supertrend:
                    self.direction = -1
                    self.supertrend = upper_band
            else:
                # 之前是空头，Upper Band 为有效线
                self.supertrend = min(upper_band, self.prev_supertrend)
                if close > self.supertrend:
                    self.direction = 1
                    self.supertrend = lower_band

        self.prev_supertrend = self.supertrend
        self.prev_close = close

        if self.direction == 1:
            if self.portfolio.is_flat(self.config.instrument_id):
                self.buy()
            elif self.portfolio.is_net_short(self.config.instrument_id):
                self.close_all_positions(self.config.instrument_id)
                self.buy()
        elif self.direction == -1:
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
        self.atr.reset()
        self.supertrend = 0.0
        self.prev_supertrend = 0.0
        self.direction = 1
        self.prev_close = None

    def on_dispose(self) -> None:
        pass


register(
    StrategyMeta(
        key="supertrend",
        name="SuperTrend",
        description="SuperTrend 趋势跟踪：基于 ATR 的动态跟踪止损线，自适应波动率",
        config_cls=SuperTrendConfig,
        strategy_cls=SuperTrend,
        default_params={
            "atr_period": 10,
            "multiplier": 3.0,
            "trade_size": 100000,
        },
    )
)
