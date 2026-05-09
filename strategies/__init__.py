from dataclasses import dataclass, field
from typing import Any

from nautilus_trader.config import StrategyConfig
from nautilus_trader.trading.strategy import Strategy


@dataclass
class StrategyMeta:
    """策略元信息，用于统一注册与动态加载。"""

    key: str
    name: str
    description: str
    config_cls: type[StrategyConfig]
    strategy_cls: type[Strategy]
    default_params: dict[str, Any] = field(default_factory=dict)


_REGISTRY: dict[str, StrategyMeta] = {}


def register(meta: StrategyMeta) -> None:
    """注册一个策略。"""
    if meta.key in _REGISTRY:
        raise ValueError(f"Strategy key '{meta.key}' already registered")
    _REGISTRY[meta.key] = meta


def get_strategy_meta(key: str) -> StrategyMeta:
    """通过 key 获取已注册的策略元信息。"""
    if key not in _REGISTRY:
        raise KeyError(f"Strategy '{key}' not found. Available: {list_strategies()}")
    return _REGISTRY[key]


def list_strategies() -> list[str]:
    """列出所有已注册的策略 key。"""
    return list(_REGISTRY.keys())
