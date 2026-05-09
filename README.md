# QuantStrategy — 基于 NautilusTrader 的量化策略仓库

本仓库基于 [NautilusTrader](https://nautilustrader.io) 构建，NautilusTrader 是一个高性能的量化交易框架，采用 **Actor 模型** 实现异步消息驱动的交易工作流。

## 1. 核心工作流

### 1.1 Actor 模型架构

NautilusTrader 的核心是 Actor 模型：

- **TradingNode**：运行时节点，统筹所有组件的生命周期
- **Actor**：业务逻辑单元（策略、风险模块、数据处理器等）
- **MessageBus**：组件间通过异步消息通信，无共享状态
- **三大引擎**：
  - `DataEngine` — 数据订阅、缓存、指标计算
  - `ExecutionEngine` — 订单路由、仓位管理、成交确认
  - `RiskEngine` — 事前风控检查（限额、黑名单等）

### 1.2 策略生命周期

策略继承自 `Strategy`，框架按以下顺序调用：

| 阶段 | 回调 | 职责 |
|------|------|------|
| 初始化 | `__init__` | 定义配置、创建指标实例 |
| 启动 | `on_start` | 订阅行情、注册指标、获取合约信息 |
| 数据驱动 | `on_bar` / `on_tick` / `on_quote` | 核心交易逻辑（信号 → 下单） |
| 事件处理 | `on_order_filled` / `on_position_opened` | 处理成交、仓位变化事件 |
| 停止 | `on_stop` | 撤单、平仓、释放资源 |
| 重置 | `on_reset` | 清空状态（用于回测分段） |
| 销毁 | `on_dispose` | 彻底清理（极少使用） |

### 1.3 数据流：订阅 → 信号 → 下单

```
DataEngine ──► Strategy.on_bar() ──► 信号判断 ──► order_factory.market()
                                            │
                                            ▼
                                    RiskEngine 风控检查
                                            │
                                            ▼
                                    ExecutionEngine ──► 交易所/模拟撮合
                                            │
                                            ▼
                                    Strategy.on_order_filled()
```

关键 API：
- `subscribe_bars(bar_type)` — 订阅 K 线
- `register_indicator_for_bars(bar_type, indicator)` — 指标自动随数据更新
- `indicators_initialized()` — 检查指标是否预热完成
- `cache.instrument(id)` / `cache.bar_count(type)` — 访问缓存数据

### 1.4 订单生命周期

```
order_factory.market() / limit() / stop_market()
        │
        ▼
submit_order(order)  ──►  ExecutionEngine  ──►  交易所
        │                                          │
        ▼                                          ▼
on_order_accepted()                        成交回报
        │                                          │
        ▼                                          ▼
on_order_filled()  ◄──────────────────────  Fill 事件
```

订单工厂支持：Market / Limit / StopMarket / StopLimit / TrailingStop 等类型。

### 1.5 回测与实盘代码统一

同一套 Strategy 代码既可用于：
- **回测**：`BacktestNode` + `BacktestEngine` 模拟撮合，支持 Tick 级精度
- **模拟盘**：`SimulatedVenue` 模拟交易所行为
- **实盘**：`LiveExecClient` 对接真实交易所（Binance、Interactive Brokers 等）

只需替换 `TradingNode` 的配置（数据源 + 执行网关），策略逻辑零改动。

### 1.6 配置驱动

策略通过 `StrategyConfig`（Pydantic BaseModel, frozen=True）声明参数，运行时由外部注入配置，策略本身无硬编码参数，便于批量回测和参数优化。

### 1.7 Grafana 监控

回测和实盘支持非侵入式指标导出到 InfluxDB + Grafana，详见 [`grafana/README.md`](grafana/README.md)。

---

## 2. 快速启动

- **回测**：修改 `run_backtest.py` 顶部的 `DATA_CSV`、`STRATEGY_CLS`、`STRATEGY_PARAMS`，然后 `python run_backtest.py`
- **实盘**：修改 `run_live.py` 顶部的 `STRATEGY` 和交易所网关配置（`DATA_CLIENTS` / `EXEC_CLIENTS`），然后 `python run_live.py`

两个脚本已包含完整的启动逻辑，仅需替换策略名称、合约代码和参数即可切换策略。

---

## 3. 子目录文档

| 目录 | 文档 | 内容 |
|------|------|------|
| `strategies/` | [`strategies/README.md`](strategies/README.md) | 策略注册机制、开发规范、文件头格式 |
| `grafana/` | [`grafana/README.md`](grafana/README.md) | 监控栈启动、数据模型、环境变量 |

---

## 4. 参考

- [NautilusTrader 官方文档](https://nautilustrader.io/docs/)
- [API Reference](https://docs.nautilustrader.io/api_reference/)
