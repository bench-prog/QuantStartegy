# ============================================================================
# 策略名称：Pair Trading / 配对交易
# 分类：    跨品种套利 (cross_sectional)
# 状态：    skeleton
# 作者：    cheristerfer
# 日期：    2026-05-08
# ============================================================================
# 概述：
#   基于两个高度相关资产的价差均值回归特性。计算价差 Z-Score，Z 超过
#   entry_z 时做空强势资产 + 做多弱势资产，Z 回归至 exit_z 内时平仓。
#
# 数据依赖：N/A（仅需 OHLCV Bar）
#
# 参数：
#   instrument_id_a — 资产 A
#   instrument_id_b — 资产 B
#   bar_type        — K 线类型
#   trade_size      — 下单数量（默认 100000）
#   lookback        — 价差统计窗口 Bar 数（默认 60）
#   entry_z         — 入场 Z-Score 阈值（默认 2.0）
#   exit_z          — 平仓 Z-Score 阈值（默认 0.5）
#
# TODO：
#   - [ ] 添加协整检验筛选配对
#   - [ ] 支持多配对组合管理
#
# 参考：
#   - Gatev, E., et al. "Pairs Trading: Performance of a Relative-Value
#     Arbitrage Rule." RFS, 2006.
# ============================================================================

from decimal import Decimal
from statistics import mean, stdev

from nautilus_trader.common.enums import LogColor
from nautilus_trader.config import PositiveInt, StrategyConfig
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.trading.strategy import Strategy

from strategies import StrategyMeta, register


class PairTradingConfig(StrategyConfig, frozen=True):
    instrument_id_a: InstrumentId
    instrument_id_b: InstrumentId
    bar_type: BarType
    trade_size: Decimal
    lookback: PositiveInt = 60
    entry_z: Decimal = Decimal("2.0")
    exit_z: Decimal = Decimal("0.5")
    order_time_in_force: TimeInForce = TimeInForce.GTC


class PairTrading(Strategy):
    def __init__(self, config: PairTradingConfig) -> None:
        super().__init__(config)
        self.instrument_a: Instrument | None = None
        self.instrument_b: Instrument | None = None
        self.spread_history: list[float] = []

    def on_start(self) -> None:
        self.instrument_a = self.cache.instrument(self.config.instrument_id_a)
        self.instrument_b = self.cache.instrument(self.config.instrument_id_b)
        if self.instrument_a is None or self.instrument_b is None:
            self.log.error("Could not find one or both instruments")
            self.stop()
            return
        self.subscribe_bars(
            BarType.from_str(f"{self.config.instrument_id_a}-1-MINUTE-LAST-EXTERNAL")
        )
        self.subscribe_bars(
            BarType.from_str(f"{self.config.instrument_id_b}-1-MINUTE-LAST-EXTERNAL")
        )

    def on_bar(self, bar: Bar) -> None:
        bar_type_a = BarType.from_str(f"{self.config.instrument_id_a}-1-MINUTE-LAST-EXTERNAL")
        bar_type_b = BarType.from_str(f"{self.config.instrument_id_b}-1-MINUTE-LAST-EXTERNAL")

        bars_a = self.cache.bars(bar_type_a)
        bars_b = self.cache.bars(bar_type_b)

        if len(bars_a) == 0 or len(bars_b) == 0:
            return

        price_a = float(list(bars_a)[-1].close)
        price_b = float(list(bars_b)[-1].close)
        spread = price_a - price_b
        self.spread_history.append(spread)

        if len(self.spread_history) < self.config.lookback:
            self.log.info(
                f"Warming up spread history [{len(self.spread_history)}/{self.config.lookback}]",
                color=LogColor.BLUE,
            )
            return

        window = self.spread_history[-self.config.lookback :]
        mu = mean(window)
        sigma = stdev(window) if len(window) > 1 else 1.0
        z_score = (spread - mu) / sigma if sigma > 0 else 0.0

        entry_z = float(self.config.entry_z)
        exit_z = float(self.config.exit_z)

        long_a = self.portfolio.is_net_long(self.config.instrument_id_a)
        short_a = self.portfolio.is_net_short(self.config.instrument_id_a)
        long_b = self.portfolio.is_net_long(self.config.instrument_id_b)
        short_b = self.portfolio.is_net_short(self.config.instrument_id_b)

        if z_score > entry_z and not short_a and not long_b:
            self.log.info(
                f"Spread Z={z_score:.2f} > {entry_z}: SHORT A / LONG B", color=LogColor.MAGENTA
            )
            if not self.portfolio.is_flat(self.config.instrument_id_a):
                self.close_all_positions(self.config.instrument_id_a)
            if not self.portfolio.is_flat(self.config.instrument_id_b):
                self.close_all_positions(self.config.instrument_id_b)
            self._submit_market(self.config.instrument_id_a, OrderSide.SELL)
            self._submit_market(self.config.instrument_id_b, OrderSide.BUY)

        elif z_score < -entry_z and not long_a and not short_b:
            self.log.info(
                f"Spread Z={z_score:.2f} < -{entry_z}: LONG A / SHORT B", color=LogColor.MAGENTA
            )
            if not self.portfolio.is_flat(self.config.instrument_id_a):
                self.close_all_positions(self.config.instrument_id_a)
            if not self.portfolio.is_flat(self.config.instrument_id_b):
                self.close_all_positions(self.config.instrument_id_b)
            self._submit_market(self.config.instrument_id_a, OrderSide.BUY)
            self._submit_market(self.config.instrument_id_b, OrderSide.SELL)

        elif abs(z_score) < exit_z and (long_a or short_a or long_b or short_b):
            self.log.info(f"Spread Z={z_score:.2f} within ±{exit_z}: EXIT", color=LogColor.YELLOW)
            self.close_all_positions(self.config.instrument_id_a)
            self.close_all_positions(self.config.instrument_id_b)

    def _submit_market(self, instrument_id: InstrumentId, side: OrderSide) -> None:
        instrument = (
            self.instrument_a if instrument_id == self.config.instrument_id_a else self.instrument_b
        )
        if instrument is None:
            return
        order = self.order_factory.market(
            instrument_id=instrument_id,
            order_side=side,
            quantity=instrument.make_qty(self.config.trade_size),
            time_in_force=self.config.order_time_in_force,
        )
        self.submit_order(order)

    def on_stop(self) -> None:
        self.cancel_all_orders(self.config.instrument_id_a)
        self.cancel_all_orders(self.config.instrument_id_b)
        self.close_all_positions(self.config.instrument_id_a)
        self.close_all_positions(self.config.instrument_id_b)

    def on_reset(self) -> None:
        self.spread_history.clear()

    def on_dispose(self) -> None:
        pass


register(
    StrategyMeta(
        key="pair_trading",
        name="Pair Trading",
        description="配对交易，基于价差的均值回归，Z-Score 偏离入场、回归平仓",
        config_cls=PairTradingConfig,
        strategy_cls=PairTrading,
        default_params={
            "lookback": 60,
            "entry_z": 2.0,
            "exit_z": 0.5,
            "trade_size": 100000,
        },
    )
)
