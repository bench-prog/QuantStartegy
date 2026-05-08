# ============================================================================
# 策略名称：Fair Value Gap / 公允价值缺口（FVG）
# 分类：    聪明钱 (smart_money)
# 状态：    skeleton
# 作者：    cheristerfer
# 日期：    2026-05-08
# ============================================================================
# 概述：
#   检测 3-K 线结构中留下的不平衡缺口（当前 K 线 low > 前两根 high 为 bullish
#   FVG，反之 bearish FVG）。价格回测缺口时入场，假定机构会回补该区域获取流动性。
#
# 数据依赖：N/A（仅需 OHLCV Bar）
#
# 参数：
#   instrument_id     — 合约
#   bar_type          — K 线类型
#   trade_size        — 下单数量（默认 100000）
#   min_gap_multiplier — 最小缺口大小（× ATR，默认 1.0）
#
# TODO：
#   - [ ] 缺口大小过滤（基于 ATR 或成交量加权）
#   - [ ] 缺口时效性管理（过期缺口自动清除）
#
# 参考：
#   - ICT (Inner Circle Trader) Smart Money Concepts
# ============================================================================

from decimal import Decimal

from nautilus_trader.common.enums import LogColor
from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.trading.strategy import Strategy

from strategies import StrategyMeta, register


class FVGConfig(StrategyConfig, frozen=True):
    instrument_id: InstrumentId
    bar_type: BarType
    trade_size: Decimal
    min_gap_multiplier: Decimal = Decimal("1.0")
    order_time_in_force: TimeInForce = TimeInForce.GTC


class FVGGap(Strategy):
    """
    Fair Value Gap (公允价值缺口) 策略。

    核心逻辑：
    -  Bullish FVG：当前 K 线 low 高于前两根 K 线的 high，
       中间留下一个向上的不平衡区域 (gap_low, gap_high)。
       价格后续回测该缺口时做多。
    -  Bearish FVG：当前 K 线 high 低于前两根 K 线的 low，
       中间留下一个向下的不平衡区域 (gap_low, gap_high)。
       价格后续回测该缺口时做空。

    缺口存续期间，机构往往会回补该区域以获取流动性。
    """

    def __init__(self, config: FVGConfig) -> None:
        super().__init__(config)
        self.instrument: Instrument = None
        self.bars: list[Bar] = []
        self.bullish_fvgs: list[tuple[float, float]] = []  # (gap_low, gap_high)
        self.bearish_fvgs: list[tuple[float, float]] = []  # (gap_low, gap_high)

    def on_start(self) -> None:
        self.instrument = self.cache.instrument(self.config.instrument_id)
        if self.instrument is None:
            self.log.error(f"Could not find instrument for {self.config.instrument_id}")
            self.stop()
            return
        self.subscribe_bars(self.config.bar_type)

    def _detect_fvg(self) -> None:
        if len(self.bars) < 3:
            return

        c = self.bars[-1]
        b = self.bars[-2]
        a = self.bars[-3]

        # Bullish FVG: c.low > a.high
        if float(c.low) > float(a.high):
            gap_low = float(a.high)
            gap_high = float(c.low)
            gap_size = gap_high - gap_low
            atr = self._estimate_atr()
            if atr is None or gap_size >= float(self.config.min_gap_multiplier) * atr:
                self.bullish_fvgs.append((gap_low, gap_high))
                self.log.info(
                    f"Bullish FVG detected: {gap_low:.5f} - {gap_high:.5f}",
                    color=LogColor.GREEN,
                )

        # Bearish FVG: c.high < a.low
        if float(c.high) < float(a.low):
            gap_low = float(c.high)
            gap_high = float(a.low)
            gap_size = gap_high - gap_low
            atr = self._estimate_atr()
            if atr is None or gap_size >= float(self.config.min_gap_multiplier) * atr:
                self.bearish_fvgs.append((gap_low, gap_high))
                self.log.info(
                    f"Bearish FVG detected: {gap_low:.5f} - {gap_high:.5f}",
                    color=LogColor.RED,
                )

    def _estimate_atr(self) -> float | None:
        if len(self.bars) < 14:
            return None
        ranges = []
        for i in range(-14, 0):
            bar = self.bars[i]
            ranges.append(float(bar.high) - float(bar.low))
        return sum(ranges) / len(ranges)

    def _clean_expired_fvgs(self, curr_close: float) -> None:
        # 如果价格完全穿过 FVG 区域，认为缺口已失效
        self.bullish_fvgs = [
            (lo, hi) for lo, hi in self.bullish_fvgs
            if curr_close > lo
        ]
        self.bearish_fvgs = [
            (lo, hi) for lo, hi in self.bearish_fvgs
            if curr_close < hi
        ]

    def on_bar(self, bar: Bar) -> None:
        if bar.is_single_price():
            return

        self.bars.append(bar)
        if len(self.bars) > 200:
            self.bars.pop(0)

        self._detect_fvg()

        curr_low = float(bar.low)
        curr_high = float(bar.high)
        curr_close = float(bar.close)

        # 价格回测 bullish FVG → 做多
        for fvg in self.bullish_fvgs[:]:
            gap_low, gap_high = fvg
            if curr_low <= gap_high and curr_high >= gap_low:
                if self.portfolio.is_flat(self.config.instrument_id):
                    self.buy()
                elif self.portfolio.is_net_short(self.config.instrument_id):
                    self.close_all_positions(self.config.instrument_id)
                    self.buy()
                self.bullish_fvgs.remove(fvg)
                break

        # 价格回测 bearish FVG → 做空
        for fvg in self.bearish_fvgs[:]:
            gap_low, gap_high = fvg
            if curr_low <= gap_high and curr_high >= gap_low:
                if self.portfolio.is_flat(self.config.instrument_id):
                    self.sell()
                elif self.portfolio.is_net_long(self.config.instrument_id):
                    self.close_all_positions(self.config.instrument_id)
                    self.sell()
                self.bearish_fvgs.remove(fvg)
                break

        self._clean_expired_fvgs(curr_close)

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
        self.bullish_fvgs.clear()
        self.bearish_fvgs.clear()

    def on_dispose(self) -> None:
        pass


register(
    StrategyMeta(
        key="fvg_gap",
        name="Fair Value Gap",
        description="聪明钱 FVG 策略：检测 3-K 线结构留下的不平衡缺口，价格回补缺口时入场",
        config_cls=FVGConfig,
        strategy_cls=FVGGap,
        default_params={
            "min_gap_multiplier": 1.0,
            "trade_size": 100000,
        },
    )
)
