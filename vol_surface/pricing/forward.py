"""
Implied forward and discount factor from put-call parity.

Put-call parity for European options states:

    C(K) - P(K) = disc * (F - K)

which is linear in K with slope -disc and intercept disc*F. So for a
fixed expiry, given several strikes with both a call and a put quote,
regressing (C(K) - P(K)) against K by ordinary least squares recovers
both disc (the discount factor to that expiry) and F (the forward
price) directly from the market -- no dividend-yield guess, no
risk-free-rate guess.

This is the single highest-value change recommended for this project:
it means call-IVs and put-IVs solved against the same (F, disc) will
agree with each other, because F was extracted to make them agree by
construction (at least in the region where parity approximately holds
for the quotes used).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class ForwardFit:
    expiry: str
    T: float
    forward: float
    discount_factor: float
    implied_rate: float  # -ln(disc)/T, for reference / comparison to a rate curve
    n_points: int
    r_squared: float


def imply_forward_and_discount(
    strikes: np.ndarray,
    call_mid: np.ndarray,
    put_mid: np.ndarray,
    T: float,
    expiry_label: str = "",
    min_points: int = 3,
) -> ForwardFit:
    """
    OLS fit of C(K) - P(K) = a + b*K, where a = disc*F and b = -disc.

    strikes, call_mid, put_mid must be aligned (same K, no NaNs) and
    should already be filtered to reasonably liquid quotes -- garbage in
    here silently produces a garbage forward that corrupts every IV
    solved against it, since every option relies on the same fit.
    """
    strikes = np.asarray(strikes, dtype=float)
    call_mid = np.asarray(call_mid, dtype=float)
    put_mid = np.asarray(put_mid, dtype=float)

    mask = np.isfinite(strikes) & np.isfinite(call_mid) & np.isfinite(put_mid)
    strikes, call_mid, put_mid = strikes[mask], call_mid[mask], put_mid[mask]

    if len(strikes) < min_points:
        raise ValueError(
            f"Need at least {min_points} clean (K, call, put) triples to fit "
            f"forward/discount for expiry {expiry_label!r}, got {len(strikes)}."
        )

    y = call_mid - put_mid
    X = np.vstack([np.ones_like(strikes), strikes]).T  # columns: [1, K]

    # OLS via lstsq rather than a normal-equations inverse: more numerically
    # stable when strikes are large numbers and closely spaced.
    coeffs, residuals, rank, _ = np.linalg.lstsq(X, y, rcond=None)
    a, b = coeffs  # y = a + b*K
    disc = -b
    if disc <= 0:
        raise ValueError(
            f"Fitted discount factor is non-positive ({disc:.6f}) for expiry "
            f"{expiry_label!r}. This means the put-call parity regression is "
            f"degenerate -- check for bad quotes (crossed markets, stale "
            f"prices) in the input strikes."
        )
    forward = a / disc

    y_hat = X @ coeffs
    ss_res = float(np.sum((y - y_hat) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0 else 1.0

    implied_rate = -np.log(disc) / T if T > 0 else 0.0

    return ForwardFit(
        expiry=expiry_label,
        T=T,
        forward=float(forward),
        discount_factor=float(disc),
        implied_rate=float(implied_rate),
        n_points=int(len(strikes)),
        r_squared=float(r_squared),
    )


def fit_forward_by_expiry(chain: pd.DataFrame, min_points: int = 3) -> pd.DataFrame:
    """
    Convenience wrapper: given a cleaned option chain DataFrame with columns
    ['expiry', 'T', 'strike', 'call_mid', 'put_mid'] (one row per strike,
    both call and put mids already merged onto it), fit forward/discount
    per expiry and return a small DataFrame indexed by expiry.

    Rows with a NaN in call_mid or put_mid are dropped per-expiry before
    fitting (a strike often has a live call quote but a dead put quote, or
    vice versa -- that's fine as long as enough clean pairs remain).
    """
    rows = []
    for expiry, g in chain.groupby("expiry"):
        g = g.dropna(subset=["call_mid", "put_mid"])
        if len(g) < min_points:
            continue
        T = float(g["T"].iloc[0])
        fit = imply_forward_and_discount(
            g["strike"].values, g["call_mid"].values, g["put_mid"].values, T, expiry_label=str(expiry),
            min_points=min_points,
        )
        rows.append(fit.__dict__)

    if not rows:
        raise ValueError(
            "Could not fit forward/discount for any expiry -- not enough "
            "expiries had >= min_points clean call+put pairs. Loosen the "
            "cleaning filters or check the data source."
        )
    return pd.DataFrame(rows).set_index("expiry")
