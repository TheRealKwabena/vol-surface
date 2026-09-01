"""
Vol surface construction: log-moneyness/total-variance coordinates, and
calendar + butterfly arbitrage checks.

Per recommendation #4: raw (strike, calendar days) axes make surfaces
incomparable across underlyings and across days for the same underlying
(a $5 strike step means something totally different for a $50 stock than
a $5000 index). Two changes fix this:

  1. Use log-moneyness  k = ln(K / F)  instead of raw strike. k=0 is
     always at-the-money-forward regardless of price level.
  2. Use total implied variance  w = sigma^2 * T  instead of sigma
     itself. w is the natural interpolation coordinate because the
     no-calendar-arbitrage condition is simply "w must be non-decreasing
     in T at fixed k" -- a condition that's awkward to state in sigma
     directly (since sigma itself can legitimately decrease with T while
     w still increases).

Per recommendation #5, two arbitrage checks are computed and surfaced
rather than silently ignored:

  Calendar arbitrage: for fixed log-moneyness k, total variance w(k, T)
  must be non-decreasing in T. A violation means the market is (at those
  two points) pricing a calendar spread at a negative value, which is a
  static arbitrage.

  Butterfly arbitrage: the call price must be a convex function of
  strike at fixed T. We check this directly on the (cleaned) mid prices
  rather than on the fitted IVs, since that's the more primitive
  no-arbitrage condition -- convexity in IV-space does not map cleanly
  to convexity in price-space and checking on price avoids that
  confusion entirely.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def add_surface_coordinates(iv_df: pd.DataFrame, forward_col: str = "forward") -> pd.DataFrame:
    """
    Given a DataFrame with columns ['strike', 'T', 'iv', forward_col],
    add 'log_moneyness' = ln(K/F) and 'total_variance' = iv^2 * T.
    """
    out = iv_df.copy()
    out["log_moneyness"] = np.log(out["strike"] / out[forward_col])
    out["total_variance"] = out["iv"] ** 2 * out["T"]
    return out


def check_calendar_arbitrage(surface_df: pd.DataFrame, k_bucket_width: float = 0.02) -> pd.DataFrame:
    """
    For each log-moneyness bucket, check that total variance is
    non-decreasing across increasing T. Returns a DataFrame of violations:
    columns ['log_moneyness_bucket', 'T_earlier', 'T_later',
    'w_earlier', 'w_later', 'violation_amount'].

    Strikes are bucketed by log-moneyness (rounded to k_bucket_width)
    because two different expiries essentially never share an exact
    strike/moneyness point -- comparing "nearby" points is the practical
    version of this check.
    """
    df = surface_df.dropna(subset=["log_moneyness", "total_variance", "T"]).copy()
    df["k_bucket"] = (df["log_moneyness"] / k_bucket_width).round() * k_bucket_width

    violations = []
    for k_bucket, g in df.groupby("k_bucket"):
        g = g.sort_values("T")
        Ts = g["T"].values
        ws = g["total_variance"].values
        for i in range(1, len(Ts)):
            if Ts[i] <= Ts[i - 1]:
                continue
            if ws[i] < ws[i - 1] - 1e-10:
                violations.append(
                    {
                        "log_moneyness_bucket": float(k_bucket),
                        "T_earlier": float(Ts[i - 1]),
                        "T_later": float(Ts[i]),
                        "w_earlier": float(ws[i - 1]),
                        "w_later": float(ws[i]),
                        "violation_amount": float(ws[i - 1] - ws[i]),
                    }
                )
    return pd.DataFrame(violations)


def check_butterfly_arbitrage(merged_chain: pd.DataFrame) -> pd.DataFrame:
    """
    For each expiry, check that call_mid is convex in strike:
    C(K_{i-1}) - 2*C(K_i) + C(K_{i+1}) >= 0 for consecutive strikes
    (unevenly spaced strikes are handled with the standard divided-
    difference form of discrete convexity). A negative value means a
    butterfly spread centered at K_i would be priced negative -- a
    static arbitrage (assuming the quotes were simultaneously
    tradeable, which is the usual caveat for any arbitrage check done
    on non-simultaneous or wide-spread quotes).

    Returns a DataFrame of violations: ['expiry', 'strike', 'convexity_value'].
    """
    violations = []
    for expiry, g in merged_chain.dropna(subset=["call_mid"]).groupby("expiry"):
        g = g.sort_values("strike")
        K = g["strike"].values
        C = g["call_mid"].values
        for i in range(1, len(K) - 1):
            k0, k1, k2 = K[i - 1], K[i], K[i + 1]
            c0, c1, c2 = C[i - 1], C[i], C[i + 1]
            # Discrete second derivative for unevenly spaced points (divided differences).
            left_slope = (c1 - c0) / (k1 - k0)
            right_slope = (c2 - c1) / (k2 - k1)
            convexity = right_slope - left_slope
            if convexity < -1e-6:
                violations.append(
                    {
                        "expiry": expiry,
                        "strike": float(k1),
                        "convexity_value": float(convexity),
                    }
                )
    return pd.DataFrame(violations)


def build_surface(iv_df: pd.DataFrame, merged_chain: pd.DataFrame, forward_col: str = "forward") -> dict:
    """
    Top-level entry point: adds surface coordinates and runs both
    arbitrage checks. Returns a dict with keys 'surface' (the annotated
    DataFrame), 'calendar_violations', 'butterfly_violations'.
    """
    surface = add_surface_coordinates(iv_df, forward_col=forward_col)
    calendar_violations = check_calendar_arbitrage(surface)
    butterfly_violations = check_butterfly_arbitrage(merged_chain)
    return {
        "surface": surface,
        "calendar_violations": calendar_violations,
        "butterfly_violations": butterfly_violations,
    }
