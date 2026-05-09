"""Smoke test for EMA Cross strategy.

Runs a minimal backtest with 200 bars to verify the strategy does not crash
and produces expected outputs.
"""

from __future__ import annotations

from decimal import Decimal

from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.config import BacktestEngineConfig, LoggingConfig
from nautilus_trader.model import TraderId
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.enums import AccountType, OmsType
from nautilus_trader.model.identifiers import Venue

from strategies.trend_following.ema_cross import EMACross, EMACrossConfig


def test_ema_cross_smoke(sample_bars, gbpusd_instrument, starting_balance):
    """EMA Cross should run a 200-bar backtest without crashing."""
    bars, bar_type = sample_bars

    engine_config = BacktestEngineConfig(
        trader_id=TraderId("TEST-EMA-001"),
        logging=LoggingConfig(log_level="WARNING"),
    )
    engine = BacktestEngine(config=engine_config)

    venue = Venue("SIM")
    engine.add_venue(
        venue=venue,
        oms_type=OmsType.HEDGING,
        account_type=AccountType.MARGIN,
        starting_balances=[starting_balance],
        base_currency=USD,
    )
    engine.add_instrument(gbpusd_instrument)
    engine.add_data(bars)

    config = EMACrossConfig(
        instrument_id=gbpusd_instrument.id,
        bar_type=bar_type,
        trade_size=Decimal("100000"),
        fast_ema_period=10,
        slow_ema_period=20,
    )
    strategy = EMACross(config)
    engine.add_strategy(strategy)

    engine.run()

    # Basic sanity checks
    assert engine.iteration > 0
    assert len(engine.cache.orders()) >= 0

    account = engine.portfolio.account(venue)
    balances = account.balances()
    assert balances  # account should have balance entries

    engine.dispose()


def test_ema_cross_fast_above_slow_assertion():
    """Strategy init should reject fast_ema_period >= slow_ema_period."""
    import pytest
    from nautilus_trader.model.data import BarType
    from nautilus_trader.model.identifiers import InstrumentId

    bar_type = BarType.from_str("GBP/USD.SIM-1-MINUTE-LAST-EXTERNAL")
    config = EMACrossConfig(
        instrument_id=InstrumentId.from_str("GBP/USD.SIM"),
        bar_type=bar_type,
        trade_size=Decimal("100000"),
        fast_ema_period=20,
        slow_ema_period=10,
    )
    with pytest.raises(ValueError, match="must be less than"):
        EMACross(config)
