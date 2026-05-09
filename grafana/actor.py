"""
MetricsActor — 通过 NautilusTrader Actor 模型非侵入式收集策略事件。

订阅 MessageBus 上的订单成交/取消事件，自动转发到 InfluxDB。
策略代码无需任何改动，只需在引擎启动前：

    actor = MetricsActor(exporter, strategy_key="ema_cross")
    engine.add_actor(actor)
"""

from __future__ import annotations

from nautilus_trader.common.actor import Actor
from nautilus_trader.common.enums import LogColor
from nautilus_trader.model.events import OrderCanceled, OrderFilled
from nautilus_trader.model.objects import Price, Quantity

from grafana.exporter import InfluxMetricsExporter


class MetricsActor(Actor):
    """监控 Actor，自动收集策略的订单、成交事件并采样持仓。"""

    def __init__(
        self,
        exporter: InfluxMetricsExporter,
        strategy_key: str,
        instrument_id,
    ) -> None:
        super().__init__()
        self.exporter = exporter
        self.strategy_key = strategy_key
        self.instrument_id = instrument_id

    def on_start(self) -> None:
        self.log.info(f"MetricsActor started for {self.strategy_key}", color=LogColor.GREEN)
        self.subscribe_order_fills(self.instrument_id)
        self.subscribe_order_cancels(self.instrument_id)

    def on_stop(self) -> None:
        self.exporter.flush()

    # ------------------------------------------------------------------ #
    #  订单事件
    # ------------------------------------------------------------------ #

    def on_order_filled(self, event: OrderFilled) -> None:
        side = event.order_side.name
        price = (
            float(event.last_px.as_double())
            if isinstance(event.last_px, Price)
            else float(event.last_px)
        )
        qty = (
            float(event.last_qty.as_double())
            if isinstance(event.last_qty, Quantity)
            else float(event.last_qty)
        )
        ts = event.ts_event

        self.exporter.write_order(
            strategy=self.strategy_key,
            side=side,
            status="filled",
            price=price,
            quantity=qty,
            ts_ns=ts,
        )

        # 成交后采样当前持仓
        self._sample_positions(ts)

    def on_order_canceled(self, event: OrderCanceled) -> None:
        ts = event.ts_event
        self.exporter.write_order(
            strategy=self.strategy_key,
            side=event.order_side.name if hasattr(event, "order_side") else "UNKNOWN",
            status="canceled",
            price=0.0,
            quantity=0.0,
            ts_ns=ts,
        )

    # ------------------------------------------------------------------ #
    #  持仓采样
    # ------------------------------------------------------------------ #

    def _sample_positions(self, ts_ns: int) -> None:
        """通过 cache 采样 net 持仓状态。"""
        if self.cache is None:
            return
        net_qty = 0.0
        avg_price = 0.0
        for pos in self.cache.positions():
            if str(pos.instrument_id) == str(self.instrument_id):
                qty = float(pos.quantity.as_double())
                if pos.side.name == "SHORT":
                    net_qty -= qty
                else:
                    net_qty += qty
                if avg_price == 0.0:
                    avg_price = float(pos.avg_px_open)
        side = "FLAT" if net_qty == 0 else ("LONG" if net_qty > 0 else "SHORT")
        self.exporter.write_position(
            strategy=self.strategy_key,
            side=side,
            quantity=abs(net_qty),
            avg_price=avg_price,
            ts_ns=ts_ns,
        )

    # ------------------------------------------------------------------ #
    #  净值/信号采样（手动调用）
    # ------------------------------------------------------------------ #

    def sample_equity(self, total: float, pnl: float, ts_ns: int | None = None) -> None:
        """手动采样账户净值；ts_ns 未传时使用当前时间。"""
        if ts_ns is None:
            import time

            ts_ns = time.time_ns()
        self.exporter.write_equity(
            strategy=self.strategy_key,
            total=total,
            pnl=pnl,
            ts_ns=ts_ns,
        )

    def sample_signal(self, signal_type: str, price: float, ts_ns: int | None = None) -> None:
        """手动采样策略信号。"""
        if ts_ns is None:
            import time

            ts_ns = time.time_ns()
        self.exporter.write_signal(
            strategy=self.strategy_key,
            signal_type=signal_type,
            price=price,
            ts_ns=ts_ns,
        )
