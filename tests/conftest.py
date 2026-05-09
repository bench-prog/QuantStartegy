"""Pytest fixtures shared across the test suite."""

from __future__ import annotations

from decimal import Decimal

import pandas as pd
import pytest
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.data import BarType
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.objects import Money
from nautilus_trader.persistence.wranglers import BarDataWrangler
from nautilus_trader.test_kit.providers import TestInstrumentProvider


@pytest.fixture
def gbpusd_instrument():
    """Return a GBP/USD FX instrument for testing."""
    venue = Venue("SIM")
    return TestInstrumentProvider.default_fx_ccy("GBP/USD", venue=venue)


@pytest.fixture
def sample_bars(gbpusd_instrument):
    """Return a small set of OHLCV bars for smoke testing (200 bars)."""
    csv_path = "data/fxcm/gbpusd-m1-ask-2012.csv"
    fallback_path = "tests/fixtures/gbpusd_sample.csv"
    import os

    csv_path = csv_path if os.path.exists(csv_path) else fallback_path
    df = pd.read_csv(csv_path, index_col="timestamp", parse_dates=True)
    df = df.head(200)

    bar_type = BarType.from_str(f"{gbpusd_instrument.id}-1-MINUTE-LAST-EXTERNAL")
    wrangler = BarDataWrangler(bar_type, gbpusd_instrument)
    bars = wrangler.process(df)
    return bars, bar_type


@pytest.fixture
def starting_balance():
    """Return default starting balance for backtests."""
    return Money(1_000_000, USD)


@pytest.fixture
def default_venue():
    """Return default simulated venue."""
    return Venue("SIM")


@pytest.fixture
def default_trade_size():
    """Return default trade size for tests."""
    return Decimal("100000")
