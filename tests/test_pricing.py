"""
Correctness tests for the pricing engine.

  1. Closed-form Greeks vs. finite-difference bumps of the same pricer.
  2. Put-call parity holding to (near) machine precision.
  3. Re-pricing with a solved IV recovers the original market price
     (round-trip test for the IV solver).

If these three pass, the pricing engine and IV solver are almost
certainly correct.
"""

import numpy as np
import pytest

from vol_surface.pricing.black_scholes import (
    bsm_price,
    bsm_greeks,
    finite_difference_greeks,
    black76_price,
)
from vol_surface.pricing.implied_vol import implied_vol_black76
from vol_surface.pricing.forward import imply_forward_and_discount

# A grid of "reasonable" market scenarios to test across: ATM, ITM, OTM,
# short-dated, long-dated, high vol, low vol.
SCENARIOS = [
    dict(S=100, K=100, T=1.0, r=0.03, q=0.01, sigma=0.20),
    dict(S=100, K=120, T=1.0, r=0.03, q=0.01, sigma=0.20),
    dict(S=100, K=80, T=1.0, r=0.03, q=0.01, sigma=0.20),
    dict(S=100, K=100, T=0.05, r=0.03, q=0.01, sigma=0.20),
    dict(S=100, K=100, T=2.0, r=0.03, q=0.01, sigma=0.60),
    dict(S=4500, K=4600, T=0.25, r=0.045, q=0.015, sigma=0.15),
]


@pytest.mark.parametrize("scenario", SCENARIOS)
@pytest.mark.parametrize("option_type", ["call", "put"])
def test_greeks_match_finite_difference(scenario, option_type):
    closed = bsm_greeks(**scenario, option_type=option_type)
    fd = finite_difference_greeks(**scenario, option_type=option_type)

    # Tolerances are relative, with a small absolute floor for
    # Greeks that pass through zero (e.g. deep OTM gamma).
    def close(a, b, rtol=1e-2, atol=1e-4):
        return abs(a - b) <= atol + rtol * abs(b)

    assert close(closed.delta, fd.delta), f"delta {closed.delta} vs fd {fd.delta}"
    assert close(closed.gamma, fd.gamma), f"gamma {closed.gamma} vs fd {fd.gamma}"
    assert close(closed.vega, fd.vega), f"vega {closed.vega} vs fd {fd.vega}"
    assert close(closed.theta, fd.theta, rtol=2e-2), f"theta {closed.theta} vs fd {fd.theta}"
    assert close(closed.rho, fd.rho), f"rho {closed.rho} vs fd {fd.rho}"
    assert close(closed.vanna, fd.vanna, rtol=5e-2), f"vanna {closed.vanna} vs fd {fd.vanna}"
    assert close(closed.volga, fd.volga, rtol=5e-2), f"volga {closed.volga} vs fd {fd.volga}"
    assert close(closed.charm, fd.charm, rtol=5e-2, atol=1e-3), f"charm {closed.charm} vs fd {fd.charm}"


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_put_call_parity_spot_form(scenario):
    call = bsm_price(**scenario, option_type="call")
    put = bsm_price(**scenario, option_type="put")
    S, K, T, r, q = scenario["S"], scenario["K"], scenario["T"], scenario["r"], scenario["q"]
    # C - P = S e^{-qT} - K e^{-rT}
    rhs = S * np.exp(-q * T) - K * np.exp(-r * T)
    assert abs((call - put) - rhs) < 1e-9


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_put_call_parity_forward_form(scenario):
    F = scenario["S"] * np.exp((scenario["r"] - scenario["q"]) * scenario["T"])
    disc = np.exp(-scenario["r"] * scenario["T"])
    call = black76_price(F, scenario["K"], scenario["T"], r=0.0, sigma=scenario["sigma"], option_type="call", disc=disc)
    put = black76_price(F, scenario["K"], scenario["T"], r=0.0, sigma=scenario["sigma"], option_type="put", disc=disc)
    rhs = disc * (F - scenario["K"])
    assert abs((call - put) - rhs) < 1e-9


@pytest.mark.parametrize("scenario", SCENARIOS)
@pytest.mark.parametrize("option_type", ["call", "put"])
def test_iv_roundtrip(scenario, option_type):
    """Price with a known sigma, solve IV back out, confirm we recover it."""
    F = scenario["S"] * np.exp((scenario["r"] - scenario["q"]) * scenario["T"])
    disc = np.exp(-scenario["r"] * scenario["T"])
    true_sigma = scenario["sigma"]

    price = black76_price(F, scenario["K"], scenario["T"], r=0.0, sigma=true_sigma, option_type=option_type, disc=disc)

    result = implied_vol_black76(
        target_price=price, F=F, K=scenario["K"], T=scenario["T"], disc=disc, option_type=option_type,
    )
    assert result.converged, f"IV solve failed to converge: {result}"
    assert abs(result.iv - true_sigma) < 1e-6, f"recovered {result.iv}, expected {true_sigma}"

    # Also confirm re-pricing at the recovered IV reproduces the original price.
    repriced = black76_price(F, scenario["K"], scenario["T"], r=0.0, sigma=result.iv, option_type=option_type, disc=disc)
    assert abs(repriced - price) < 1e-6


def test_iv_solver_rejects_arbitrage_violating_price():
    """A price above the discounted forward can't be rationalized by any vol."""
    F, K, T, disc = 100.0, 100.0, 1.0, 0.97
    absurd_price = F * disc * 1.5  # way above the max possible call value
    result = implied_vol_black76(target_price=absurd_price, F=F, K=K, T=T, disc=disc, option_type="call")
    assert not result.converged
    assert result.iv is None


def test_iv_solver_uses_newton_fastpath_when_reliable():
    """Sanity check that the Newton fast path actually engages for a liquid ATM case."""
    F, K, T, disc = 100.0, 100.0, 1.0, 0.97
    price = black76_price(F, K, T, r=0.0, sigma=0.25, option_type="call", disc=disc)
    result = implied_vol_black76(target_price=price, F=F, K=K, T=T, disc=disc, option_type="call")
    assert result.method == "newton"


def test_implied_forward_recovers_known_forward_and_discount():
    """Construct synthetic call/put prices from a known F and disc, confirm the
    OLS parity fit recovers both exactly (up to floating point)."""
    true_F, true_disc = 105.0, 0.965
    strikes = np.array([90.0, 95.0, 100.0, 105.0, 110.0, 115.0, 120.0])
    sigma = 0.22
    T = 0.5

    calls = np.array([black76_price(true_F, k, T, r=0.0, sigma=sigma, option_type="call", disc=true_disc) for k in strikes])
    puts = np.array([black76_price(true_F, k, T, r=0.0, sigma=sigma, option_type="put", disc=true_disc) for k in strikes])

    fit = imply_forward_and_discount(strikes, calls, puts, T, expiry_label="test")

    assert abs(fit.forward - true_F) < 1e-6
    assert abs(fit.discount_factor - true_disc) < 1e-6
    assert fit.r_squared > 0.999999
