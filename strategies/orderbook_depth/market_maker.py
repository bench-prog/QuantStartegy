# ============================================================================
# 策略名称：Market Maker / 做市策略
# 分类：    订单簿深度 (orderbook_depth)
# 状态：    skeleton
# 作者：    cheristerfer
# 日期：    2026-05-08
# ============================================================================
# 概述：
#   在订单簿双边持续挂限价单赚取买卖价差，通过库存管理（Inventory Skew）
#   避免单边持仓过大，成交后自动补单。理想情况下以 Maker 身份成交获取返佣。
#
# 数据依赖：需接入 L2 Order Book（subscribe_order_book_deltas）+ Tick 级成交
#   流，无法仅凭 OHLCV 运行。
#
# 参数：
#   instrument_id        — 合约
#   bar_type             — K 线类型（辅助）
#   order_qty            — 挂单数量（默认 0.01）
#   spread_offset_bps    — 挂单价差偏移基点（默认 5 bps）
#   max_inventory        — 最大单边持仓（默认 1.0）
#   inventory_skew_factor — 库存倾斜调整因子（默认 0.5）
#
# TODO：
#   - [ ] 接入 L2 Order Book 数据
#   - [ ] 实现报价、补单、撤单重挂逻辑
#   - [ ] 添加 inventory 风控和紧急平仓
#   - [ ] 结合短期趋势信号调整报价中心
#
# 参考：
#   - N/A
# ============================================================================

from decimal import Decimal

from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.data import BarType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.trading.strategy import Strategy

from strategies import StrategyMeta, register


class MarketMakerConfig(StrategyConfig, frozen=True):
    """
    做市策略配置。

    本策略为骨架模板，核心逻辑依赖 Tick 级订单簿（Order Book）数据。

    需要接入的外部数据：
    -  Tick 级订单簿深度（L2 Order Book）
    -  实时买卖挂单量和价格
    -  交易所返佣结构（Maker/Taker 费率）

    数据来源：
    -  NautilusTrader 的 LiveDataClient（如 BinanceDataClient）
    -  交易所 WebSocket 直连
    """

    instrument_id: InstrumentId
    bar_type: BarType
    # 挂单数量
    order_qty: Decimal
    # 挂单边距（相对于中间价的偏移）
    spread_offset_bps: Decimal = Decimal("5")  # 5 个基点
    # 最大库存（单边持仓上限）
    max_inventory: Decimal = Decimal("1.0")
    #  inventory 倾斜调整因子：持仓偏向一侧时调整报价
    inventory_skew_factor: Decimal = Decimal("0.5")


