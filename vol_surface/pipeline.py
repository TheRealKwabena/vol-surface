"""
End-to-end pipeline: ticker -> cleaned chain -> per-expiry forward/discount
-> solved IV surface -> arbitrage-checked surface.

This is the module the Streamlit app calls; it's kept separate from the
app so the whole pipeline can be exercised from a plain script or a test
without touching Streamlit at all.
"""

from __future__ import annotations

import pandas as pd

from .data.fetch import ChainCleaningConfig, fetch_chain
from .pricing.forward import fit_forward_by_expiry
from .pricing.implied_vol import solve_iv_surface
from .surface.build import build_surface


def run_pipeline(ticker: str, max_expiries: int | None = None, cleaning_config: ChainCleaningConfig | None = None) -> dict:
    clean_long, merged_wide, cleaning_report = fetch_chain(ticker, max_expiries=max_expiries, config=cleaning_config)

    forward_fits = fit_forward_by_expiry(merged_wide)

    # Attach forward + discount factor onto every row of the long (per-option) chain.
    iv_input = clean_long.merge(
        forward_fits[["forward", "discount_factor"]], left_on="expiry", right_index=True, how="inner",
    )

    solved = solve_iv_surface(iv_input)

    valid = solved[solved["iv"].notna() & solved["iv_converged"]].copy()

    surface_result = build_surface(valid, merged_wide, forward_col="forward")

    return {
        "ticker": ticker,
        "cleaning_report": cleaning_report,
        "forward_fits": forward_fits,
        "solved_options": solved,
        "valid_options": valid,
        "surface": surface_result["surface"],
        "calendar_violations": surface_result["calendar_violations"],
        "butterfly_violations": surface_result["butterfly_violations"],
        "merged_wide": merged_wide,
    }
