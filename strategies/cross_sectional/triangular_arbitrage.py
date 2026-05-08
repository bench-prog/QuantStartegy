# ============================================================================
# 策略名称：Triangular Arbitrage / 三角套利
# 分类：    跨品种套利 (cross_sectional)
# 状态：    skeleton
# 作者：    cheristerfer
# 日期：    2026-05-08
# ============================================================================
# 概述：
#   利用三个交易对之间的价格不一致进行无风险套利。正向循环 USDT→A→B→USDT，
#   反向循环 USDT→B→A→USDT，循环完成后 USDT 增加即存在套利空间。
#
# 数据依赖：需同时订阅三个交易对 Bar 行情；建议接入订单簿深度验证可执行性。
#
# 参数：
#   pair_a_instrument_id — 交易对 A（如 BTCUSDT）
#   pair_a_bar_type      — A K 线类型
#   pair_b_instrument_id — 交易对 B（如 ETHBTC）
#   pair_b_bar_type      — B K 线类型
#   pair_c_instrument_id — 交易对 C（如 ETHUSDT）
#   pair_c_bar_type      — C K 线类型
#   trade_size           — 下单数量（默认 1000）
#   min_profit_pct       — 最小套利收益率阈值（默认 0.05%）
#
# TODO：
#   - [ ] 维护三个交易对的最新价格
#   - [ ] 计算正向和反向套利收益率
#   - [ ] 收益率超过阈值时同时下三个订单
#   - [ ] 使用限价单避免滑点
#   - [ ] 添加并发订单管理和失败回滚
#
# 参考：
#   - N/A
# ============================================================================

from decimal import Decimal

from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.trading.strategy import Strategy

from strategies import StrategyMeta, register


class TriangularArbitrageConfig(StrategyConfig, frozen=True):
    """
    三角套利配置。

    本策略为骨架模板，需同时订阅三个交易对行情。

    典型三角套利循环示例：
    -  USDT → BTC → ETH → USDT
    -  即：买入 BTC/USDT → 卖出 BTC/ETH → 卖出 ETH/USDT
    -  如果循环完成后 USDT 增加，则存在套利空间
    """

    pair_a_instrument_id: InstrumentId   # 如 BTCUSDT
    pair_a_bar_type: BarType
    pair_b_instrument_id: InstrumentId   # 如 ETHBTC (BTC 计价)
    pair_b_bar_type: BarType
    pair_c_instrument_id: InstrumentId   # 如 ETHUSDT
    pair_c_bar_type: BarType
    trade_size: Decimal
    # 最小套利收益率阈值
    min_profit_pct: Decimal = Decimal("0.05")


class TriangularArbitrage(Strategy):
    """
    三角套利策略骨架。

    核心逻辑：
    -  利用三个交易对之间的价格不一致进行无风险套利。
    -  正向循环：USDT → A → B → USDT
    -  反向循环：USDT → B → A → USDT

    套利条件计算：
    -  正向：1 / price(A/USDT) × price(B/A) × price(B/USDT) > 1 + min_profit_pct
    -  反向：price(B/USDT) / price(B/A) / price(A/USDT) > 1 + min_profit_pct

    需要的外部数据及接入点：
    ========================================================================
    1. 三个交易对的实时行情
       - 必须同时订阅 pair_a, pair_b, pair_c 的 bar_type
       - 在 on_bar() 中区分不同来源更新对应价格

    2. 最低成交量验证
       - 三角套利需要三个交易对都有足够深度
       - 需接入订单簿或成交量数据验证可执行性

    3. 手续费计算
       - 三次交易的手续费累积可能侵蚀套利利润
       - 需精确计算包含手续费后的净收益率
    ========================================================================

    实现 TODO：
    - [ ] 维护三个交易对的最新价格
    - [ ] 计算正向和反向套利收益率
    - [ ] 收益率超过阈值时同时下三个交易对的订单
    - [ ] 考虑使用限价单避免滑点侵蚀利润
    - [ ] 添加并发订单管理和失败回滚机制
    """

    def __init__(self, config: TriangularArbitrageConfig) -> None:
        super().__init__(config)
        self.price_a: float = 0.0
        self.price_b: float = 0.0
        self.price_c: float = 0.0

    def on_start(self) -> None:
        self.subscribe_bars(self.config.pair_a_bar_type)
        self.subscribe_bars(self.config.pair_b_bar_type)
        self.subscribe_bars(self.config.pair_c_bar_type)

    def on_bar(self, bar: Bar) -> None:
        if bar.bar_type == self.config.pair_a_bar_type:
            self.price_a = float(bar.close)
        elif bar.bar_type == self.config.pair_b_bar_type:
            self.price_b = float(bar.close)
        elif bar.bar_type == self.config.pair_c_bar_type:
            self.price_c = float(bar.close)

        if self.price_a == 0 or self.price_b == 0 or self.price_c == 0:
            return

        # TODO: 计算三角套利收益率
        # forward = (1 / price_a) * price_b * price_c
        # reverse = price_c / price_b / price_a
        # 注意：以上公式需根据实际交易对关系调整
        # if forward > 1 + min_profit_pct:
        #     执行正向套利
        # if reverse > 1 + min_profit_pct:
        #     执行反向套利
        pass

    def on_stop(self) -> None:
        for instrument_id in [
            self.config.pair_a_instrument_id,
            self.config.pair_b_instrument_id,
            self.config.pair_c_instrument_id,
        ]:
            self.cancel_all_orders(instrument_id)
            self.close_all_positions(instrument_id)

    def on_reset(self) -> None:
        self.price_a = 0.0
        self.price_b = 0.0
        self.price_c = 0.0

    def on_dispose(self) -> None:
        pass


register(
    StrategyMeta(
        key="triangular_arbitrage",
        name="Triangular Arbitrage",
        description="三角套利骨架：利用三个交易对价格不一致套利，需同时订阅三对行情",
        config_cls=TriangularArbitrageConfig,
        strategy_cls=TriangularArbitrage,
        default_params={
            "trade_size": Decimal("1000"),
            "min_profit_pct": Decimal("0.05"),
        },
    )
)
