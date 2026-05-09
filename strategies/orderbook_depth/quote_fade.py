# ============================================================================
# 策略名称：Quote Fade / 流动性抓取（Fade）
# 分类：    订单簿深度 (orderbook_depth)
# 状态：    skeleton
# 作者：    cheristerfer
# 日期：    2026-05-08
# ============================================================================
# 概述：
#   监控 Tick 级成交流向，当一侧成交量急剧放大（大单吃单）时反向交易（Fade），
#   假定该侧流动性已被消耗将引发价格反向。同时接入订单簿辅助判断。
#
# 数据依赖：需接入 TradeTick + L2 OrderBook Deltas（或 QuoteTick），仅凭 OHLCV
#   无法运行。
#
# 参数：
#   instrument_id      — 合约
#   trade_size         — 下单数量（默认 100000）
#   lookback_trades    — 回溯 Tick 数（默认 10）
#   size_threshold_ratio — 成交量比值阈值（默认 3.0）
#   cooldown_bars      — 触发后冷却 Tick 数（默认 5）
#   use_quote_ticks    — 是否用 QuoteTick 替代 L2（默认 False）
#
# TODO：
#   - [ ] 结合订单簿深度过滤假突破
#   - [ ] 自适应阈值（基于近期成交量分布）
#
# 参考：
#   - N/A
# ============================================================================

from decimal import Decimal

from nautilus_trader.common.enums import LogColor
from nautilus_trader.config import PositiveFloat, PositiveInt, StrategyConfig
from nautilus_trader.model.book import OrderBook
from nautilus_trader.model.data import OrderBookDeltas, QuoteTick, TradeTick
from nautilus_trader.model.enums import BookType, OrderSide, TimeInForce
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.trading.strategy import Strategy

from strategies import StrategyMeta, register


class QuoteFadeConfig(StrategyConfig, frozen=True):
    instrument_id: InstrumentId
    trade_size: Decimal
    lookback_trades: PositiveInt = 10
    size_threshold_ratio: PositiveFloat = 3.0
    cooldown_bars: PositiveInt = 5
    use_quote_ticks: bool = False
    order_time_in_force: TimeInForce = TimeInForce.GTC


class QuoteFade(Strategy):
    def __init__(self, config: QuoteFadeConfig) -> None:
        super().__init__(config)
        self.instrument: Instrument | None = None
        self._book: OrderBook | None = None
        self.trade_history: list[TradeTick] = []
        self.cooldown: int = 0

    def on_start(self) -> None:
        self.instrument = self.cache.instrument(self.config.instrument_id)
        if self.instrument is None:
            self.log.error(f"Could not find instrument for {self.config.instrument_id}")
            self.stop()
            return

        if self.config.use_quote_ticks:
            self._book = OrderBook(self.instrument.id, BookType.L1_MBP)
            self.subscribe_quote_ticks(self.instrument.id)
        else:
            self.subscribe_order_book_deltas(self.instrument.id, BookType.L2_MBP)

        self.subscribe_trade_ticks(self.instrument.id)

    def on_order_book_deltas(self, deltas: OrderBookDeltas) -> None:
        pass

    def on_quote_tick(self, tick: QuoteTick) -> None:
        if self._book is not None:
            self._book.update_quote_tick(tick)

    def on_trade_tick(self, tick: TradeTick) -> None:
        self.trade_history.append(tick)
        if len(self.trade_history) > self.config.lookback_trades * 2:
            self.trade_history = self.trade_history[-self.config.lookback_trades * 2 :]

        if self.cooldown > 0:
            self.cooldown -= 1
            return

        if len(self.trade_history) < self.config.lookback_trades:
            return

        recent = self.trade_history[-self.config.lookback_trades :]
        buy_volume = sum(float(t.size) for t in recent if t.aggressor_side == OrderSide.BUY)
        sell_volume = sum(float(t.size) for t in recent if t.aggressor_side == OrderSide.SELL)

        if sell_volume <= 0 or buy_volume <= 0:
            return

        ratio = buy_volume / sell_volume
        threshold = float(self.config.size_threshold_ratio)

        if ratio > threshold and self.portfolio.is_flat(self.config.instrument_id):
            self.log.info(
                f"Buy volume {buy_volume:.2f} / Sell volume {sell_volume:.2f} = {ratio:.2f} > {threshold}: FADE LONG",
                color=LogColor.MAGENTA,
            )
            self.cooldown = self.config.cooldown_bars
            self.buy()
        elif ratio < 1 / threshold and self.portfolio.is_flat(self.config.instrument_id):
            self.log.info(
                f"Buy volume {buy_volume:.2f} / Sell volume {sell_volume:.2f} = {ratio:.2f} < {1 / threshold:.2f}: FADE SHORT",
                color=LogColor.MAGENTA,
            )
            self.cooldown = self.config.cooldown_bars
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
        self._book = None
        self.trade_history.clear()
        self.cooldown = 0

    def on_dispose(self) -> None:
        pass


register(
    StrategyMeta(
        key="quote_fade",
        name="Quote Fade",
        description="流动性抓取策略，当一侧被大量吃单后反向交易（fade）",
        config_cls=QuoteFadeConfig,
        strategy_cls=QuoteFade,
        default_params={
            "lookback_trades": 10,
            "size_threshold_ratio": 3.0,
            "cooldown_bars": 5,
            "trade_size": 100000,
        },
    )
)
