# ============================================================================
# 策略名称：Volatility Cone / 波动率锥
# 分类：    波动率 (volatility)
# 状态：    skeleton
# 作者：    cheristerfer
# 日期：    2026-05-08
# ============================================================================
# 概述：
#   将当前期权隐含波动率（IV）与各周期的历史已实现波动率（RV）分布对比，
#   形成"波动率锥"。IV 处于历史极低分位时做多波动率（买入跨式），处于极高
#   分位时做空波动率（卖出跨式），配合 Delta 对冲维持方向中性。
#
# 数据依赖：需接入期权 IV 数据（Deribit / OKX Options API），仅凭 OHLCV 无法
#   运行。RV 可从 K 线计算。
#
# 参数：
#   instrument_id      — 合约
#   bar_type           — K 线类型
#   trade_size         — 下单数量（默认 1）
#   rv_lookback_days   — RV 计算回溯天数（默认 30）
#   iv_percentile_low  — 做多波动率百分位阈值（默认 20%）
#   iv_percentile_high — 做空波动率百分位阈值（默认 80%）
#
# TODO：
#   - [ ] 接入期权 IV DataClient
#   - [ ] 计算并维护历史 RV 分布（不同周期）
#   - [ ] 构建波动率锥，判断当前 IV 分位
#   - [ ] 选择合适到期日的 ATM 期权组合
#   - [ ] Delta 对冲和动态调仓
#   - [ ] 到期前展期管理
#
# 参考：
#   - N/A
# ============================================================================

from decimal import Decimal

from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.trading.strategy import Strategy

from strategies import StrategyMeta, register


class VolatilityConeConfig(StrategyConfig, frozen=True):
    """
    波动率锥策略配置。

    本策略为骨架模板，核心逻辑依赖期权隐含波动率（IV）数据。

    需要接入的外部数据：
    -  期权链的隐含波动率（IV）曲面数据
    -  历史已实现波动率（RV），可从 K 线数据计算
    -  来源：Deribit / OKX / Binance Options API

    数据结构示例：
    {
        "instrument": "BTC-240628-50000-C",
        "strike": 50000,
        "expiry": "2024-06-28",
        "iv": 0.55,      # 隐含波动率
        "delta": 0.25,
        "vega": 12.5,
    }
    """

    instrument_id: InstrumentId
    bar_type: BarType
    trade_size: Decimal
    # 历史波动率计算周期（天数）
    rv_lookback_days: int = 30
    # 波动率百分位阈值：当前 IV < 20% 分位 → 做多波动率；> 80% → 做空
    iv_percentile_low: Decimal = Decimal("20")
    iv_percentile_high: Decimal = Decimal("80")


class VolatilityCone(Strategy):
    """
    波动率锥（Volatility Cone）策略骨架。

    核心逻辑：
    -  计算不同时间周期（7d, 30d, 60d, 90d）的历史已实现波动率（RV）分布。
    -  将当前期权 IV 与历史 RV 分布对比，形成"波动率锥"。
    -  当 IV 处于历史极低分位（<20%）→ 做多波动率（买入跨式/宽跨式）。
    -  当 IV 处于历史极高分位（>80%）→ 做空波动率（卖出跨式/宽跨式）。

    需要的外部数据及接入点：
    ========================================================================
    1. 期权 IV 数据流
       - 需接入期权交易所的期权链数据
       - 获取 ATM（平值）期权的 IV 作为市场隐含波动率基准
       - Deribit API: /public/get_book_summary_by_currency
       - OKX API: /api/v5/public/opt-summary

    2. 历史 RV 数据
       - 可从 K 线数据计算：RV = std(returns) × sqrt(365)
       - 需维护不同周期的滚动 RV 历史分布

    3. 期权希腊字母（风控用）
       - Delta 对冲：保持 Delta-neutral
       - Vega 暴露：监控波动率敞口
       - Theta 衰减：时间价值损耗
    ========================================================================

    实现 TODO：
    - [ ] 接入期权 IV DataClient
    - [ ] 计算并维护历史 RV 分布（不同周期）
    - [ ] 构建波动率锥，判断当前 IV 分位
    - [ ] 选择合适到期日的 ATM 期权组合
    - [ ] Delta 对冲和动态调仓
    - [ ] 到期前展期（Roll）管理
    """

    def __init__(self, config: VolatilityConeConfig) -> None:
        super().__init__(config)
        self.bars: list = []
        self.current_iv: float = 0.0
        self.rv_history: dict[int, list[float]] = {}  # days -> list of RV

    def on_start(self) -> None:
        self.subscribe_bars(self.config.bar_type)
        # TODO: 订阅期权 IV 数据通道
        # self.subscribe_data(DataType(OptionIV, metadata={...}))

    def on_bar(self, bar) -> None:
        # 维护 K 线缓存用于计算 RV
        self.bars.append(bar)
        if len(self.bars) > 500:
            self.bars.pop(0)

        # TODO: 计算滚动 RV
        # returns = [log(close[i] / close[i-1]) for i in range(1, len)]
        # rv = std(returns) * sqrt(365)

        # TODO: 获取当前 IV 并与历史分布比较
        # percentile = percentile_rank(current_iv, historical_ivs)
        # if percentile < iv_percentile_low: 买入跨式
        # if percentile > iv_percentile_high: 卖出跨式
        pass

    def on_stop(self) -> None:
        self.cancel_all_orders(self.config.instrument_id)
        self.close_all_positions(self.config.instrument_id)

    def on_reset(self) -> None:
        self.bars.clear()
        self.current_iv = 0.0
        self.rv_history.clear()

    def on_dispose(self) -> None:
        pass


register(
    StrategyMeta(
        key="volatility_cone",
        name="Volatility Cone",
        description="波动率锥骨架：对比期权IV与历史RV分布，极值分位时做多/做空波动率，需接入期权数据",
        config_cls=VolatilityConeConfig,
        strategy_cls=VolatilityCone,
        default_params={
            "rv_lookback_days": 30,
            "iv_percentile_low": Decimal("20"),
            "iv_percentile_high": Decimal("80"),
            "trade_size": Decimal("1"),
        },
    )
)
