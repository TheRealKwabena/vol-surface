"""
Option chain fetching via yfinance, with cleaning as a first-class step.

Assumption made explicit here (flagged as an open decision in the original
project discussion, defaulted per project instructions): yfinance is used
because it's free and gets the whole pipeline working end-to-end with zero
signup friction. It is an unofficial wrapper around Yahoo Finance's web
endpoints -- it can break without warning, and quotes can be stale
(particularly bid/ask on illiquid strikes, which may not have updated in
hours). This module isolates all of that risk behind one interface
(fetch_chain) so that swapping in a paid feed (Polygon, Tradier, Databento,
CBOE DataShop) later means writing one new function with the same output
schema, not touching the pricing/surface code at all.

Per project recommendation #2, cleaning happens here, before anything
reaches the solver, and is treated as a first-class pipeline stage rather
than an afterthought:
  - use mid = (bid+ask)/2, never last traded price (last can be stale by
    hours and produces spikes that ruin a surface)
  - drop quotes with bid <= 0 (no live bid = no real market)
  - drop quotes where the bid-ask spread as a fraction of mid exceeds a
    threshold (default 40%) -- these are not tradeable prices
  - drop quotes with zero volume AND zero open interest (nobody's home)
  - drop quotes that violate no-arbitrage bounds against the estimated
    forward (deferred to the surface-construction stage, since it needs F)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np
import pandas as pd

try:
    import yfinance as yf
except ImportError:  # pragma: no cover
    yf = None


@dataclass
class ChainCleaningConfig:
    max_spread_frac: float = 0.40   # drop if (ask-bid)/mid > this
    require_volume_or_oi: bool = True
    min_mid: float = 0.01           # drop sub-penny quotes (numerical noise, not real prices)


def _require_yfinance():
    if yf is None:
        raise ImportError(
            "yfinance is not installed. Run `pip install yfinance` "
            "(it's in requirements.txt) to use live data fetching."
        )


def fetch_raw_chain(ticker: str, max_expiries: int | None = None) -> pd.DataFrame:
    """
    Pull all available expiries' option chains for `ticker` from yfinance
    and stack them into one long DataFrame with a uniform schema:

    columns: expiry (str, 'YYYY-MM-DD'), T (float, years, ACT/365 from now),
             strike, option_type ('call'/'put'), bid, ask, last, volume,
             open_interest, implied_vol_yf (yfinance's own IV, kept only
             for comparison -- we solve our own), underlying_price

    This is intentionally "raw": no filtering happens here, so you can
    always inspect exactly what the vendor returned before any cleaning
    decision is applied.
    """
    _require_yfinance()

    tk = yf.Ticker(ticker)
    spot = tk.fast_info.get("lastPrice") if hasattr(tk, "fast_info") else None
    if spot is None:
        hist = tk.history(period="1d")
        spot = float(hist["Close"].iloc[-1]) if not hist.empty else np.nan

    expiries = tk.options
    if max_expiries is not None:
        expiries = expiries[:max_expiries]

    now = datetime.now(timezone.utc)
    frames = []
    for expiry in expiries:
        try:
            chain = tk.option_chain(expiry)
        except Exception:
            continue  # yfinance occasionally 404s a single expiry transiently; skip and move on

        expiry_dt = datetime.strptime(expiry, "%Y-%m-%d").replace(
            hour=21, minute=0, second=0, tzinfo=timezone.utc  # approx 4pm ET close
        )
        T = max((expiry_dt - now).total_seconds() / (365.0 * 24 * 3600), 0.0)

        for opt_type, df in (("call", chain.calls), ("put", chain.puts)):
            if df.empty:
                continue
            d = df.copy()
            d["expiry"] = expiry
            d["T"] = T
            d["option_type"] = opt_type
            d["underlying_price"] = spot
            d = d.rename(columns={"impliedVolatility": "implied_vol_yf", "openInterest": "open_interest"})
            frames.append(
                d[
                    [
                        "expiry", "T", "strike", "option_type", "bid", "ask", "lastPrice",
                        "volume", "open_interest", "implied_vol_yf", "underlying_price",
                    ]
                ].rename(columns={"lastPrice": "last"})
            )

    if not frames:
        raise ValueError(
            f"No option chain data returned for {ticker!r}. Check the ticker "
            f"symbol, or yfinance may be rate-limiting / temporarily down."
        )

    return pd.concat(frames, ignore_index=True)


def clean_chain(raw: pd.DataFrame, config: ChainCleaningConfig | None = None) -> pd.DataFrame:
    """
    Apply the cleaning rules described in the module docstring. Returns a
    new DataFrame with a 'mid' column added and rows failing any filter
    dropped. Adds a boolean breakdown as attrs for transparency (how many
    rows each filter removed), useful for a "data quality" panel in the
    dashboard.
    """
    config = config or ChainCleaningConfig()
    df = raw.copy()
    n0 = len(df)

    df["mid"] = (df["bid"] + df["ask"]) / 2.0

    filters = {}

    keep = df["bid"] > 0
    filters["bid_positive"] = int((~keep).sum())
    df = df[keep]

    keep = df["mid"] >= config.min_mid
    filters["min_mid"] = int((~keep).sum())
    df = df[keep]

    spread_frac = (df["ask"] - df["bid"]) / df["mid"]
    keep = spread_frac <= config.max_spread_frac
    filters["spread_too_wide"] = int((~keep).sum())
    df = df[keep]

    if config.require_volume_or_oi:
        keep = (df["volume"].fillna(0) > 0) | (df["open_interest"].fillna(0) > 0)
        filters["no_volume_or_oi"] = int((~keep).sum())
        df = df[keep]

    df = df.reset_index(drop=True)
    df.attrs["cleaning_report"] = {
        "rows_in": n0,
        "rows_out": len(df),
        "rows_dropped": n0 - len(df),
        "filters": filters,
    }
    return df


def merge_calls_puts(clean: pd.DataFrame) -> pd.DataFrame:
    """
    Reshape the long (one row per option) cleaned chain into one row per
    (expiry, strike) with call_mid and put_mid side by side -- the shape
    the put-call parity forward fit needs. A strike with only a call (or
    only a put) surviving cleaning becomes a row with a NaN in the other
    column; fit_forward_by_expiry drops those before fitting.
    """
    calls = clean[clean["option_type"] == "call"][["expiry", "T", "strike", "mid"]].rename(
        columns={"mid": "call_mid"}
    )
    puts = clean[clean["option_type"] == "put"][["expiry", "T", "strike", "mid"]].rename(
        columns={"mid": "put_mid"}
    )
    merged = pd.merge(calls, puts, on=["expiry", "T", "strike"], how="outer")
    return merged.sort_values(["expiry", "strike"]).reset_index(drop=True)


def fetch_chain(ticker: str, max_expiries: int | None = None, config: ChainCleaningConfig | None = None):
    """
    End-to-end convenience: fetch, clean, and return both the cleaned
    long-form chain (for IV solving) and the merged call/put wide-form
    (for forward fitting).

    Returns (clean_long_df, merged_wide_df, cleaning_report).
    """
    raw = fetch_raw_chain(ticker, max_expiries=max_expiries)
    clean = clean_chain(raw, config)
    merged = merge_calls_puts(clean)
    return clean, merged, clean.attrs.get("cleaning_report", {})
