"""
Streamlit dashboard: Options Volatility Surface & Greeks Visualizer.

Two tabs:
  1. Vol Surface  -- pulls a live option chain (yfinance), cleans it,
     fits forward/discount per expiry via put-call parity, solves IV,
     plots the 3D surface in (log-moneyness, T, total variance) space,
     and flags calendar/butterfly arbitrage violations.
  2. Greeks Explorer -- pure sliders (S, K, T, r, sigma) over the
     from-scratch BSM engine, showing all first- and second-order
     Greeks and how they move. No network call needed for this tab, so
     it always works even if data fetching is unavailable.

Run with:  streamlit run app/dashboard.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running via `streamlit run app/dashboard.py` from the repo root
# without installing the package first.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from vol_surface.data.fetch import ChainCleaningConfig
from vol_surface.pipeline import run_pipeline
from vol_surface.pricing.black_scholes import bsm_price, bsm_greeks

st.set_page_config(page_title="Vol Surface & Greeks Visualizer", layout="wide")


# --------------------------------------------------------------------------
# Cached data pipeline -- st.cache_data discipline per recommendation.
# TTL is short (5 min) since option quotes move; ticker+max_expiries+cleaning
# params are the cache key so changing any of them re-fetches.
# --------------------------------------------------------------------------

@st.cache_data(ttl=300, show_spinner="Fetching and processing option chain...")
def cached_pipeline(ticker: str, max_expiries: int, max_spread_frac: float, require_vol_oi: bool):
    config = ChainCleaningConfig(max_spread_frac=max_spread_frac, require_volume_or_oi=require_vol_oi)
    return run_pipeline(ticker, max_expiries=max_expiries, cleaning_config=config)


def render_surface_tab():
    st.header("Implied Volatility Surface")
    st.caption(
        "Forward and discount factor are implied per-expiry from put-call parity "
        "(no dividend-yield or risk-free-rate guess). IV is solved via Newton-Raphson "
        "with a Brent's-method fallback for non-convergent cases."
    )

    col_a, col_b, col_c, col_d = st.columns(4)
    with col_a:
        ticker = st.text_input("Ticker", value="SPY")
    with col_b:
        max_expiries = st.slider("Max expiries to fetch", 1, 20, 8)
    with col_c:
        max_spread_frac = st.slider("Max bid-ask spread (% of mid)", 5, 100, 40) / 100.0
    with col_d:
        require_vol_oi = st.checkbox("Require volume or open interest > 0", value=True)

    if st.button("Fetch & Build Surface", type="primary"):
        st.session_state["run_requested"] = True

    if not st.session_state.get("run_requested"):
        st.info("Set your parameters and click **Fetch & Build Surface**. Note: SPY/SPX are American/European-settlement-flavored index-linked products; SPY itself is American-style but highly liquid and dividend-adjusted forwards from parity absorb most of that effect for near-the-money strikes.")
        return

    try:
        result = cached_pipeline(ticker, max_expiries, max_spread_frac, require_vol_oi)
    except Exception as e:
        st.error(f"Pipeline failed: {e}")
        return

    report = result["cleaning_report"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Raw quotes", report.get("rows_in", 0))
    c2.metric("After cleaning", report.get("rows_out", 0))
    c3.metric("Dropped", report.get("rows_dropped", 0))
    solved = result["solved_options"]
    conv_rate = solved["iv_converged"].mean() * 100 if len(solved) else 0.0
    c4.metric("IV solve convergence", f"{conv_rate:.1f}%")

    with st.expander("Cleaning filter breakdown"):
        st.json(report.get("filters", {}))

    with st.expander("Forward / discount factor fit per expiry"):
        st.dataframe(result["forward_fits"])

    surface = result["surface"]
    if surface.empty:
        st.warning("No valid IV points survived cleaning + solving. Try loosening filters.")
        return

    # --- 3D surface plot: log-moneyness x T x total variance ---
    st.subheader("3D Surface: log-moneyness × T × total implied variance")
    fig = go.Figure(
        data=[
            go.Scatter3d(
                x=surface["log_moneyness"],
                y=surface["T"],
                z=surface["total_variance"],
                mode="markers",
                marker=dict(
                    size=3,
                    color=surface["iv"],
                    colorscale="Viridis",
                    colorbar=dict(title="IV"),
                ),
                text=[
                    f"K={row.strike:.1f}<br>T={row.T:.3f}<br>IV={row.iv:.3f}"
                    for row in surface.itertuples()
                ],
                hoverinfo="text",
            )
        ]
    )
    fig.update_layout(
        scene=dict(
            xaxis_title="log-moneyness ln(K/F)",
            yaxis_title="T (years)",
            zaxis_title="total variance (σ²T)",
        ),
        height=650,
        margin=dict(l=0, r=0, t=20, b=0),
    )
    st.plotly_chart(fig, use_container_width=True)

    # --- Arbitrage flags ---
    st.subheader("Arbitrage checks")
    cal_v = result["calendar_violations"]
    fly_v = result["butterfly_violations"]
    col1, col2 = st.columns(2)
    with col1:
        if cal_v.empty:
            st.success("No calendar arbitrage violations detected.")
        else:
            st.error(f"{len(cal_v)} calendar arbitrage violation(s) detected (total variance decreasing in T).")
            st.dataframe(cal_v)
    with col2:
        if fly_v.empty:
            st.success("No butterfly arbitrage violations detected.")
        else:
            st.error(f"{len(fly_v)} butterfly arbitrage violation(s) detected (non-convex call prices).")
            st.dataframe(fly_v)

    with st.expander("Raw solved IV table"):
        st.dataframe(surface)


def render_greeks_tab():
    st.header("Live Greeks Explorer")
    st.caption("Pure from-scratch BSM engine -- no data fetch needed. Drag the sliders.")

    col1, col2 = st.columns(2)
    with col1:
        S = st.slider("Spot price (S)", 10.0, 1000.0, 100.0)
        K = st.slider("Strike (K)", 10.0, 1000.0, 100.0)
        T = st.slider("Time to expiry, years (T)", 0.01, 3.0, 0.5)
    with col2:
        r = st.slider("Risk-free rate (r)", -0.02, 0.10, 0.04)
        q = st.slider("Dividend yield (q)", 0.0, 0.10, 0.015)
        sigma = st.slider("Volatility (σ)", 0.01, 2.0, 0.20)

    option_type = st.radio("Option type", ["call", "put"], horizontal=True)

    price = bsm_price(S, K, T, r, q, sigma, option_type)
    greeks = bsm_greeks(S, K, T, r, q, sigma, option_type)

    st.metric("Price", f"{price:.4f}")

    g1, g2, g3, g4 = st.columns(4)
    g1.metric("Delta", f"{greeks.delta:.4f}")
    g1.metric("Vanna", f"{greeks.vanna:.4f}")
    g2.metric("Gamma", f"{greeks.gamma:.5f}")
    g2.metric("Volga", f"{greeks.volga:.4f}")
    g3.metric("Vega", f"{greeks.vega:.4f}")
    g3.metric("Charm", f"{greeks.charm:.5f}")
    g4.metric("Theta (per yr)", f"{greeks.theta:.4f}")
    g4.metric("Rho", f"{greeks.rho:.4f}")

    # Gamma & Vega vs spot, at fixed K/T/r/q/sigma -- classic teaching plot.
    st.subheader("Gamma & Vega vs. Spot Price")
    S_grid = np.linspace(max(S * 0.5, 1), S * 1.5, 200)
    gammas = [bsm_greeks(s, K, T, r, q, sigma, option_type).gamma for s in S_grid]
    vegas = [bsm_greeks(s, K, T, r, q, sigma, option_type).vega for s in S_grid]

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=S_grid, y=gammas, name="Gamma", yaxis="y1"))
    fig.add_trace(go.Scatter(x=S_grid, y=vegas, name="Vega", yaxis="y2"))
    fig.add_vline(x=S, line_dash="dot", annotation_text="current S")
    fig.update_layout(
        xaxis_title="Spot price",
        yaxis=dict(title="Gamma"),
        yaxis2=dict(title="Vega", overlaying="y", side="right"),
        height=400,
        legend=dict(orientation="h"),
    )
    st.plotly_chart(fig, use_container_width=True)


def main():
    st.title("Options Volatility Surface & Greeks Visualizer")
    tab1, tab2 = st.tabs(["Vol Surface (live data)", "Greeks Explorer (no data needed)"])
    with tab1:
        render_surface_tab()
    with tab2:
        render_greeks_tab()


if __name__ == "__main__":
    main()
