"""
Implied volatility solvers.

Design choice (per project recommendation #3): Brent's method is the
default, not Newton-Raphson. NR divides by vega at every step, and vega
collapses to ~0 for deep ITM/OTM strikes and very short-dated options --
exactly the noisiest, least liquid corner of a real option chain. NR
will happily diverge or return a negative/absurd vol there with no
warning. Brent's method instead brackets the root on a fixed interval
and *cannot* leave it, so worst case it's slow, never wrong.

We still offer an NR fast-path (a handful of iterations) because on
well-behaved, liquid, near-the-money strikes it converges in 3-4 steps
and is meaningfully faster when solving thousands of strikes for a full
surface. If NR fails to converge in max_nr_iter steps, or lands outside
the valid vol bracket, we silently fall back to Brent -- the caller
never sees the difference except in speed.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import brentq

from .black_scholes import black76_price

VOL_LOWER = 1e-6
VOL_UPPER = 5.0


@dataclass
class IVResult:
    iv: float | None
    converged: bool
    method: str  # "newton", "brent", or "failed"
    iterations: int


def _vega_black76(F, K, T, sigma):
    """Black-76 vega, used only internally to drive the Newton-Raphson fast path."""
    from scipy.stats import norm
    T = max(T, 1e-12)
    sigma = max(sigma, 1e-12)
    d1 = (np.log(F / K) + 0.5 * sigma**2 * T) / (sigma * np.sqrt(T))
    return F * norm.pdf(d1) * np.sqrt(T)


def _newton_step(F, K, T, disc, target_price, option_type, sigma0, max_iter, tol):
    sigma = sigma0
    for i in range(max_iter):
        price = black76_price(F, K, T, r=0.0, sigma=sigma, option_type=option_type, disc=disc)
        vega = disc * _vega_black76(F, K, T, sigma)
        diff = price - target_price

        if abs(diff) < tol:
            return sigma, True, i + 1

        if vega < 1e-8:  # vega collapsed -- NR is not safe to continue
            return sigma, False, i + 1

        step = diff / vega
        sigma_new = sigma - step

        if not np.isfinite(sigma_new) or sigma_new <= VOL_LOWER or sigma_new >= VOL_UPPER:
            return sigma, False, i + 1

        sigma = sigma_new

    return sigma, False, max_iter


def implied_vol_black76(
    target_price: float,
    F: float,
    K: float,
    T: float,
    disc: float = 1.0,
    option_type: str = "call",
    sigma0: float = 0.3,
    use_newton_fastpath: bool = True,
    max_newton_iter: int = 6,
    newton_tol: float = 1e-8,
    brent_tol: float = 1e-10,
) -> IVResult:
    """
    Solve for sigma such that black76_price(F, K, T, sigma, disc=disc) ==
    target_price. target_price should be the *undiscounted-consistent*
    market mid (i.e. the actual traded option mid price, not a forward
    price -- disc is applied inside black76_price).

    Returns IVResult(iv=None, converged=False, method="failed", ...) if the
    market price itself is outside arbitrage bounds (worse than intrinsic,
    or above the discounted forward), since no volatility can rationalize
    it and returning a nonsense number is worse than returning None.
    """
    # No-arbitrage sanity check on the *undiscounted* forward-space price.
    if option_type == "call":
        intrinsic = max(F - K, 0.0) * disc
        upper_bound = F * disc
    else:
        intrinsic = max(K - F, 0.0) * disc
        upper_bound = K * disc

    if target_price < intrinsic - 1e-8 or target_price > upper_bound + 1e-8:
        return IVResult(iv=None, converged=False, method="failed", iterations=0)

    if use_newton_fastpath:
        sigma, converged, n_iter = _newton_step(
            F, K, T, disc, target_price, option_type, sigma0, max_newton_iter, newton_tol
        )
        if converged:
            return IVResult(iv=float(sigma), converged=True, method="newton", iterations=n_iter)

    # Brent fallback: bracket-guaranteed root find.
    def f(sigma):
        return black76_price(F, K, T, r=0.0, sigma=sigma, option_type=option_type, disc=disc) - target_price

    f_lo, f_hi = f(VOL_LOWER), f(VOL_UPPER)
    if np.sign(f_lo) == np.sign(f_hi):
        # Price sits outside what's reachable within [VOL_LOWER, VOL_UPPER] --
        # should be rare given the arbitrage check above, but can still
        # happen right at the boundary from floating point.
        return IVResult(iv=None, converged=False, method="failed", iterations=0)

    try:
        result = brentq(f, VOL_LOWER, VOL_UPPER, xtol=brent_tol, full_output=True)
        sigma_root, r = result
        return IVResult(
            iv=float(sigma_root),
            converged=bool(r.converged),
            method="brent",
            iterations=int(r.iterations),
        )
    except Exception:
        return IVResult(iv=None, converged=False, method="failed", iterations=0)


def solve_iv_surface(df, F_col="forward", disc_col="discount_factor"):
    """
    Vectorized-by-row convenience: given a DataFrame with columns
    ['strike', 'T', 'mid', 'option_type', F_col, disc_col], solve IV for
    every row and return the same frame with 'iv', 'iv_converged',
    'iv_method' columns appended.

    Deliberately a plain Python loop, not a numpy vectorization: each row
    is an independent 1D root-find with its own bracket-or-fallback logic,
    and a chain is at most a few thousand rows, so the loop costs
    milliseconds -- not worth the loss of clarity.
    """
    ivs, converged, methods = [], [], []
    for _, row in df.iterrows():
        res = implied_vol_black76(
            target_price=row["mid"],
            F=row[F_col],
            K=row["strike"],
            T=row["T"],
            disc=row[disc_col],
            option_type=row["option_type"],
        )
        ivs.append(res.iv)
        converged.append(res.converged)
        methods.append(res.method)

    out = df.copy()
    out["iv"] = ivs
    out["iv_converged"] = converged
    out["iv_method"] = methods
    return out
