"""
Grafana / InfluxDB 监控模块

通过 MetricsActor 非侵入式收集策略事件，写入 InfluxDB，
由 Grafana 展示回测/实盘监控面板。

用法：
    from grafana import InfluxMetricsExporter, MetricsActor

    exporter = InfluxMetricsExporter(url="http://localhost:8086", token="...")
    actor = MetricsActor(exporter, strategy_key="ema_cross")
    engine.add_actor(actor)
"""

from grafana.exporter import InfluxMetricsExporter, MetricsPoint

__all__ = ["InfluxMetricsExporter", "MetricsPoint"]

try:
    from grafana.actor import MetricsActor

    __all__.append("MetricsActor")
except ImportError:
    pass  # nautilus_trader 未安装时跳过 Actor 导入
