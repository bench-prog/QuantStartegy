# 策略开发指南

本目录包含所有策略实现，按交易理念分为 7 个子目录。

## 目录结构

```
strategies/
├── __init__.py              # 策略注册中心（StrategyMeta + register）
├── trend_following/         # 趋势跟踪
├── mean_reversion/          # 均值回归
├── volatility/              # 波动率
├── pattern_recognition/     # 形态识别
├── cross_sectional/         # 截面/套利
├── orderbook_depth/         # 订单簿深度
├── smart_money/             # 聪明钱/市场结构
└── docs/                    # 分类概览 HTML（策略列表、参数速查等）
```

---

## 策略注册机制

策略通过 `register()` 函数注册元信息（key、名称、描述、配置类、策略类、默认参数），便于上层系统动态加载。

```python
from strategies import StrategyMeta, register

register(
    StrategyMeta(
        key="ema_cross",
        name="EMA Cross",
        description="快慢 EMA 交叉，金叉做多、死叉做空",
        config_cls=EMACrossConfig,
        strategy_cls=EMACross,
        default_params={"fast_ema_period": 10, "slow_ema_period": 20},
    )
)
```

注册后可通过 `get_strategy_meta("ema_cross")` 或 `list_strategies()` 查询。

---

## 开发规范

### 策略文件头格式

每个策略 `.py` 文件顶部必须包含统一格式的头注释：

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
| 分类 | ✅ | 中文分类名 + 子目录名 |
| 状态 | ✅ | `skeleton` / `backtest` / `paper` / `live` |
| 作者 | ✅ | 初始创建者 |
| 日期 | ✅ | 文件创建日期 `YYYY-MM-DD` |
| 概述 | ✅ | 2-3 句，说清策略做什么、核心原理 |
| 数据依赖 | ✅ | 仅需 OHLCV Bar/Tick 时写 `N/A`；需要 Level 2 / 订单簿 / 外部 API 时详述 |
| 参数 | ✅ | 列出 Config 类中的关键参数、说明和默认值 |
| TODO | ✅ | 待实现的功能点；无待办时写 `N/A` |
| 参考 | 可选 | 策略依据的论文、文章、数据源；无参考时写 `N/A` |

### 增加策略需同步更新文档

新增策略时，除了编写 `.py` 文件，还需完成以下文档同步：

1. **分类归属**：将策略放入正确的分类子目录
2. **分类概览 HTML**：更新对应分类的 `0x-xxx-overview.html`
   - 在"策略列表"中增加新策略的说明
   - 在"参数速查"表中补充关键参数和默认值
   - 如有必要，更新"回测建议"
3. **首页索引**：更新 `strategies/docs/00-overview.html` 中的策略总览表

---

## 参考

- [NautilusTrader 官方文档](https://nautilustrader.io/docs/)
- [API Reference](https://docs.nautilustrader.io/api_reference/)
