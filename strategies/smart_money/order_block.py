# ============================================================================
# 策略名称：Order Block / 订单块（OB）
# 分类：    聪明钱 (smart_money)
# 状态：    skeleton
# 作者：    cheristerfer
# 日期：    2026-05-08
# ============================================================================
# 概述：
#   检测 swing high/low 形成前最后一根推动 K 线作为 Order Block（机构挂单区域），
#   价格回测该区域时入场。Bullish OB = 下跌推动前的 bearish K 线区间作为支撑，
#   Bearish OB = 上涨推动前的 bullish K 线区间作为阻力。
#
# 数据依赖：N/A（仅需 OHLCV Bar）
#
# 参数：
#   instrument_id  — 合约
#   bar_type       — K 线类型
#   trade_size     — 下单数量（默认 100000）
#   lookback       — OB 搜索回溯 Bar 数（默认 5）
#   swing_lookback — swing 确认 Bar 数（默认 3）
#   use_body_only  — 仅使用 K 线实体区间（默认 False）
#
# TODO：
#   - [ ] 多时间框架 OB 共振
#   - [ ] OB 被突破后标记为失效并重新检测
#
# 参考：
#   - ICT (Inner Circle Trader) Smart Money Concepts
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


class OrderBlockConfig(StrategyConfig, frozen=True):
    instrument_id: InstrumentId
    bar_type: BarType
    trade_size: Decimal
    lookback: PositiveInt = 5
    swing_lookback: PositiveInt = 3
    use_body_only: bool = False
    order_time_in_force: TimeInForce = TimeInForce.GTC


class OrderBlock(Strategy):
    """
    Order Block (订单块) 策略。

    核心逻辑：
    -  bullish order block：在一段下跌推动后价格反转，
       记录推动下跌前最后一根 bearish K 线的区间作为支撑区域，
       后续价格回测该区域时做多。
    -  bearish order block：在一段上涨推动后价格反转，
       记录推动上涨前最后一根 bullish K 线的区间作为阻力区域，
       后续价格回测该区域时做空。

    OB 的识别依赖 swing high / swing low 的确认。
    """

    def __init__(self, config: OrderBlockConfig) -> None:
        super().__init__(config)
        self.instrument: Instrument = None
        self.bars: list[Bar] = []
        self.bullish_ob: tuple[float, float] | None = None  # (low, high)
        self.bearish_ob: tuple[float, float] | None = None  # (low, high)

    def on_start(self) -> None:
        self.instrument = self.cache.instrument(self.config.instrument_id)
        if self.instrument is None:
            self.log.error(f"Could not find instrument for {self.config.instrument_id}")
            self.stop()
            return
        self.subscribe_bars(self.config.bar_type)

    def _is_swing_high(self, idx: int) -> bool:
        if idx < self.config.swing_lookback or idx >= len(self.bars) - self.config.swing_lookback:
            return False
        pivot_high = float(self.bars[idx].high)
        for i in range(1, self.config.swing_lookback + 1):
            if float(self.bars[idx - i].high) >= pivot_high:
                return False
            if float(self.bars[idx + i].high) >= pivot_high:
                return False
        return True

    def _is_swing_low(self, idx: int) -> bool:
        if idx < self.config.swing_lookback or idx >= len(self.bars) - self.config.swing_lookback:
            return False
        pivot_low = float(self.bars[idx].low)
        for i in range(1, self.config.swing_lookback + 1):
            if float(self.bars[idx - i].low) <= pivot_low:
                return False
            if float(self.bars[idx + i].low) <= pivot_low:
                return False
        return True

    def _detect_order_blocks(self) -> None:
        if len(self.bars) < self.config.lookback + self.config.swing_lookback * 2 + 1:
            return

        # 从后往前检测最近的 swing point
        for i in range(len(self.bars) - self.config.swing_lookback - 1, self.config.swing_lookback, -1):
            if self._is_swing_low(i):
                # 找 swing low 形成前的 bearish K 线（推动下跌的 K 线）
                for j in range(i - 1, max(i - self.config.lookback, -1), -1):
                    bar = self.bars[j]
                    if float(bar.close) < float(bar.open):  # bearish
                        if self.config.use_body_only:
                            low = min(float(bar.open), float(bar.close))
                            high = max(float(bar.open), float(bar.close))
                        else:
                            low = float(bar.low)
                            high = float(bar.high)
                        self.bullish_ob = (low, high)
                        self.log.info(f"Bullish OB detected @ idx={j}: {self.bullish_ob}", color=LogColor.GREEN)
                        break
                break

        for i in range(len(self.bars) - self.config.swing_lookback - 1, self.config.swing_lookback, -1):
            if self._is_swing_high(i):
                # 找 swing high 形成前的 bullish K 线（推动上涨的 K 线）
                for j in range(i - 1, max(i - self.config.lookback, -1), -1):
                    bar = self.bars[j]
                    if float(bar.close) > float(bar.open):  # bullish
                        if self.config.use_body_only:
                            low = min(float(bar.open), float(bar.close))
                            high = max(float(bar.open), float(bar.close))
                        else:
                            low = float(bar.low)
                            high = float(bar.high)
                        self.bearish_ob = (low, high)
                        self.log.info(f"Bearish OB detected @ idx={j}: {self.bearish_ob}", color=LogColor.RED)
                        break
                break

    def on_bar(self, bar: Bar) -> None:
        if bar.is_single_price():
            return

        self.bars.append(bar)
        if len(self.bars) > 200:
            self.bars.pop(0)

        self._detect_order_blocks()

        curr_low = float(bar.low)
        curr_high = float(bar.high)
        curr_close = float(bar.close)

        # 价格进入 bullish OB 区域 → 做多
        if self.bullish_ob is not None:
            ob_low, ob_high = self.bullish_ob
            if curr_low <= ob_high and curr_high >= ob_low:
                if self.portfolio.is_flat(self.config.instrument_id):
                    self.buy()
                elif self.portfolio.is_net_short(self.config.instrument_id):
                    self.close_all_positions(self.config.instrument_id)
                    self.buy()
                self.bullish_ob = None  # 消费掉

        # 价格进入 bearish OB 区域 → 做空
        if self.bearish_ob is not None:
            ob_low, ob_high = self.bearish_ob
            if curr_low <= ob_high and curr_high >= ob_low:
                if self.portfolio.is_flat(self.config.instrument_id):
                    self.sell()
                elif self.portfolio.is_net_long(self.config.instrument_id):
                    self.close_all_positions(self.config.instrument_id)
                    self.sell()
                self.bearish_ob = None  # 消费掉

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
        self.bars.clear()
        self.bullish_ob = None
        self.bearish_ob = None

    def on_dispose(self) -> None:
        pass


register(
    StrategyMeta(
        key="order_block",
        name="Order Block",
        description="聪明钱订单块策略：检测 swing high/low 形成前的推动 K 线作为 OB，价格回测 OB 区域时入场",
        config_cls=OrderBlockConfig,
        strategy_cls=OrderBlock,
        default_params={
            "lookback": 5,
            "swing_lookback": 3,
            "use_body_only": False,
            "trade_size": 100000,
        },
    )
)
