# ============================================================================
# 策略名称：On-Chain Analysis / 链上数据分析
# 分类：    聪明钱 (smart_money)
# 状态：    skeleton
# 作者：    cheristerfer
# 日期：    2026-05-08
# ============================================================================
# 概述：
#   利用区块链公开数据（MVRV、NUPL、交易所净流入/流出、巨鲸动向）综合评估
#   市场估值水平生成交易信号。多指标共振确认，适合日线/4H 级别运行。
#
# 数据依赖：需接入 Glassnode / CryptoQuant / Santiment 等链上数据 API，
#   仅凭 OHLCV 无法运行。大多数指标每日更新。
#
# 参数：
#   instrument_id              — 合约
#   bar_type                   — K 线类型
#   trade_size                 — 下单数量（默认 0.1）
#   exchange_outflow_threshold — 交易所流出阈值 BTC（默认 1000）
#   mvrv_overvalued            — MVRV 高估阈值（默认 3.5）
#   mvrv_undervalued           — MVRV 低估阈值（默认 1.0）
#
# TODO：
#   - [ ] 接入 Glassnode/CryptoQuant API
#   - [ ] 维护链上指标缓存（避免频繁调用 API）
#   - [ ] 定义多指标综合评分系统
#   - [ ] 考虑不同周期的链上数据
#   - [ ] 添加链上数据延迟的处理
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


class OnChainAnalysisConfig(StrategyConfig, frozen=True):
    """
    链上数据分析策略配置。

    本策略为骨架模板，核心逻辑依赖区块链链上数据。

    需要接入的外部数据：
    -  交易所流入/流出数据（Exchange Inflow/Outflow）
    -  巨鲸钱包监控（Whale Watching）
    -  长期持有者比例（HODL Waves）
    -  MVRV 比率（Market Value / Realized Value）
    -  NUPL（Net Unrealized Profit/Loss）

    数据来源：
    -  Glassnode API: studio.glassnode.com
    -  CryptoQuant: cryptoquant.com
    -  Santiment: santiment.net
    -  自建节点直接读取链上数据（Bitcoin Core, Geth）
    """

    instrument_id: InstrumentId
    bar_type: BarType
    trade_size: Decimal
    # 信号阈值
    exchange_outflow_threshold: Decimal = Decimal("1000")  # BTC
    mvrv_overvalued: Decimal = Decimal("3.5")
    mvrv_undervalued: Decimal = Decimal("1.0")


class OnChainAnalysis(Strategy):
    """
    链上数据分析策略骨架。

    核心逻辑：
    利用区块链的公开透明特性，将链上指标转化为交易信号。

    关键指标及信号解释：
    ========================================================================
    1. 交易所净流入/流出（Exchange Netflow）
       - 大额流入交易所 → 抛售压力 → 看跌信号
       - 大额流出交易所 → 屯币意愿 → 看涨信号
       - 阈值：单日 > 1000 BTC 可视为显著信号

    2. MVRV 比率
       - MVRV > 3.5：市场严重高估，考虑减仓/做空
       - MVRV < 1.0：市场严重低估，考虑加仓/做多
       - 历史上 MVRV < 1 对应 BTC 大底区域

    3. NUPL（净未实现盈亏）
       - NUPL > 0.5：市场进入狂热期，顶部信号
       - NUPL < 0：市场整体亏损，底部区域

    4. 长期持有者比例（HODL Waves）
       - 长期持有者增持 = 供应收紧 = 看涨
       - 长期持有者减持 = 供应释放 = 看跌

    5. 巨鲸动向（Whale Alert）
       - 巨鲸转入交易所 = 潜在抛售
       - 巨鲸从交易所转出 = 长期持有
    ========================================================================

    需要的外部数据及接入点：
    ========================================================================
    1. 链上数据 API
       - Glassnode: /v1/metrics/{category}/{metric}
       - CryptoQuant: /v1/exchange-flows
       - 需 API Key，通常有频率限制

    2. 数据更新频率
       - 大多数链上指标每日更新一次
       - 交易所净流入可接近实时（10-30分钟延迟）
       - 策略适合在日线/4小时级别运行

    3. 数据融合
       - 单一链上指标假信号较多
       - 建议多指标共振确认（如 MVRV + NUPL + Exchange Flow）
    ========================================================================

    实现 TODO：
    - [ ] 接入 Glassnode/CryptoQuant API
    - [ ] 维护链上指标缓存（避免频繁调用 API）
    - [ ] 定义多指标综合评分系统
    - [ ] 考虑不同周期的链上数据（日线 vs 周线）
    - [ ] 添加链上数据延迟的处理（使用上一日数据）
    """

    def __init__(self, config: OnChainAnalysisConfig) -> None:
        super().__init__(config)
        self.on_chain_data: dict[str, float] = {}
        self.last_update_time: int = 0

    def on_start(self) -> None:
        self.subscribe_bars(self.config.bar_type)
        # TODO: 初始化链上数据连接
        # self.on_chain_client = GlassnodeClient(api_key="...")
        # self._fetch_on_chain_data()

    def _fetch_on_chain_data(self) -> None:
        """获取链上数据，建议每根 K 线或每日调用一次。"""
        # TODO: 调用外部 API 获取指标
        # self.on_chain_data["mvrv"] = glassnode.get_mvrv()
        # self.on_chain_data["nupl"] = glassnode.get_nupl()
        # self.on_chain_data["exchange_netflow"] = glassnode.get_exchange_netflow()
        pass

    def on_bar(self, bar) -> None:
        # TODO: 定期刷新链上数据（避免每根 K 线都调用 API）
        # if bar.ts_event - self.last_update_time > update_interval:
        #     self._fetch_on_chain_data()
        #     self.last_update_time = bar.ts_event

        # TODO: 综合评估链上指标
        # score = 0
        # if self.on_chain_data.get("mvrv", 0) < mvrv_undervalued:
        #     score += 1
        # if self.on_chain_data.get("exchange_netflow", 0) < -threshold:
        #     score += 1
        # if self.on_chain_data.get("nupl", 0) < 0:
        #     score += 1
        # if score >= 2: buy()
        pass

    def on_stop(self) -> None:
        self.cancel_all_orders(self.config.instrument_id)
        self.close_all_positions(self.config.instrument_id)

    def on_reset(self) -> None:
        self.on_chain_data.clear()
        self.last_update_time = 0

    def on_dispose(self) -> None:
        pass


register(
    StrategyMeta(
        key="on_chain_analysis",
        name="On-Chain Analysis",
        description="链上数据分析骨架：利用MVRV、NUPL、交易所资金流等链上指标生成信号，需接入Glassnode/CryptoQuant",
        config_cls=OnChainAnalysisConfig,
        strategy_cls=OnChainAnalysis,
        default_params={
            "exchange_outflow_threshold": Decimal("1000"),
            "mvrv_overvalued": Decimal("3.5"),
            "mvrv_undervalued": Decimal("1.0"),
            "trade_size": Decimal("0.1"),
        },
    )
)
