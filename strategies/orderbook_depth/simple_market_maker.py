# ============================================================================
# 策略名称：Simple Market Maker / 简单做市
# 分类：    订单簿深度 (orderbook_depth)
# 状态：    skeleton
# 作者：    cheristerfer
# 日期：    2026-05-08
# ============================================================================
# 概述：
#   在最佳买卖价（best bid/ask）外偏移 N 个 tick 挂限价单，订单簿每次更新时
#   撤旧挂新。含仓位上限控制，防止单边持仓过大。相比 Market Maker 去掉了
#   inventory skew、信号增强等高级功能，适合快速理解做市逻辑。
#
# 数据依赖：需接入 L2 OrderBook Deltas 或 QuoteTick，仅凭 OHLCV 无法运行。
#
# 参数：
#   instrument_id — 合约
#   order_size    — 挂单数量（默认 0.01）
#   spread_ticks  — 价差偏移 tick 数（默认 1）
#   max_position  — 最大持仓（默认 10）
#   use_quote_ticks — 是否用 QuoteTick 替代 L2（默认 False）
#
# TODO：
#   - [ ] 添加 inventory skew 倾斜报价
#   - [ ] 添加成交补单逻辑
#
# 参考：
#   - N/A
# ============================================================================

from decimal import Decimal

from nautilus_trader.config import PositiveInt, StrategyConfig
from nautilus_trader.model.book import OrderBook
from nautilus_trader.model.data import OrderBookDeltas, QuoteTick
from nautilus_trader.model.enums import BookType, OrderSide, TimeInForce
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.trading.strategy import Strategy

from strategies import StrategyMeta, register


class SimpleMarketMakerConfig(StrategyConfig, frozen=True):
    instrument_id: InstrumentId
    order_size: Decimal
    spread_ticks: PositiveInt = 1
    max_position: Decimal = Decimal("10")
    use_quote_ticks: bool = False
    order_time_in_force: TimeInForce = TimeInForce.GTC


class SimpleMarketMaker(Strategy):
    def __init__(self, config: SimpleMarketMakerConfig) -> None:
        super().__init__(config)
        self.instrument: Instrument | None = None
        self._book: OrderBook | None = None

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

        self._place_quotes()

    def on_order_book_deltas(self, deltas: OrderBookDeltas) -> None:
        self._update_quotes()

    def on_quote_tick(self, tick: QuoteTick) -> None:
        if self._book is not None:
            self._book.update_quote_tick(tick)
        self._update_quotes()

    def _get_book(self) -> OrderBook | None:
        return self._book or self.cache.order_book(self.config.instrument_id)

    def _place_quotes(self) -> None:
        book = self._get_book()
        if not book:
            return
        bid = book.best_bid_price()
        ask = book.best_ask_price()
        if not bid or not ask:
            return

        tick_size = float(self.instrument.price_increment)
        bid_price = bid - self.config.spread_ticks * tick_size
        ask_price = ask + self.config.spread_ticks * tick_size

        position = self.cache.position(self.config.instrument_id)
        position_qty = float(position.quantity) if position else 0.0

        if position_qty < float(self.config.max_position):
            bid_order = self.order_factory.limit(
                instrument_id=self.config.instrument_id,
                order_side=OrderSide.BUY,
                quantity=self.instrument.make_qty(self.config.order_size),
                price=self.instrument.make_price(bid_price),
                post_only=True,
                time_in_force=self.config.order_time_in_force,
            )
            self.submit_order(bid_order)

        if position_qty > -float(self.config.max_position):
            ask_order = self.order_factory.limit(
                instrument_id=self.config.instrument_id,
                order_side=OrderSide.SELL,
                quantity=self.instrument.make_qty(self.config.order_size),
                price=self.instrument.make_price(ask_price),
                post_only=True,
                time_in_force=self.config.order_time_in_force,
            )
            self.submit_order(ask_order)

    def _update_quotes(self) -> None:
        self.cancel_all_orders(self.config.instrument_id)
        self._place_quotes()

    def on_stop(self) -> None:
        self.cancel_all_orders(self.config.instrument_id)
        self.close_all_positions(self.config.instrument_id)

    def on_reset(self) -> None:
        self._book = None

    def on_dispose(self) -> None:
        pass


register(
    StrategyMeta(
        key="simple_market_maker",
        name="Simple Market Maker",
        description="简单做市策略，在 best bid/ask 外挂单赚取价差",
        config_cls=SimpleMarketMakerConfig,
        strategy_cls=SimpleMarketMaker,
        default_params={
            "spread_ticks": 1,
            "order_size": Decimal("0.01"),
            "max_position": Decimal("10"),
        },
    )
)
