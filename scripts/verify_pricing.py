"""
Plain-assertion verification of the pricing engine, surface construction,
and IV solver -- no pytest required.

This exists because the sandbox this project was originally built in had
network egress restricted to a small allowlist that did not include PyPI,
so pytest (and yfinance/streamlit/plotly) could not be installed there to
run tests/test_pricing.py and tests/test_surface.py directly, even though
numpy/scipy/pandas were already available.

This script exercises the exact same logic and scenarios as those two test
files, as plain Python asserts, run with `python3 scripts/verify_pricing.py`.
It is not a replacement for actually running `pytest tests/ -v` once you
have normal internet access -- do that too.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from vol_surface.pricing.black_scholes import bsm_price, bsm_greeks, finite_difference_greeks, black76_price
from vol_surface.pricing.implied_vol import implied_vol_black76
from vol_surface.pricing.forward import imply_forward_and_discount
from vol_surface.surface.build import add_surface_coordinates, check_calendar_arbitrage, check_butterfly_arbitrage

PASS = 0
FAIL = 0


def check(name, condition):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  OK   {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name}")


SCENARIOS = [
    dict(S=100, K=100, T=1.0, r=0.03, q=0.01, sigma=0.20),
    dict(S=100, K=120, T=1.0, r=0.03, q=0.01, sigma=0.20),
    dict(S=100, K=80, T=1.0, r=0.03, q=0.01, sigma=0.20),
    dict(S=100, K=100, T=0.05, r=0.03, q=0.01, sigma=0.20),
    dict(S=100, K=100, T=2.0, r=0.03, q=0.01, sigma=0.60),
    dict(S=4500, K=4600, T=0.25, r=0.045, q=0.015, sigma=0.15),
]


def close(a, b, rtol, atol):
    return abs(a - b) <= atol + rtol * abs(b)


print("=== 1. Closed-form Greeks vs finite difference ===")
for scenario in SCENARIOS:
    for option_type in ["call", "put"]:
        closed = bsm_greeks(**scenario, option_type=option_type)
        fd = finite_difference_greeks(**scenario, option_type=option_type)
        label = f"{scenario} {option_type}"
        check(f"delta  {label}", close(closed.delta, fd.delta, 1e-2, 1e-4))
        check(f"gamma  {label}", close(closed.gamma, fd.gamma, 1e-2, 1e-4))
        check(f"vega   {label}", close(closed.vega, fd.vega, 1e-2, 1e-4))
        check(f"theta  {label}", close(closed.theta, fd.theta, 2e-2, 1e-4))
        check(f"rho    {label}", close(closed.rho, fd.rho, 1e-2, 1e-4))
        check(f"vanna  {label}", close(closed.vanna, fd.vanna, 5e-2, 1e-4))
        check(f"volga  {label}", close(closed.volga, fd.volga, 5e-2, 1e-4))
        check(f"charm  {label}", close(closed.charm, fd.charm, 5e-2, 1e-3))

print("\n=== 2. Put-call parity (spot form) ===")
for scenario in SCENARIOS:
    call = bsm_price(**scenario, option_type="call")
    put = bsm_price(**scenario, option_type="put")
    S, K, T, r, q = scenario["S"], scenario["K"], scenario["T"], scenario["r"], scenario["q"]
    rhs = S * np.exp(-q * T) - K * np.exp(-r * T)
    check(f"parity spot {scenario}", abs((call - put) - rhs) < 1e-9)

print("\n=== 3. Put-call parity (forward form / Black-76) ===")
for scenario in SCENARIOS:
    F = scenario["S"] * np.exp((scenario["r"] - scenario["q"]) * scenario["T"])
    disc = np.exp(-scenario["r"] * scenario["T"])
    call = black76_price(F, scenario["K"], scenario["T"], r=0.0, sigma=scenario["sigma"], option_type="call", disc=disc)
    put = black76_price(F, scenario["K"], scenario["T"], r=0.0, sigma=scenario["sigma"], option_type="put", disc=disc)
    rhs = disc * (F - scenario["K"])
    check(f"parity fwd {scenario}", abs((call - put) - rhs) < 1e-9)

print("\n=== 4. IV round-trip ===")
for scenario in SCENARIOS:
    for option_type in ["call", "put"]:
        F = scenario["S"] * np.exp((scenario["r"] - scenario["q"]) * scenario["T"])
        disc = np.exp(-scenario["r"] * scenario["T"])
        true_sigma = scenario["sigma"]
        price = black76_price(F, scenario["K"], scenario["T"], r=0.0, sigma=true_sigma, option_type=option_type, disc=disc)
        result = implied_vol_black76(target_price=price, F=F, K=scenario["K"], T=scenario["T"], disc=disc, option_type=option_type)
        label = f"{scenario} {option_type}"
        check(f"iv converged {label}", result.converged)
        if result.converged:
            check(f"iv recovered {label} (got {result.iv:.6f}, want {true_sigma})", abs(result.iv - true_sigma) < 1e-6)
            repriced = black76_price(F, scenario["K"], scenario["T"], r=0.0, sigma=result.iv, option_type=option_type, disc=disc)
            check(f"iv repriced matches {label}", abs(repriced - price) < 1e-6)

print("\n=== 5. IV solver edge cases ===")
F, K, T, disc = 100.0, 100.0, 1.0, 0.97
absurd_price = F * disc * 1.5
result = implied_vol_black76(target_price=absurd_price, F=F, K=K, T=T, disc=disc, option_type="call")
check("rejects arbitrage-violating price", not result.converged and result.iv is None)

price = black76_price(F, K, T, r=0.0, sigma=0.25, option_type="call", disc=disc)
result = implied_vol_black76(target_price=price, F=F, K=K, T=T, disc=disc, option_type="call")
check("newton fastpath engages for liquid ATM case", result.method == "newton")

print("\n=== 6. Implied forward/discount recovery ===")
true_F, true_disc = 105.0, 0.965
strikes = np.array([90.0, 95.0, 100.0, 105.0, 110.0, 115.0, 120.0])
sigma, T = 0.22, 0.5
calls = np.array([black76_price(true_F, k, T, r=0.0, sigma=sigma, option_type="call", disc=true_disc) for k in strikes])
puts = np.array([black76_price(true_F, k, T, r=0.0, sigma=sigma, option_type="put", disc=true_disc) for k in strikes])
fit = imply_forward_and_discount(strikes, calls, puts, T, expiry_label="test")
check(f"forward recovered (got {fit.forward:.6f}, want {true_F})", abs(fit.forward - true_F) < 1e-6)
check(f"discount recovered (got {fit.discount_factor:.6f}, want {true_disc})", abs(fit.discount_factor - true_disc) < 1e-6)
check("r_squared ~ 1.0", fit.r_squared > 0.999999)

print("\n=== 7. Surface coordinates ===")
df = pd.DataFrame({"strike": [90, 100, 110], "T": [0.5, 0.5, 0.5], "iv": [0.25, 0.20, 0.22], "forward": [100, 100, 100]})
out = add_surface_coordinates(df)
check("log-moneyness at ATM is 0", np.isclose(out.loc[out["strike"] == 100, "log_moneyness"].iloc[0], 0.0))
check("log-moneyness at K=90", np.isclose(out.loc[out["strike"] == 90, "log_moneyness"].iloc[0], np.log(0.9)))
check("total variance = iv^2 * T", np.isclose(out["total_variance"].iloc[1], 0.20**2 * 0.5))

print("\n=== 8. Calendar arbitrage detection ===")
df = pd.DataFrame({"strike": [100, 100], "forward": [100, 100], "T": [0.1, 0.5], "iv": [0.30, 0.10]})
df = add_surface_coordinates(df)
violations = check_calendar_arbitrage(df)
check("detects decreasing total variance", len(violations) == 1)

df = pd.DataFrame({"strike": [100, 100, 100], "forward": [100, 100, 100], "T": [0.1, 0.3, 0.5], "iv": [0.20, 0.20, 0.20]})
df = add_surface_coordinates(df)
violations = check_calendar_arbitrage(df)
check("clean surface has no violations", len(violations) == 0)

print("\n=== 9. Butterfly arbitrage detection ===")
df = pd.DataFrame({"expiry": ["2099-01-01"] * 3, "strike": [95, 100, 105], "call_mid": [10.0, 6.0, 1.0]})
violations = check_butterfly_arbitrage(df)
check("detects non-convex calls", len(violations) == 1)

df = pd.DataFrame({"expiry": ["2099-01-01"] * 3, "strike": [95, 100, 105], "call_mid": [10.0, 6.5, 4.0]})
violations = check_butterfly_arbitrage(df)
check("convex calls pass", len(violations) == 0)

print(f"\n{'='*50}\n{PASS} passed, {FAIL} failed\n{'='*50}")
sys.exit(1 if FAIL else 0)
