# ============================================================================
# 策略名称：Engulfing Pattern / 吞没形态
# 分类：    形态识别 (pattern_recognition)
# 状态：    skeleton
# 作者：    cheristerfer
# 日期：    2026-05-08
# ============================================================================
# 概述：
#   识别 K 线吞没形态：看涨吞没（前一根阴线被当前阳线完全包裹）做多，
#   看跌吞没（前一根阳线被当前阴线完全包裹）做空。可选趋势过滤降低假信号。
#
# 数据依赖：N/A（仅需 OHLCV Bar）
#
# 参数：
#   instrument_id  — 合约
#   bar_type       — K 线类型
#   trade_size     — 下单数量（默认 100000）
#   use_trend_filter — 是否启用 SMA20 趋势过滤（默认 True）
#
# TODO：
#   - [ ] 添加更多形态（锤子线、十字星、晨星等）
#   - [ ] 形态强度评分（实体占比、影线比例）
#
# 参考：
#   - N/A
# ============================================================================

from decimal import Decimal

from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.trading.strategy import Strategy

from strategies import StrategyMeta, register


class EngulfingPatternConfig(StrategyConfig, frozen=True):
    instrument_id: InstrumentId
    bar_type: BarType
    trade_size: Decimal
    use_trend_filter: bool = True
    order_time_in_force: TimeInForce = TimeInForce.GTC


class EngulfingPattern(Strategy):
    def __init__(self, config: EngulfingPatternConfig) -> None:
        super().__init__(config)
        self.instrument: Instrument = None
        self.prev_bar: Bar | None = None

    def on_start(self) -> None:
        self.instrument = self.cache.instrument(self.config.instrument_id)
        if self.instrument is None:
            self.log.error(f"Could not find instrument for {self.config.instrument_id}")
            self.stop()
            return
        self.subscribe_bars(self.config.bar_type)

    def on_bar(self, bar: Bar) -> None:
        if bar.is_single_price():
            return

        if self.prev_bar is None:
            self.prev_bar = bar
            return

        prev = self.prev_bar
        curr = bar

        prev_body = abs(float(prev.close) - float(prev.open))
        curr_body = abs(float(curr.close) - float(curr.open))
        prev_bullish = float(prev.close) > float(prev.open)
        prev_bearish = float(prev.close) < float(prev.open)
        curr_bullish = float(curr.close) > float(curr.open)
        curr_bearish = float(curr.close) < float(curr.open)

        # Bullish engulfing: prev bearish, curr bullish, curr body covers prev body
        bullish_engulfing = (
            prev_bearish
            and curr_bullish
            and float(curr.open) <= float(prev.close)
            and float(curr.close) >= float(prev.open)
            and curr_body > prev_body
        )

        # Bearish engulfing: prev bullish, curr bearish, curr body covers prev body
        bearish_engulfing = (
            prev_bullish
            and curr_bearish
            and float(curr.open) >= float(prev.close)
            and float(curr.close) <= float(prev.open)
            and curr_body > prev_body
        )

        if self.config.use_trend_filter:
            cache = self.cache
            bar_type = self.config.bar_type
            if cache.bar_count(bar_type) >= 20:
                recent = list(cache.bars(bar_type))[-20:]
                closes = [float(b.close) for b in recent]
                sma20 = sum(closes) / len(closes)
                trend_up = float(curr.close) > sma20
                trend_down = float(curr.close) < sma20
            else:
                trend_up = trend_down = True
        else:
            trend_up = trend_down = True

        if bullish_engulfing and trend_down:
            if self.portfolio.is_flat(self.config.instrument_id):
                self.buy()
            elif self.portfolio.is_net_short(self.config.instrument_id):
                self.close_all_positions(self.config.instrument_id)
                self.buy()
        elif bearish_engulfing and trend_up:
            if self.portfolio.is_flat(self.config.instrument_id):
                self.sell()
            elif self.portfolio.is_net_long(self.config.instrument_id):
                self.close_all_positions(self.config.instrument_id)
                self.sell()

        self.prev_bar = bar

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
        self.prev_bar = None

    def on_dispose(self) -> None:
        pass


register(
    StrategyMeta(
        key="engulfing_pattern",
        name="Engulfing Pattern",
        description="吞没形态策略，看涨/看跌吞没配合趋势过滤",
        config_cls=EngulfingPatternConfig,
        strategy_cls=EngulfingPattern,
        default_params={
            "use_trend_filter": True,
            "trade_size": 100000,
        },
    )
)
