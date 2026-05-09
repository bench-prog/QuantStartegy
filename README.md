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

### 1.7 Grafana监控面板

### 1.7.1 启动/停止监控栈
docker compose -f docker-compose.monitoring.yml up -d
docker compose -f docker-compose.monitoring.yml down

### 1.7.2 启动/停止 colima
colima start
colima stop

### 1.7.3 带监控回测
conda run -n nautilus_trader python backtest_one.py ema_cross --metrics

### 1.7.4 打开 Grafana
open http://localhost:3000/d/quant-backtest


## 2. 策略注册机制

策略通过 `register()` 函数注册元信息（key、名称、描述、配置类、策略类、默认参数），便于上层系统动态加载。

## 3. 开发规范

### 3.1 策略文件头格式

每个策略 `.py` 文件顶部必须包含统一格式的头注释，方便快速了解策略概况：

```python
# ============================================================================
# 策略名称：<English Name> / <中文名称>
# 分类：    <中文分类> (<directory_name>)
# 状态：    <skeleton|backtest|paper|live>
# 作者：    <author>
# 日期：    YYYY-MM-DD
# ============================================================================
# 概述：
#   <2-3 句描述策略核心逻辑和交易原理>
#
# 数据依赖：<N/A（仅需 OHLCV Bar）| 具体数据源描述>
#
# 参数：
#   param_name_1 — <说明>（默认 <value>）
#   param_name_2 — <说明>（默认 <value>）
#
# TODO：
#   - [ ] <待完成事项>
#
# 参考：
#   - <论文/文献/博客链接>
#   - N/A
# ============================================================================
```

**字段说明：**

| 字段 | 必填 | 说明 |
|------|------|------|
| 策略名称 | ✅ | 英文名与 `register()` 中 `key` 一致；中文名与 `name` 一致 |
| 分类 | ✅ | 中文分类名 + 子目录名（`trend_following` / `mean_reversion` / `volatility` / `cross_sectional` / `orderbook_depth` / `pattern_recognition` / `smart_money`） |
| 状态 | ✅ | `skeleton`（骨架）/ `backtest`（回测验证中）/ `paper`（模拟盘）/ `live`（实盘） |
| 作者 | ✅ | 初始创建者 |
| 日期 | ✅ | 文件创建日期，格式 `YYYY-MM-DD` |
| 概述 | ✅ | 2-3 句，说清策略做什么、核心原理 |
| 数据依赖 | ✅ | 仅需 OHLCV Bar/Tick 时写 `N/A（仅需 OHLCV Bar）`；需要 Level 2 / 订单簿 / 外部 API 时才详述 |
| 参数 | ✅ | 列出 Config 类中的关键参数、说明和默认值 |
| TODO | ✅ | 待实现的功能点；无待办时可写 `N/A` |
| 参考 | 可选 | 策略依据的论文、文章、数据源；无参考时写 `N/A` |

### 3.2 增加策略需同步更新文档

新增策略时，除了编写 `.py` 文件，还需完成以下文档同步：

1. **分类归属**：将策略放入正确的分类子目录（`trend_following/` / `mean_reversion/` / `volatility/` / `pattern_recognition/` / `cross_sectional/` / `orderbook_depth/`）
2. **分类概览 HTML**：更新对应分类的 `0x-xxx-overview.html`：
   - 在"策略列表"中增加新策略的说明
   - 在"参数速查"表中补充关键参数和默认值
   - 如有必要，更新"回测建议"
3. **首页索引**：更新 `strategies/README.html` 中的策略总览表和目录结构
4. **回测脚本**：如策略是常用模板，可在 `run_backtest.py` 中预留导入注释示例

> 文档与代码保持一致是多人协作和后续维护的基础。

## 4. 快速启动

- **回测**：修改 `run_backtest.py` 顶部的 `DATA_CSV`、`STRATEGY_CLS`、`STRATEGY_PARAMS`，然后 `python run_backtest.py`
- **实盘**：修改 `run_live.py` 顶部的 `STRATEGY` 和交易所网关配置（`DATA_CLIENTS` / `EXEC_CLIENTS`），然后 `python run_live.py`

两个脚本已包含完整的启动逻辑，仅需替换策略名称、合约代码和参数即可切换策略。

## 5. 参考

- [NautilusTrader 官方文档](https://nautilustrader.io/docs/)
- [API Reference](https://docs.nautilustrader.io/api_reference/)
