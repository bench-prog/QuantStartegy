# ============================================================================
# 策略名称：Liquidity Sweep / 流动性猎杀
# 分类：    聪明钱 (smart_money)
# 状态：    skeleton
# 作者：    cheristerfer
# 日期：    2026-05-08
# ============================================================================
# 概述：
#   检测价格突破近期高低点后迅速反转的猎杀行为：跌破 low 后收回 → 做多，
#   突破 high 后回落 → 做空。假定聪明钱故意触发止损盘获取流动性后反向操作。
#
# 数据依赖：N/A（仅需 OHLCV Bar）
#
# 参数：
#   instrument_id      — 合约
#   bar_type           — K 线类型
#   trade_size         — 下单数量（默认 100000）
#   lookback           — 高低点回溯 Bar 数（默认 10）
#   sweep_lookback     — 摆动点确认 Bar 数（默认 3）
#   close_threshold_pct — 收回比例阈值%（默认 0.5）
#
# TODO：
#   - [ ] 添加成交量确认（猎杀 K 线成交量放大）
#   - [ ] 多时间框架 Sweep 检测
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


class LiquiditySweepConfig(StrategyConfig, frozen=True):
    instrument_id: InstrumentId
    bar_type: BarType
    trade_size: Decimal
    lookback: PositiveInt = 10
    sweep_lookback: PositiveInt = 3
    close_threshold_pct: Decimal = Decimal("0.5")
    order_time_in_force: TimeInForce = TimeInForce.GTC


class LiquiditySweep(Strategy):
    """
    Liquidity Sweep (流动性猎杀) 策略。

    核心逻辑：
    -  聪明钱会故意推动价格突破近期高点/低点，
       猎杀该区域密集的止损单（流动性），随后迅速反转。
    -  Bullish Sweep：价格跌破近期低点（诱发空头止损），
       但收盘/后续 K 线收回至低点之上 → 跟随聪明钱做多。
    -  Bearish Sweep：价格突破近期高点（诱发多头止损），
       但收盘/后续 K 线回落至高点之下 → 跟随聪明钱做空。

    参数 `close_threshold_pct` 控制收回幅度的敏感度：
    价格突破高低点后，需要在该 K 线内收回一定比例才确认猎杀成功。
    """

    def __init__(self, config: LiquiditySweepConfig) -> None:
        super().__init__(config)
        self.instrument: Instrument = None
        self.bars: list[Bar] = []
        self.pending_sweep: str | None = None  # "bullish" or "bearish"

    def on_start(self) -> None:
        self.instrument = self.cache.instrument(self.config.instrument_id)
        if self.instrument is None:
            self.log.error(f"Could not find instrument for {self.config.instrument_id}")
            self.stop()
            return
        self.subscribe_bars(self.config.bar_type)

    def _recent_high_low(self) -> tuple[float, float]:
        recent = self.bars[-self.config.lookback :]
        high = max(float(b.high) for b in recent)
        low = min(float(b.low) for b in recent)
        return high, low

    def _detect_sweep(self, bar: Bar) -> None:
        if len(self.bars) < self.config.lookback + 1:
            return

        recent_high, recent_low = self._recent_high_low()
        curr_open = float(bar.open)
        curr_high = float(bar.high)
        curr_low = float(bar.low)
        curr_close = float(bar.close)

        threshold = float(self.config.close_threshold_pct) / 100.0

        # Bullish sweep: 跌破 recent_low 后收回
        if curr_low < recent_low:
            sweep_range = curr_high - curr_low
            if sweep_range == 0:
                return
            recovery = curr_close - recent_low
            recovery_pct = recovery / sweep_range
            if recovery_pct >= threshold:
                self.pending_sweep = "bullish"
                self.log.info(
                    f"Bullish sweep detected: broke low {recent_low:.5f}, closed {curr_close:.5f}",
                    color=LogColor.GREEN,
                )
            return

        # Bearish sweep: 突破 recent_high 后回落
        if curr_high > recent_high:
            sweep_range = curr_high - curr_low
            if sweep_range == 0:
                return
            rejection = recent_high - curr_close
            rejection_pct = rejection / sweep_range
            if rejection_pct >= threshold:
                self.pending_sweep = "bearish"
                self.log.info(
                    f"Bearish sweep detected: broke high {recent_high:.5f}, closed {curr_close:.5f}",
                    color=LogColor.RED,
                )

    def _execute_sweep_signal(self) -> None:
        if self.pending_sweep == "bullish":
            if self.portfolio.is_flat(self.config.instrument_id):
                self.buy()
            elif self.portfolio.is_net_short(self.config.instrument_id):
                self.close_all_positions(self.config.instrument_id)
                self.buy()
            self.pending_sweep = None
        elif self.pending_sweep == "bearish":
            if self.portfolio.is_flat(self.config.instrument_id):
                self.sell()
            elif self.portfolio.is_net_long(self.config.instrument_id):
                self.close_all_positions(self.config.instrument_id)
                self.sell()
            self.pending_sweep = None

    def on_bar(self, bar: Bar) -> None:
        if bar.is_single_price():
            return

        self.bars.append(bar)
        if len(self.bars) > 200:
            self.bars.pop(0)

        # 先执行上一根 K 线检测到的 sweep 信号
        self._execute_sweep_signal()

        # 检测当前 K 线是否形成 sweep
        self._detect_sweep(bar)

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
        self.pending_sweep = None

    def on_dispose(self) -> None:
        pass


register(
    StrategyMeta(
        key="liquidity_sweep",
        name="Liquidity Sweep",
        description="聪明钱流动性猎杀策略：价格突破近期高低点后迅速反转，跟随聪明钱方向入场",
        config_cls=LiquiditySweepConfig,
        strategy_cls=LiquiditySweep,
        default_params={
            "lookback": 10,
            "sweep_lookback": 3,
            "close_threshold_pct": 0.5,
            "trade_size": 100000,
        },
    )
)
