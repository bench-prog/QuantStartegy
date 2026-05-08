# ============================================================================
# 策略名称：Basis Trading / 期现套利
# 分类：    跨品种套利 (cross_sectional)
# 状态：    skeleton
# 作者：    cheristerfer
# 日期：    2026-05-08
# ============================================================================
# 概述：
#   利用期货与现货之间的基差（Basis = F - S）收敛特性套利。Contango 时
#   买入现货 + 做空期货，持有至到期收敛获利；Backwardation 时反向操作。
#
# 数据依赖：需同时订阅现货和期货两个 Bar 行情；交割合约还需到期日信息。
#
# 参数：
#   spot_instrument_id     — 现货合约
#   spot_bar_type          — 现货 K 线类型
#   futures_instrument_id  — 期货合约
#   futures_bar_type       — 期货 K 线类型
#   trade_size             — 下单数量（默认 0.1）
#   min_basis_annual_pct   — 开仓年化基差阈值（默认 5.0%）
#   close_basis_annual_pct — 平仓年化基差阈值（默认 1.0%）
#
# TODO：
#   - [ ] 计算实时基差和年化基差并触发开平仓
#   - [ ] 处理交割合约到期展期（换月）
#   - [ ] 计入手续费和滑点对套利空间的侵蚀
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


class BasisTradingConfig(StrategyConfig, frozen=True):
    """
    期现套利（基差交易）配置。

    本策略为骨架模板，核心逻辑需同时订阅期货和现货行情。

    需要接入的数据：
    -  现货行情（如 BTCUSDT Spot）
    -  交割/永续期货行情（如 BTCUSDT Quarterly）
    -  期货到期日信息（交割合约需要）
    """

    spot_instrument_id: InstrumentId
    spot_bar_type: BarType
    futures_instrument_id: InstrumentId
    futures_bar_type: BarType
    trade_size: Decimal
    # 开仓基差阈值：年化基差超过此值才开仓
    min_basis_annual_pct: Decimal = Decimal("5.0")
    # 平仓基差阈值：年化基差低于此值平仓
    close_basis_annual_pct: Decimal = Decimal("1.0")


class BasisTrading(Strategy):
    """
    期现套利（基差交易）策略骨架。

    核心逻辑：
    -  Contango（期货溢价）时：买入现货 + 做空期货，到期收敛获利
    -  Backwardation（期货折价）时：做反向操作（需借币做空现货）

    需要的外部数据及接入点：
    ========================================================================
    1. 双合约行情
       - 同时订阅现货和期货的 bar_type
       - 在 on_bar() 中根据 bar.bar_type 区分数据来源

    2. 期货到期信息
       - 交割合约需知道到期时间 T
       - 年化基差 = (F - S) / S × 365 / T_days
       - 来源：交易所合约信息 API

    3. 资金成本
       - 现货买入需要 USDT（资金占用）
       - 期货做空需要保证金
       - 需计算综合资金成本，确保套利收益 > 成本
    ========================================================================

    实现 TODO：
    - [ ] 在 on_bar() 中分别处理现货和期货 bar，维护最新价格
    - [ ] 计算实时基差和年化基差
    - [ ] 根据基差阈值触发开仓/平仓
    - [ ] 处理交割合约的到期展期（换月）
    - [ ] 考虑交易手续费和滑点对套利空间的侵蚀
    """

    def __init__(self, config: BasisTradingConfig) -> None:
        super().__init__(config)
        self.instrument_spot: Instrument | None = None
        self.instrument_futures: Instrument | None = None
        self.spot_price: float = 0.0
        self.futures_price: float = 0.0

    def on_start(self) -> None:
        self.instrument_spot = self.cache.instrument(self.config.spot_instrument_id)
        self.instrument_futures = self.cache.instrument(self.config.futures_instrument_id)

        if self.instrument_spot is None or self.instrument_futures is None:
            self.log.error("Could not find instruments for basis trading")
            self.stop()
            return

        self.subscribe_bars(self.config.spot_bar_type)
        self.subscribe_bars(self.config.futures_bar_type)

    def on_bar(self, bar: Bar) -> None:
        # 根据 bar_type 区分数据来源
        if bar.bar_type == self.config.spot_bar_type:
            self.spot_price = float(bar.close)
        elif bar.bar_type == self.config.futures_bar_type:
            self.futures_price = float(bar.close)

        if self.spot_price == 0 or self.futures_price == 0:
            return

        # TODO: 计算年化基差
        # basis = (futures_price - spot_price) / spot_price
        # annual_basis = basis * 365 / days_to_expiry
        # if annual_basis > min_basis_annual_pct:
        #     买入现货 + 做空期货
        # elif annual_basis < close_basis_annual_pct:
        #     平仓
        pass

    def on_stop(self) -> None:
        self.cancel_all_orders(self.config.spot_instrument_id)
        self.cancel_all_orders(self.config.futures_instrument_id)
        self.close_all_positions(self.config.spot_instrument_id)
        self.close_all_positions(self.config.futures_instrument_id)

    def on_reset(self) -> None:
        self.spot_price = 0.0
        self.futures_price = 0.0

    def on_dispose(self) -> None:
        pass


register(
    StrategyMeta(
        key="basis_trading",
        name="Basis Trading",
        description="期现套利骨架：利用期货与现货的基差收敛获利，需同时订阅双合约行情",
        config_cls=BasisTradingConfig,
        strategy_cls=BasisTrading,
        default_params={
            "trade_size": Decimal("0.1"),
            "min_basis_annual_pct": Decimal("5.0"),
            "close_basis_annual_pct": Decimal("1.0"),
        },
    )
)
