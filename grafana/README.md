# Grafana 监控模块

非侵入式回测/实盘监控，基于 InfluxDB 2.x + Grafana。

## 快速开始

```bash
# 1. 启动 InfluxDB + Grafana
docker compose -f docker-compose.monitoring.yml up -d

# 2. 安装依赖（如未安装）
pip install influxdb-client

# 3. 带监控运行单策略回测
python backtest_one.py ema_cross --metrics

# 4. 打开 Grafana 查看面板
open http://localhost:3000/d/quant-backtest
```

## 架构

```
Strategy.on_order_filled() ──► MessageBus ──► MetricsActor ──► InfluxDB ──► Grafana
```

策略代码零改动，通过 `MetricsActor` 订阅事件实现监控。

## 数据模型

| Measurement | Tags | Fields | 用途 |
|---|---|---|---|
| `equity` | `strategy`, `run_id` | `total`, `pnl` | 净值曲线 |
| `orders` | `strategy`, `run_id`, `side`, `status` | `price`, `quantity` | 订单事件 |
| `positions` | `strategy`, `run_id`, `side` | `quantity`, `avg_price` | 仓位快照 |
| `trades` | `strategy`, `run_id`, `side` | `entry_price`, `exit_price`, `pnl` | 平仓盈亏 |
| `signals` | `strategy`, `run_id`, `type` | `price` | 策略信号 |
| `bars` | `instrument`, `bar_type` | `open`, `high`, `low`, `close`, `volume` | K线（可选） |

## 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `INFLUX_URL` | `http://localhost:8086` | InfluxDB 地址 |
| `INFLUX_TOKEN` | `quant-token-change-me` | InfluxDB API token |

## 文件结构

```
grafana/
├── __init__.py          # 包入口
├── exporter.py          # InfluxDB 写入封装
├── actor.py             # MetricsActor（NautilusTrader Actor）
├── dashboards/
│   └── backtest.json    # 预置回测监控面板
└── provisioning/
    ├── datasource.yml   # 数据源自动配置
    └── dashboard.yml    # 面板自动加载
```
