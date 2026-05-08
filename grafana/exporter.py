"""
InfluxDB 2.x 指标导出器

封装 influxdb-client，提供量化交易专用的写入接口。
支持批量写入、自动重试、本地队列缓冲。
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from datetime import datetime, timezone
from typing import Any


# influxdb-client 为可选依赖；未安装时 graceful degrade
try:
    from influxdb_client import InfluxDBClient, Point
    from influxdb_client.client.write_api import ASYNCHRONOUS, SYNCHRONOUS

    _HAS_INFLUXDB = True
except ImportError:
    _HAS_INFLUXDB = False


DEFAULT_BUCKET = "quant_strategy"
DEFAULT_ORG = "quant"


@dataclass
class MetricsPoint:
    """单个指标点，内部统一转为 InfluxDB Point。"""

    measurement: str
    tags: dict[str, str] = field(default_factory=dict)
    fields: dict[str, float | int | str | bool] = field(default_factory=dict)
    timestamp_ns: int | None = None  # Unix nanoseconds

    def to_influx_point(self) -> Any:
        if not _HAS_INFLUXDB:
            raise RuntimeError("influxdb-client not installed")
        p = Point(self.measurement)
        for k, v in self.tags.items():
            p = p.tag(k, v)
        for k, v in self.fields.items():
            if isinstance(v, bool):
                p = p.field(k, v)
            elif isinstance(v, (int, float)):
                p = p.field(k, float(v))
            elif isinstance(v, Decimal):
                p = p.field(k, float(v))
            else:
                p = p.field(k, str(v))
        if self.timestamp_ns is not None:
            p = p.time(self.timestamp_ns)
        return p


class InfluxMetricsExporter:
    """InfluxDB 指标导出器。

    Parameters
    ----------
    url : str
        InfluxDB 地址，例如 http://localhost:8086
    token : str
        InfluxDB API token（至少需要有 write 权限）
    org : str
        InfluxDB organization，默认 "quant"
    bucket : str
        InfluxDB bucket，默认 "quant_strategy"
    batch_size : int
        批量写入条数，默认 500
    flush_interval_sec : float
        自动 flush 间隔，默认 5.0 秒
    enabled : bool
        是否启用写入，默认 True；设为 False 时所有写入变为 no-op
    """

    def __init__(
        self,
        url: str = "http://localhost:8086",
        token: str = "quant-token-change-me",
        org: str = DEFAULT_ORG,
        bucket: str = DEFAULT_BUCKET,
        batch_size: int = 500,
        flush_interval_sec: float = 5.0,
        enabled: bool = True,
    ) -> None:
        self.url = url
        self.token = token
        self.org = org
        self.bucket = bucket
        self.batch_size = batch_size
        self.flush_interval_sec = flush_interval_sec
        self.enabled = enabled

        self._client: Any | None = None
        self._write_api: Any | None = None
        self._buffer: list[MetricsPoint] = []
        self._lock = threading.Lock()
        self._run_id = uuid.uuid4().hex[:12]
        self._closed = False

        if enabled and _HAS_INFLUXDB:
            self._client = InfluxDBClient(url=url, token=token, org=org)
            self._write_api = self._client.write_api(write_options=ASYNCHRONOUS)
            self._start_flusher()
        elif enabled and not _HAS_INFLUXDB:
            import warnings

            warnings.warn(
                "influxdb-client not installed; metrics will be logged to stdout only. "
                "Install with: pip install influxdb-client",
                stacklevel=2,
            )

    # ------------------------------------------------------------------ #
    #  便捷写入接口
    # ------------------------------------------------------------------ #

    def write_equity(self, strategy: str, total: float, pnl: float, ts_ns: int) -> None:
        """写入账户净值。"""
        self._push(
            MetricsPoint(
                measurement="equity",
                tags={"strategy": strategy, "run_id": self._run_id},
                fields={"total": total, "pnl": pnl},
                timestamp_ns=ts_ns,
            )
        )

    def write_order(
        self,
        strategy: str,
        side: str,
        status: str,
        price: float,
        quantity: float,
        ts_ns: int,
    ) -> None:
        """写入订单事件。"""
        self._push(
            MetricsPoint(
                measurement="orders",
                tags={"strategy": strategy, "run_id": self._run_id, "side": side, "status": status},
                fields={"price": price, "quantity": quantity},
                timestamp_ns=ts_ns,
            )
        )

    def write_position(
        self,
        strategy: str,
        side: str,
        quantity: float,
        avg_price: float,
        ts_ns: int,
    ) -> None:
        """写入仓位快照。"""
        self._push(
            MetricsPoint(
                measurement="positions",
                tags={"strategy": strategy, "run_id": self._run_id, "side": side},
                fields={"quantity": quantity, "avg_price": avg_price},
                timestamp_ns=ts_ns,
            )
        )

    def write_trade(
        self,
        strategy: str,
        side: str,
        quantity: float,
        entry_price: float,
        exit_price: float,
        pnl: float,
        ts_ns: int,
    ) -> None:
        """写入单笔交易（平仓后）。"""
        self._push(
            MetricsPoint(
                measurement="trades",
                tags={"strategy": strategy, "run_id": self._run_id, "side": side},
                fields={
                    "quantity": quantity,
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "pnl": pnl,
                },
                timestamp_ns=ts_ns,
            )
        )

    def write_signal(
        self,
        strategy: str,
        signal_type: str,
        price: float,
        ts_ns: int,
    ) -> None:
        """写入策略信号（如 crossover, overbought）。"""
        self._push(
            MetricsPoint(
                measurement="signals",
                tags={"strategy": strategy, "run_id": self._run_id, "type": signal_type},
                fields={"price": price},
                timestamp_ns=ts_ns,
            )
        )

    def write_bar(
        self,
        instrument: str,
        bar_type: str,
        open_p: float,
        high_p: float,
        low_p: float,
        close_p: float,
        volume: float,
        ts_ns: int,
    ) -> None:
        """写入 K 线数据（可选，用于图表叠加）。"""
        self._push(
            MetricsPoint(
                measurement="bars",
                tags={"instrument": instrument, "bar_type": bar_type},
                fields={
                    "open": open_p,
                    "high": high_p,
                    "low": low_p,
                    "close": close_p,
                    "volume": volume,
                },
                timestamp_ns=ts_ns,
            )
        )

    # ------------------------------------------------------------------ #
    #  内部方法
    # ------------------------------------------------------------------ #

    def _push(self, point: MetricsPoint) -> None:
        if not self.enabled:
            return
        with self._lock:
            self._buffer.append(point)
            if len(self._buffer) >= self.batch_size:
                self._flush()

    def _flush(self) -> None:
        if not self._buffer:
            return
        batch = self._buffer[:]
        self._buffer = []

        if self._write_api is not None:
            points = [p.to_influx_point() for p in batch]
            self._write_api.write(bucket=self.bucket, record=points)
        else:
            # influxdb-client 未安装时打印到 stdout
            import sys

            for p in batch:
                if p.timestamp_ns:
                    ts = datetime.fromtimestamp(p.timestamp_ns / 1e9, tz=timezone.utc).isoformat()
                else:
                    ts = "now"
                print(f"[METRICS] {ts} {p.measurement} {p.tags} {p.fields}")
            sys.stdout.flush()

    def _start_flusher(self) -> None:
        def _loop() -> None:
            while True:
                time.sleep(self.flush_interval_sec)
                with self._lock:
                    self._flush()

        t = threading.Thread(target=_loop, daemon=True, name="influx-flusher")
        t.start()

    def close(self) -> None:
        """关闭连接前强制 flush 剩余数据。可安全多次调用。"""
        with self._lock:
            self._flush()
        if self._closed:
            return
        self._closed = True
        if self._write_api is not None:
            self._write_api.close()
        if self._client is not None:
            self._client.close()

    def __enter__(self) -> InfluxMetricsExporter:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
