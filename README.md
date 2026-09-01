# Options Volatility Surface & Greeks Visualizer

An interactive dashboard that fetches live option chains, prices them with a
from-scratch Black-Scholes-Merton / Black-76 engine, solves for implied
volatility, and plots the resulting 3D volatility surface alongside a live
Greeks explorer.

This is Project 1 from the two-project quant finance build plan. Project 2
(the limit order book / market-making simulator) is a separate, unrelated
codebase and is not part of this repo.

## Quickstart

```bash
git clone https://github.com/TheRealKwabena/vol-surface.git
cd vol-surface

python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

pip install -r requirements.txt

streamlit run app/dashboard.py
```

Streamlit opens the dashboard at `http://localhost:8501`. Requires Python
3.9+. See "Running the dashboard" below for what each tab does, and
"Running the tests" to verify the pricing/surface logic.

## Assumptions made to start building

Two of the four scoping questions were answered explicitly; two were left to
a reasonable default so the build could start immediately. Revisit these at
any time — they're all one-line config changes, not architectural choices.

| Decision | Choice | Rationale |
|---|---|---|
| Instrument | **SPY** (index-linked ETF options) | You chose index options. SPY is used instead of SPX because yfinance serves SPY chains reliably; SPX chains are frequently incomplete or unavailable through yfinance. SPY is technically American-style, but is dividend-adjusted and, because the forward is *implied from the market* via put-call parity rather than assumed, the early-exercise premium on puts is small and mostly absorbed for near-the-money strikes and shorter expiries. It is not zero — see "Known limitations" below. |
| Data source | **yfinance** *(assumed — you didn't answer)* | Free, zero signup, gets the full pipeline (fetch → clean → forward fit → IV solve → surface → arbitrage checks) working end-to-end today. It's an unofficial scraper: it can break without warning and quotes can be stale. All fetching logic lives in one file (`vol_surface/data/fetch.py`) behind one function (`fetch_chain`) specifically so swapping in Polygon/Tradier/Databento/CBOE later is a one-file change. |
| Purpose | **Portfolio piece, built with learning rigor** *(assumed — you didn't answer)* | Since this wasn't answered, the build defaults to the more rigorous end: closed-form Greeks implemented and derived from scratch (not imported), tested against finite differences and put-call parity, forward extracted from the market rather than guessed, and arbitrage checks surfaced in the UI rather than silently ignored. If you actually just wanted a fast working tool, tell me and we can strip this down. |
| Framework | **Streamlit** | You chose this. |

## Architecture

```
vol_surface/
  pricing/
    black_scholes.py   # BSM (spot form) + Black-76 (forward form), closed-form Greeks (1st + 2nd order)
    forward.py          # Implied forward & discount factor via put-call parity OLS regression
    implied_vol.py       # IV solver: Newton-Raphson fast path, Brent's method fallback
  data/
    fetch.py            # yfinance fetch + cleaning (mid price, spread filter, volume/OI filter)
  surface/
    build.py            # log-moneyness/total-variance coordinates, calendar & butterfly arbitrage checks
  pipeline.py            # wires the above into one ticker -> surface call
app/
  dashboard.py           # Streamlit UI: Vol Surface tab + Greeks Explorer tab
tests/
  test_pricing.py         # Greeks vs finite-difference, put-call parity, IV round-trip
  test_surface.py          # surface coordinates + arbitrage detection
```

**Why Black-76, not just spot-form BSM:** spot-form BSM needs a dividend
yield `q`, which for a real underlying is a guess that quietly corrupts
every downstream Greek. Instead, `forward.py` regresses `C(K) - P(K)`
against `K` for each expiry — this line's slope and intercept hand you the
discount factor and the forward *directly from what the market is pricing*,
with no guess at all. Every option's IV is then solved against that expiry's
own fitted forward via Black-76.

**Why Brent, not just Newton-Raphson:** Newton-Raphson divides by vega,
which collapses to ~0 for deep ITM/OTM and short-dated options — exactly
where real chain data is noisiest. The solver tries a fast Newton step first
(converges in 3-4 iterations for liquid near-the-money strikes) and falls
back to Brent's method, which is bracket-guaranteed to find the root on
`[1e-6, 5.0]` and cannot diverge, whenever Newton doesn't converge cleanly.

## Running the tests

```bash
pytest tests/ -v
```

Three families of correctness tests, per the original build plan:
1. Closed-form Greeks vs. finite-difference bumps of the same pricer (delta,
   gamma, vega, theta, rho, vanna, volga, charm).
2. Put-call parity holding to near machine precision, in both spot and
   forward form.
3. IV round-trip: price at a known sigma, solve IV back out, confirm
   recovery to `1e-6` and that re-pricing at the recovered IV reproduces the
   original price.

Plus surface-level tests: log-moneyness/total-variance coordinate
correctness, and that both the calendar and butterfly arbitrage checks
correctly flag a synthetic violation and pass a synthetic clean surface.

### A note on how these tests were verified while building this

The sandbox this was built in has network egress restricted to a small
allowlist that does not include PyPI, so `pytest`, `yfinance`, `streamlit`,
and `plotly` could not actually be `pip install`-ed to run the full suite in
that environment. `numpy`, `scipy`, and `pandas` *were* available there.

To still verify correctness before handing this over, `scripts/verify_pricing.py`
reimplements the same three test families as plain Python assertions (no
pytest) and was run successfully against every scenario in
`tests/test_pricing.py` — see that script's output for the results. All
files were also syntax-checked with `py_compile`, including `data/fetch.py`
and `app/dashboard.py`, which depend on packages not present in that sandbox.
**You should still run `pytest tests/ -v` yourself once dependencies are
installed** — the plain-assertion script covers the same logic but pytest's
run is the one that matters going forward as you extend this.

## Running the dashboard

```bash
streamlit run app/dashboard.py
```

- **Vol Surface tab**: enter a ticker (defaults to SPY), fetch a live chain,
  see the cleaning report, the fitted forward/discount per expiry, the 3D
  surface, and any arbitrage flags.
- **Greeks Explorer tab**: pure sliders over the BSM engine, no network
  call — always works, good for building intuition or if data fetching is
  down.

## New frontend (Next.js + shadcn/ui)

The same functionality is also available as a two-service app: a FastAPI
backend that wraps `vol_surface.pipeline.run_pipeline` as JSON, and a
Next.js + shadcn/ui frontend. Both `app/dashboard.py` (above) and this
frontend currently work side by side — the Streamlit dashboard will be
retired once this frontend is fully verified.

Run both in separate terminals, from the repo root:

```bash
# Terminal 1 — backend (uses the same venv as above)
source .venv/bin/activate
pip install -r backend/requirements.txt
cd backend && uvicorn main:app --reload --port 8000
```

```bash
# Terminal 2 — frontend
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`. The frontend proxies `/api/backend/*` to the
FastAPI server at `:8000` (configured in `frontend/next.config.ts`), so no
CORS setup is needed in dev.

- **Vol Surface tab**: same live-data pipeline as the Streamlit version,
  rendered with Plotly.js.
- **Greeks Explorer tab**: the BSM pricer/Greeks are ported to TypeScript
  (`frontend/lib/bsm.ts`) and run entirely client-side — no backend call
  needed, same as the Streamlit version.

## Known limitations / things to revisit

- **SPY is American-style.** The engine prices European options. The
  early-exercise premium this ignores is small for calls (never optimal to
  exercise a call on a non-dividend-paying asset early, and small even with
  dividends) but real for puts, especially deep ITM puts with meaningful
  time value. If you want this eliminated rather than bounded, the fix is
  either switching to SPX (harder to get reliable full chains from
  yfinance) or adding a Barone-Adesi-Whaley American approximation — flagged
  in the original build plan as a real scope fork, not done here.
- **yfinance reliability.** Treat any single fetch failure as "try again,"
  not as a bug — Yahoo's endpoints are unofficial and occasionally
  rate-limit or return partial data. The pipeline already skips individual
  expiries that error out rather than failing the whole fetch.
- **SVI / spline fitting not yet implemented.** The surface currently plots
  raw solved IV points rather than a fitted parametric slice (SVI) or spline.
  This was recommendation #6 in the original plan and is a natural next
  step once the raw pipeline is validated against real data.
- **Time-to-maturity uses calendar days, not trading days,** with expiry
  approximated at 4pm ET. Calendar-day T is the simpler, slightly-wrong
  choice flagged in the original plan (vol should accrue on trading days).
- **Risk-free rate slider in the Greeks Explorer tab is illustrative only**
  — the Vol Surface tab does not use it at all, since discount factors there
  come from the parity fit, not from `r`.

## Suggested next steps

1. Run this against real SPY data and sanity-check that the surface actually
   shows the expected skew shape (higher IV at low strikes) before trusting
   it further.
2. Add the SVI parametric fit per expiry (recommendation #6) — this is
   probably the highest-value next addition since it turns scattered points
   into a smooth, arbitrage-checkable curve.
3. Decide whether to keep SPY or move to a paid data feed for SPX if the
   American-exercise approximation bothers you.
