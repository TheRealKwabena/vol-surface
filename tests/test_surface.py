"""Tests for surface coordinate construction and arbitrage detection."""

import numpy as np
import pandas as pd

from vol_surface.surface.build import (
    add_surface_coordinates,
    check_calendar_arbitrage,
    check_butterfly_arbitrage,
)


def test_add_surface_coordinates():
    df = pd.DataFrame({"strike": [90, 100, 110], "T": [0.5, 0.5, 0.5], "iv": [0.25, 0.20, 0.22], "forward": [100, 100, 100]})
    out = add_surface_coordinates(df)
    assert np.isclose(out.loc[out["strike"] == 100, "log_moneyness"].iloc[0], 0.0)
    assert np.isclose(out.loc[out["strike"] == 90, "log_moneyness"].iloc[0], np.log(0.9))
    assert np.isclose(out["total_variance"].iloc[1], 0.20**2 * 0.5)


def test_calendar_arbitrage_detects_decreasing_total_variance():
    # Same log-moneyness bucket, total variance decreases from T=0.1 to T=0.5 -- a violation.
    df = pd.DataFrame(
        {
            "strike": [100, 100],
            "forward": [100, 100],
            "T": [0.1, 0.5],
            "iv": [0.30, 0.10],  # w = 0.09*0.1=0.009 then 0.01*0.5=0.005 -> decreasing
        }
    )
    df = add_surface_coordinates(df)
    violations = check_calendar_arbitrage(df)
    assert len(violations) == 1


def test_calendar_arbitrage_clean_surface_has_no_violations():
    df = pd.DataFrame(
        {
            "strike": [100, 100, 100],
            "forward": [100, 100, 100],
            "T": [0.1, 0.3, 0.5],
            "iv": [0.20, 0.20, 0.20],  # constant vol -> w strictly increasing in T
        }
    )
    df = add_surface_coordinates(df)
    violations = check_calendar_arbitrage(df)
    assert len(violations) == 0


def test_butterfly_arbitrage_detects_non_convex_calls():
    # Strikes 95, 100, 105 with call prices that are concave (not convex) at 100.
    df = pd.DataFrame(
        {
            "expiry": ["2099-01-01"] * 3,
            "strike": [95, 100, 105],
            "call_mid": [10.0, 6.0, 1.0],  # slopes: -4/5=-0.8, then -5/5=-1.0 -> decreasing slope = concave
        }
    )
    violations = check_butterfly_arbitrage(df)
    assert len(violations) == 1


def test_butterfly_arbitrage_convex_calls_pass():
    df = pd.DataFrame(
        {
            "expiry": ["2099-01-01"] * 3,
            "strike": [95, 100, 105],
            "call_mid": [10.0, 6.5, 4.0],  # slopes: -0.7, then -0.5 -> increasing slope = convex
        }
    )
    violations = check_butterfly_arbitrage(df)
    assert len(violations) == 0
