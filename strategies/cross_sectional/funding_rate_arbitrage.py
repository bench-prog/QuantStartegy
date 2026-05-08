# ============================================================================
# 策略名称：Funding Rate Arbitrage / 资金费率套利
# 分类：    跨品种套利 (cross_sectional)
# 状态：    skeleton
# 作者：    cheristerfer
# 日期：    2026-05-08
# ============================================================================
# 概述：
#   做空高资金费率的永续合约，同时买入等值现货对冲，每 8 小时收取资金费。
#   费率转负或降至阈值以下时平仓退出，收益稳定且方向风险可控。
#
# 数据依赖：需同时订阅现货和永续合约 Bar；还需接入交易所资金费率数据（REST
#   API / WebSocket / DataClient），无法仅凭 OHLCV 运行。
#
# 参数：
#   spot_instrument_id — 现货合约
#   spot_bar_type      — 现货 K 线类型
#   perp_instrument_id — 永续合约
#   perp_bar_type      — 永续 K 线类型
#   hedge_size         — 对冲仓位数量（默认 0.1）
#   min_funding_rate   — 开仓资金费率阈值（默认 0.01%）
#   max_funding_rate   — 风控减仓费率阈值（默认 1%）
#
# TODO：
#   - [ ] 接入 FundingRate DataClient 或外部数据推送
#   - [ ] 实现 on_funding_rate() 回调处理资金费率更新
#   - [ ] 根据费率符号和大小触发开仓/平仓
#   - [ ] 添加基差监控，基差异常时触发风控平仓
#   - [ ] 考虑多币种资金费率轮动
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


class FundingRateArbitrageConfig(StrategyConfig, frozen=True):
    """
    资金费率套利配置。

    本策略为骨架模板，核心逻辑依赖外部资金费率数据，无法仅凭 K 线运行。

    需要接入的外部数据：
    -  永续合约实时资金费率（Funding Rate）
    -  来源：交易所 API（如 Binance /ft/fundingRate, OKX /api/v5/public/funding-rate）
    -  频率：通常每 8 小时结算一次

    数据接入方式建议：
    1.  在 NautilusTrader 中自定义 DataClient，订阅 funding_rate 类型数据
    2.  或通过 on_bar 中调用外部 REST API 获取（不推荐，延迟高）
    3.  使用 Redis/MQ 推送实时资金费率到策略的 MessageBus

    典型交易对示例：
    -  现货：BTCUSDT  (Binance Spot)
    -  永续：BTCUSDT  (Binance USDT-M Perp)
    """

    # 现货合约
    spot_instrument_id: InstrumentId
    spot_bar_type: BarType
    # 永续合约
    perp_instrument_id: InstrumentId
    perp_bar_type: BarType
    # 对冲仓位数量
    hedge_size: Decimal
    # 资金费率阈值：超过此值才开仓
    min_funding_rate: Decimal = Decimal("0.0001")  # 0.01%
    # 资金费率极值：超过此值触发减仓风控
    max_funding_rate: Decimal = Decimal("0.01")  # 1%


class FundingRateArbitrage(Strategy):
    """
    资金费率套利策略（骨架模板）。

    核心逻辑：
    -  当永续合约资金费率为正（多头付空头），做空永续 + 买入等值现货对冲。
    -  每 8 小时收取一次资金费，收益稳定且风险低。
    -  当资金费率转负或降至阈值以下，平仓退出。

    需要的外部数据及接入点：
    ========================================================================
    1. Funding Rate 数据流
       - 在 on_start() 中订阅 funding_rate 数据通道
       - 或在 on_bar() 中通过外部 API 轮询获取
       - 数据结构示例：{"symbol": "BTCUSDT", "fundingRate": "0.0003",
                        "fundingTime": 1710000000000}

    2. 双合约行情数据
       - 需要同时订阅现货和永续合约的 bar_type
       - 用于监控基差（basis = perp_price - spot_price）
       - 基差过大时需考虑展期或平仓

    3. 风控数据
       - 交易所维持保证金率（用于计算强平价）
       - 账户保证金水位（防止单侧爆仓）
    ========================================================================

    实现 TODO：
    - [ ] 接入 FundingRate DataClient 或外部数据推送
    - [ ] 实现 on_funding_rate() 回调处理资金费率更新
    - [ ] 根据资金费率符号和大小触发开仓/平仓
    - [ ] 添加基差监控，基差异常时触发风控平仓
    - [ ] 考虑多币种资金费率轮动（选择费率最高的币种做空）
    """

    def __init__(self, config: FundingRateArbitrageConfig) -> None:
        super().__init__(config)
        self.instrument_spot: Instrument | None = None
        self.instrument_perp: Instrument | None = None
        self.current_funding_rate: float = 0.0

    def on_start(self) -> None:
        self.instrument_spot = self.cache.instrument(self.config.spot_instrument_id)
        self.instrument_perp = self.cache.instrument(self.config.perp_instrument_id)

        if self.instrument_spot is None or self.instrument_perp is None:
            self.log.error("Could not find instruments for funding rate arbitrage")
            self.stop()
            return

        self.subscribe_bars(self.config.spot_bar_type)
        self.subscribe_bars(self.config.perp_bar_type)

        # TODO: 订阅 funding_rate 数据通道
        # 示例：self.subscribe_data(DataType(FundingRate, metadata={"symbol": "BTCUSDT"}))

    def on_bar(self, bar: Bar) -> None:
        # TODO: 在此处接入外部资金费率数据
        # 方式 1：从缓存读取已推送的 funding_rate 数据
        # 方式 2：调用外部 API（如 requests.get(exchange_funding_api)）

        # TODO: 核心交易逻辑
        # 1. 获取当前资金费率 self.current_funding_rate
        # 2. 获取现货价格和永续价格，计算基差
        # 3. 如果 funding_rate > min_funding_rate:
        #       - 做空永续 (SELL perp)
        #       - 买入现货 (BUY spot)
        # 4. 如果 funding_rate < 0 或 funding_rate 大幅下降:
        #       - 平掉对冲仓位
        # 5. 风控：检查基差是否异常扩大、保证金率是否安全
        pass

    def on_stop(self) -> None:
        self.cancel_all_orders(self.config.spot_instrument_id)
        self.cancel_all_orders(self.config.perp_instrument_id)
        self.close_all_positions(self.config.spot_instrument_id)
        self.close_all_positions(self.config.perp_instrument_id)

    def on_reset(self) -> None:
        self.current_funding_rate = 0.0

    def on_dispose(self) -> None:
        pass


register(
    StrategyMeta(
        key="funding_rate_arbitrage",
        name="Funding Rate Arbitrage",
        description="资金费率套利骨架：做空高费率永续合约+买入现货对冲，需接入外部资金费率数据流",
        config_cls=FundingRateArbitrageConfig,
        strategy_cls=FundingRateArbitrage,
        default_params={
            "hedge_size": Decimal("0.1"),
            "min_funding_rate": Decimal("0.0001"),
            "max_funding_rate": Decimal("0.01"),
        },
    )
)
