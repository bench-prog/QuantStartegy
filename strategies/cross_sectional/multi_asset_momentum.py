# ============================================================================
# 策略名称：Multi-Asset Momentum / 多资产动量轮动
# 分类：    跨品种套利 (cross_sectional)
# 状态：    skeleton
# 作者：    cheristerfer
# 日期：    2026-05-08
# ============================================================================
# 概述：
#   每 N 根 Bar 计算候选资产池中各项的动量（价格涨跌幅），按动量排序后
#   持有 Top-K 资产做多，淘汰末位资产。本质是横截面动量策略。
#
# 数据依赖：N/A（仅需 OHLCV Bar）
#
# 参数：
#   instrument_ids — 候选资产池
#   bar_type       — K 线类型
#   trade_size     — 下单数量（默认 100000）
#   lookback       — 动量计算回溯期 Bar 数（默认 20）
#   top_k          — 持有资产数量（默认 3）
#   rebalance_bars — 换仓间隔 Bar 数（默认 100）
#
# TODO：
#   - [ ] 添加做空方向（动量最差的 K 个做空）
#   - [ ] 添加波动率调整仓位
#
# 参考：
#   - Jegadeesh, N. & Titman, S. "Returns to Buying Winners and Selling Losers."
#     Journal of Finance, 1993.
# ============================================================================

from decimal import Decimal

from nautilus_trader.common.enums import LogColor
from nautilus_trader.config import PositiveInt, StrategyConfig
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.trading.strategy import Strategy

from strategies import StrategyMeta, register


class MultiAssetMomentumConfig(StrategyConfig, frozen=True):
    instrument_ids: list[InstrumentId]
    bar_type: BarType
    trade_size: Decimal
    lookback: PositiveInt = 20
    top_k: PositiveInt = 3
    rebalance_bars: PositiveInt = 100
    order_time_in_force: TimeInForce = TimeInForce.GTC


class MultiAssetMomentum(Strategy):
    def __init__(self, config: MultiAssetMomentumConfig) -> None:
        super().__init__(config)
        self.instruments: dict[InstrumentId, Instrument] = {}
        self.bar_count = 0

    def on_start(self) -> None:
        for instrument_id in self.config.instrument_ids:
            instrument = self.cache.instrument(instrument_id)
            if instrument is None:
                self.log.error(f"Could not find instrument for {instrument_id}")
                continue
            self.instruments[instrument_id] = instrument
            self.subscribe_bars(BarType.from_str(f"{instrument_id}-1-MINUTE-LAST-EXTERNAL"))

    def on_bar(self, bar: Bar) -> None:
        self.bar_count += 1
        if self.bar_count % self.config.rebalance_bars != 0:
            return

        scores = []
        for instrument_id in self.config.instrument_ids:
            bar_type = BarType.from_str(f"{instrument_id}-1-MINUTE-LAST-EXTERNAL")
            bars = self.cache.bars(bar_type)
            if len(bars) < self.config.lookback + 1:
                continue
            recent = list(bars)[-self.config.lookback:]
            if len(recent) < 2:
                continue
            start_price = float(recent[0].close)
            end_price = float(recent[-1].close)
            if start_price <= 0:
                continue
            momentum = (end_price - start_price) / start_price
            scores.append((instrument_id, momentum))

        if len(scores) < self.config.top_k:
            self.log.info(
                f"Not enough instruments for ranking ({len(scores)} < {self.config.top_k})",
                color=LogColor.BLUE,
            )
            return

        scores.sort(key=lambda x: x[1], reverse=True)
        top_k_ids = {s[0] for s in scores[:self.config.top_k]}

        self.log.info(
            f"Rebalance @ bar {self.bar_count}: top {self.config.top_k} = {[str(i) for i in top_k_ids]}",
            color=LogColor.CYAN,
        )

        for instrument_id in self.config.instrument_ids:
            is_top = instrument_id in top_k_ids
            is_long = self.portfolio.is_net_long(instrument_id)
            is_short = self.portfolio.is_net_short(instrument_id)
            is_flat = self.portfolio.is_flat(instrument_id)

            if is_top and is_flat:
                self._submit_market(instrument_id, OrderSide.BUY)
            elif is_top and is_short:
                self.close_all_positions(instrument_id)
                self._submit_market(instrument_id, OrderSide.BUY)
            elif not is_top and is_long:
                self.close_all_positions(instrument_id)

    def _submit_market(self, instrument_id: InstrumentId, side: OrderSide) -> None:
        instrument = self.instruments.get(instrument_id)
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
        for instrument_id in self.config.instrument_ids:
            self.cancel_all_orders(instrument_id)
            self.close_all_positions(instrument_id)

    def on_reset(self) -> None:
        self.bar_count = 0

    def on_dispose(self) -> None:
        pass


register(
    StrategyMeta(
        key="multi_asset_momentum",
        name="Multi-Asset Momentum",
        description="多资产动量轮动，按涨跌幅排序持有 Top-K",
        config_cls=MultiAssetMomentumConfig,
        strategy_cls=MultiAssetMomentum,
        default_params={
            "lookback": 20,
            "top_k": 3,
            "rebalance_bars": 100,
            "trade_size": 100000,
        },
    )
)