class MarketMaker(Strategy):
    """
    做市策略骨架。

    核心逻辑：
    -  在订单簿双边持续挂限价单，赚取买卖价差（Bid-Ask Spread）。
    -  理想情况下订单作为 Maker 成交，享受更低的手续费甚至返佣。
    -  通过库存管理（Inventory Management）避免单边持仓过大。

    做市策略关键组件：
    ========================================================================
    1. 报价策略（Quoting Strategy）
       - 基础报价：Mid Price ± Spread
       -  skew 调整：持仓偏多时提高卖价、降低买价；反之亦然
       -  公式：bid = mid × (1 - spread/2 - skew×inventory)
               ask = mid × (1 + spread/2 - skew×inventory)

    2. 库存管理（Inventory Management）
       - 目标：保持 inventory ≈ 0（中性）
       - 方法：inventory 偏离时调整报价倾斜度
       - 风控：inventory 超过 max_inventory 时暂停该侧报价

    3. 撤单重挂（Quote Replenishment）
       - 订单成交后立刻在对侧补单
       - 价格移动时取消旧订单、挂新订单
       - 避免"挂单手"（Stale Orders）被市场狙击

    4. 信号增强（Signal-Based MM）
       - 结合短期趋势信号调整报价中心
       - 看涨时整体上移报价，看跌时下移
    ========================================================================

    需要的外部数据及接入点：
    ========================================================================
    1. L2 Order Book 数据
       - 需通过 NautilusTrader 的 subscribe_order_book_deltas() 接入
       - 或直接使用交易所 WebSocket 推送
       - 数据格式：{bids: [[price, qty], ...], asks: [[price, qty], ...]}

    2. Tick 级交易流（Trades）
       - 监控近期成交方向判断短期压力
       - 大单买入/卖出信号

    3. 费率结构
       - Maker 费率（通常负值，即返佣）
       - Taker 费率
       - 用于计算盈亏平衡点
    ========================================================================

    实现 TODO：
    - [ ] 接入 L2 Order Book 数据（subscribe_order_book_deltas）
    - [ ] 实现 on_quote() 或 on_order_book() 回调
    - [ ] 计算 mid price 和调整后的 bid/ask 价格
    - [ ] 使用限价单（Limit Order）挂单
    - [ ] 成交后触发补单逻辑
    - [ ] 定期取消未成交的过时订单
    - [ ] 添加 inventory 风控和紧急平仓
    """

    def __init__(self, config: MarketMakerConfig) -> None:
        super().__init__(config)
        self.inventory: Decimal = Decimal("0")
        self.active_bids: list = []
        self.active_asks: list = []

    def on_start(self) -> None:
        # TODO: 订阅订单簿深度数据
        # self.subscribe_order_book_deltas(self.config.instrument_id)
        # self.subscribe_order_book_snapshots(self.config.instrument_id)
        pass

    def on_quote(self, quote) -> None:
        """
        当订单簿更新时触发。
        这是做市策略的核心回调。
        """
        # TODO: 计算 mid price
        # mid = (quote.bid + quote.ask) / 2

        # TODO: 根据 inventory 调整 skew
        # skew = float(self.config.inventory_skew_factor) * float(self.inventory)

        # TODO: 计算目标挂单价格
        # offset = float(self.config.spread_offset_bps) / 10000
        # target_bid = mid * (1 - offset - skew)
        # target_ask = mid * (1 + offset - skew)

        # TODO: 取消旧订单、挂新订单
        # self.cancel_all_orders(self.config.instrument_id)
        # self._place_quote_orders(target_bid, target_ask)
        pass

    def _place_quote_orders(self, bid_price: float, ask_price: float) -> None:
        """在目标价格挂双边限价单。"""
        # TODO: 使用 order_factory.limit() 创建限价单
        # TODO: 提交 BUY limit @ bid_price
        # TODO: 提交 SELL limit @ ask_price
        pass

    def on_order_filled(self, order) -> None:
        """
        订单成交后更新 inventory 并补单。
        """
        # TODO: 更新 inventory
        # if order.side == BUY: self.inventory += order.filled_qty
        # if order.side == SELL: self.inventory -= order.filled_qty

        # TODO: 触发补单
        # self._replenish_quote()
        pass

    def on_stop(self) -> None:
        self.cancel_all_orders(self.config.instrument_id)
        # TODO: 清仓剩余 inventory（可用市价单或 TWAP）
        # if self.inventory != 0:
        #     self.close_all_positions(self.config.instrument_id)

    def on_reset(self) -> None:
        self.inventory = Decimal("0")
        self.active_bids.clear()
        self.active_asks.clear()

    def on_dispose(self) -> None:
        pass


register(
    StrategyMeta(
        key="market_maker",
        name="Market Maker",
        description="做市策略骨架：双边挂限价单赚取价差，需接入L2订单簿Tick数据",
        config_cls=MarketMakerConfig,
        strategy_cls=MarketMaker,
        default_params={
            "order_qty": Decimal("0.01"),
            "spread_offset_bps": Decimal("5"),
            "max_inventory": Decimal("1.0"),
            "inventory_skew_factor": Decimal("0.5"),
        },
    )
)
