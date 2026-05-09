# ============================================================================
# 策略名称：Order Book Imbalance / 订单簿深度不平衡
# 分类：    订单簿深度 (orderbook_depth)
# 状态：    skeleton
# 作者：    cheristerfer
# 日期：    2026-05-08
# ============================================================================
# 概述：
#   计算前 N 档买盘与卖盘深度比值（Imbalance），比值超过阈值时认为买方/卖方
#   强势，顺势跟进做多/做空。支持 L2 OrderBook Deltas 或 QuoteTick 两种数据源。
#
# 数据依赖：需接入 L2 OrderBook Deltas 或 QuoteTick，仅凭 OHLCV 无法运行。
#
# 参数：
#   instrument_id              — 合约
#   trade_size                 — 下单数量（默认 100000）
#   depth_levels               — 深度档位数（默认 5）
#   imbalance_threshold        — 不平衡比值阈值（默认 2.0）
#   min_seconds_between_triggers — 触发冷却时间秒（默认 1.0）
#   use_quote_ticks            — 是否用 QuoteTick 替代 L2（默认 False）
#
# TODO：
#   - [ ] 添加反向信号（均值回归模式）
#   - [ ] 动态调整 depth_levels
#
# 参考：
#   - N/A
# ============================================================================

from decimal import Decimal
from typing import Any

from nautilus_trader.config import PositiveFloat, StrategyConfig
from nautilus_trader.model.book import OrderBook
from nautilus_trader.model.data import OrderBookDeltas, QuoteTick
from nautilus_trader.model.enums import BookType, OrderSide, TimeInForce
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.trading.strategy import Strategy

from strategies import StrategyMeta, register


class OrderBookImbalanceConfig(StrategyConfig, frozen=True):
    instrument_id: InstrumentId
    trade_size: Decimal
    depth_levels: int = 5
    imbalance_threshold: PositiveFloat = 2.0
    min_seconds_between_triggers: PositiveFloat = 1.0
    use_quote_ticks: bool = False
    order_time_in_force: TimeInForce = TimeInForce.GTC


class OrderBookImbalance(Strategy):
    def __init__(self, config: OrderBookImbalanceConfig) -> None:
        super().__init__(config)
        self.instrument: Instrument | None = None
        self._book: OrderBook | None = None
        self._last_trigger_time: Any = None

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

    def on_order_book_deltas(self, deltas: OrderBookDeltas) -> None:
        self.check_trigger()

    def on_quote_tick(self, tick: QuoteTick) -> None:
        if self._book is not None:
            self._book.update_quote_tick(tick)
        self.check_trigger()

    def check_trigger(self) -> None:
        book = self._book or self.cache.order_book(self.config.instrument_id)
        if not book or not book.spread():
            return

        bid_size = book.best_bid_size()
        ask_size = book.best_ask_size()
        if not bid_size or not ask_size or bid_size <= 0 or ask_size <= 0:
            return

        # 累加前 N 档深度
        bid_depth = sum(
            float(level.exposure()) for level in book.bids()[: self.config.depth_levels]
        )
        ask_depth = sum(
            float(level.exposure()) for level in book.asks()[: self.config.depth_levels]
        )
        if ask_depth <= 0:
            return

        imbalance = bid_depth / ask_depth
        self.log.info(
            f"Imbalance: {imbalance:.2f} (bid_depth={bid_depth:.2f}, ask_depth={ask_depth:.2f})",
        )

        if self._is_cooldown_active():
            return
        if self.cache.orders_inflight(strategy_id=self.id):
            return

        threshold = float(self.config.imbalance_threshold)

        if imbalance > threshold and self.portfolio.is_flat(self.config.instrument_id):
            self._last_trigger_time = self.clock.utc_now()
            self.buy()
        elif imbalance < 1 / threshold and self.portfolio.is_flat(self.config.instrument_id):
            self._last_trigger_time = self.clock.utc_now()
            self.sell()

    def _is_cooldown_active(self) -> bool:
        if self._last_trigger_time is None:
            return False
        elapsed = (self.clock.utc_now() - self._last_trigger_time).total_seconds()
        return elapsed < self.config.min_seconds_between_triggers

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
        self._last_trigger_time = None

    def on_dispose(self) -> None:
        pass


register(
    StrategyMeta(
        key="orderbook_imbalance",
        name="Order Book Imbalance",
        description="订单簿深度不平衡策略，买/卖深度比值突破阈值时跟进",
        config_cls=OrderBookImbalanceConfig,
        strategy_cls=OrderBookImbalance,
        default_params={
            "depth_levels": 5,
            "imbalance_threshold": 2.0,
            "trade_size": 100000,
        },
    )
)
