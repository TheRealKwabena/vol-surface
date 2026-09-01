"""
Black-Scholes-Merton (spot form) and Black-76 (forward form) closed-form
pricing and Greeks, implemented from scratch.

Why two forms live here rather than one:

Spot-form BSM takes (S, K, T, r, q, sigma) and requires you to know the
continuous dividend yield q. For single names, q is often guessed or
backed out crudely from analyst estimates, and that guess pollutes every
downstream Greek.

Black-76 sidesteps this entirely by taking the forward price F directly:

    F = S * exp((r - q) * T)

If instead of *assuming* q you *infer* F from the options market itself
(see vol_surface.pricing.forward.imply_forward_and_discount), you get a
forward that is consistent with what the market is actually pricing,
with zero guesswork. Black-76 is therefore the form we build the surface
on; the spot-form functions are kept because they're the more familiar
entry point, useful for tests, and for the "manual Greeks explorer" panel
in the dashboard where a user drags S/K/T/r/sigma sliders directly.

All formulas below are derived from the standard risk-neutral pricing
argument, not imported from a finance library -- only scipy.stats.norm's
cdf/pdf (the standard normal distribution function itself) is used as a
primitive.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.stats import norm

_EPS = 1e-12


def _safe_T(T: float | np.ndarray) -> float | np.ndarray:
    """Guard against T=0 (expiry instant) blowing up d1/d2 with a divide by zero."""
    return np.maximum(T, _EPS)


def _safe_sigma(sigma: float | np.ndarray) -> float | np.ndarray:
    return np.maximum(sigma, _EPS)


# --------------------------------------------------------------------------
# Spot-form Black-Scholes-Merton
# --------------------------------------------------------------------------


def d1_d2_spot(S, K, T, r, q, sigma):
    """Standard d1, d2 for spot-form BSM with continuous dividend yield q."""
    T = _safe_T(T)
    sigma = _safe_sigma(sigma)
    d1 = (np.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    return d1, d2


def bsm_price(S, K, T, r, q, sigma, option_type: str = "call"):
    """
    Spot-form Black-Scholes-Merton price.

    S     : spot price
    K     : strike
    T     : time to expiry in years
    r     : continuously-compounded risk-free rate
    q     : continuously-compounded dividend yield
    sigma : volatility (annualized)
    """
    d1, d2 = d1_d2_spot(S, K, T, r, q, sigma)
    disc_r = np.exp(-r * T)
    disc_q = np.exp(-q * T)

    if option_type == "call":
        return S * disc_q * norm.cdf(d1) - K * disc_r * norm.cdf(d2)
    elif option_type == "put":
        return K * disc_r * norm.cdf(-d2) - S * disc_q * norm.cdf(-d1)
    else:
        raise ValueError(f"option_type must be 'call' or 'put', got {option_type!r}")


# --------------------------------------------------------------------------
# Forward-form Black-76
# --------------------------------------------------------------------------


def d1_d2_forward(F, K, T, sigma):
    """
    Standard d1, d2 for Black-76, priced off the forward F directly.
    This is BSM with S -> F and r, q both dropped (they're baked into F
    and the discount factor is applied separately).
    """
    T = _safe_T(T)
    sigma = _safe_sigma(sigma)
    d1 = (np.log(F / K) + 0.5 * sigma**2 * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    return d1, d2


def black76_price(F, K, T, r, sigma, option_type: str = "call", disc: float | None = None):
    """
    Black-76 price of a European option on a forward F, discounted to
    present value.

    disc: discount factor exp(-r*T). If None, computed from r and T.
    Passing disc explicitly lets you use a discount factor implied
    directly from put-call parity instead of a risk-free-rate guess.
    """
    d1, d2 = d1_d2_forward(F, K, T, sigma)
    if disc is None:
        disc = np.exp(-r * T)

    if option_type == "call":
        return disc * (F * norm.cdf(d1) - K * norm.cdf(d2))
    elif option_type == "put":
        return disc * (K * norm.cdf(-d2) - F * norm.cdf(-d1))
    else:
        raise ValueError(f"option_type must be 'call' or 'put', got {option_type!r}")


# --------------------------------------------------------------------------
# Greeks (spot-form) -- first order
# --------------------------------------------------------------------------


@dataclass
class Greeks:
    delta: float
    gamma: float
    vega: float   # per 1.00 (100 vol points) change in sigma; divide by 100 for "per 1 vol point"
    theta: float  # per year; divide by 365 for "per calendar day"
    rho: float    # per 1.00 (100%) change in r; divide by 100 for "per 1% change"
    vanna: float  # d(delta)/d(sigma) == d(vega)/d(S)
    volga: float  # d(vega)/d(sigma), a.k.a. vomma
    charm: float  # d(delta)/d(t) -- delta decay


def bsm_greeks(S, K, T, r, q, sigma, option_type: str = "call") -> Greeks:
    """
    Closed-form Greeks for spot-form BSM, first and second order.

    Derivations (call; put analogs follow from put-call parity):
      delta = e^{-qT} N(d1)                         (put: -e^{-qT} N(-d1))
      gamma = e^{-qT} phi(d1) / (S sigma sqrt(T))    (same for call & put)
      vega  = S e^{-qT} phi(d1) sqrt(T)              (same for call & put)
      theta = -S e^{-qT} phi(d1) sigma / (2 sqrt(T))
              - r K e^{-rT} N(d2) + q S e^{-qT} N(d1)         (call)
      rho   = K T e^{-rT} N(d2)                      (put: -K T e^{-rT} N(-d2))
      vanna = -e^{-qT} phi(d1) d2 / sigma
      volga = vega * d1 * d2 / sigma
      charm = q e^{-qT} N(d1) - e^{-qT} phi(d1) * (2(r-q)T - d2 sigma sqrt(T)) / (2 T sigma sqrt(T))  (call)
    """
    T_safe = _safe_T(T)
    sigma_safe = _safe_sigma(sigma)
    d1, d2 = d1_d2_spot(S, K, T_safe, r, q, sigma_safe)
    disc_r = np.exp(-r * T_safe)
    disc_q = np.exp(-q * T_safe)
    pdf_d1 = norm.pdf(d1)
    sqrtT = np.sqrt(T_safe)

    gamma = disc_q * pdf_d1 / (S * sigma_safe * sqrtT)
    vega = S * disc_q * pdf_d1 * sqrtT
    vanna = -disc_q * pdf_d1 * d2 / sigma_safe
    volga = vega * d1 * d2 / sigma_safe

    if option_type == "call":
        delta = disc_q * norm.cdf(d1)
        theta = (
            -S * disc_q * pdf_d1 * sigma_safe / (2 * sqrtT)
            - r * K * disc_r * norm.cdf(d2)
            + q * S * disc_q * norm.cdf(d1)
        )
        rho = K * T_safe * disc_r * norm.cdf(d2)
        charm = q * disc_q * norm.cdf(d1) - disc_q * pdf_d1 * (
            2 * (r - q) * T_safe - d2 * sigma_safe * sqrtT
        ) / (2 * T_safe * sigma_safe * sqrtT)
    elif option_type == "put":
        delta = -disc_q * norm.cdf(-d1)
        theta = (
            -S * disc_q * pdf_d1 * sigma_safe / (2 * sqrtT)
            + r * K * disc_r * norm.cdf(-d2)
            - q * S * disc_q * norm.cdf(-d1)
        )
        rho = -K * T_safe * disc_r * norm.cdf(-d2)
        charm = -q * disc_q * norm.cdf(-d1) - disc_q * pdf_d1 * (
            2 * (r - q) * T_safe - d2 * sigma_safe * sqrtT
        ) / (2 * T_safe * sigma_safe * sqrtT)
    else:
        raise ValueError(f"option_type must be 'call' or 'put', got {option_type!r}")

    return Greeks(
        delta=float(delta),
        gamma=float(gamma),
        vega=float(vega),
        theta=float(theta),
        rho=float(rho),
        vanna=float(vanna),
        volga=float(volga),
        charm=float(charm),
    )


def finite_difference_greeks(S, K, T, r, q, sigma, option_type: str = "call", h: float = 1e-4) -> Greeks:
    """
    Independent finite-difference estimate of the same Greeks, used only
    to test bsm_greeks against (see tests/test_pricing.py). Central
    differences throughout.
    """
    def price(S_, K_, T_, r_, q_, sigma_):
        return bsm_price(S_, K_, T_, r_, q_, sigma_, option_type)

    hS = h * S
    hSig = h
    hT = h
    hR = h

    delta = (price(S + hS, K, T, r, q, sigma) - price(S - hS, K, T, r, q, sigma)) / (2 * hS)
    gamma = (
        price(S + hS, K, T, r, q, sigma)
        - 2 * price(S, K, T, r, q, sigma)
        + price(S - hS, K, T, r, q, sigma)
    ) / (hS**2)
    vega = (price(S, K, T, r, q, sigma + hSig) - price(S, K, T, r, q, sigma - hSig)) / (2 * hSig)
    # theta as -d(price)/dT (time decay, price loses value as T shrinks)
    theta = -(price(S, K, T + hT, r, q, sigma) - price(S, K, T - hT, r, q, sigma)) / (2 * hT)
    rho = (price(S, K, T, r + hR, q, sigma) - price(S, K, T, r - hR, q, sigma)) / (2 * hR)
    vanna = (
        price(S + hS, K, T, r, q, sigma + hSig)
        - price(S + hS, K, T, r, q, sigma - hSig)
        - price(S - hS, K, T, r, q, sigma + hSig)
        + price(S - hS, K, T, r, q, sigma - hSig)
    ) / (4 * hS * hSig)
    volga = (
        price(S, K, T, r, q, sigma + hSig) - 2 * price(S, K, T, r, q, sigma) + price(S, K, T, r, q, sigma - hSig)
    ) / (hSig**2)
    charm = (
        price(S + hS, K, T + hT, r, q, sigma)
        - price(S + hS, K, T - hT, r, q, sigma)
        - price(S - hS, K, T + hT, r, q, sigma)
        + price(S - hS, K, T - hT, r, q, sigma)
    ) / (4 * hS * hT)
    # charm defined as d(delta)/dt where t is calendar time = -d(delta)/dT
    charm = -charm

    return Greeks(
        delta=float(delta),
        gamma=float(gamma),
        vega=float(vega),
        theta=float(theta),
        rho=float(rho),
        vanna=float(vanna),
        volga=float(volga),
        charm=float(charm),
    )
