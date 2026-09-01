"""
FastAPI wrapper around vol_surface.pipeline.run_pipeline.

Pure JSON-serialization layer -- no pricing/surface/cleaning logic lives
here. Every DataFrame the pipeline produces is converted to a list of
JSON-safe records (NaN -> None) and passed through.

Run with:  uvicorn main:app --reload --port 8000   (from this directory)
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow `from vol_surface...` regardless of the working directory this is
# launched from, same trick app/dashboard.py uses for the Streamlit app.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from schemas import CleaningReport, VolSurfaceRequest, VolSurfaceResponse
from vol_surface.data.fetch import ChainCleaningConfig
from vol_surface.pipeline import run_pipeline

app = FastAPI(title="Vol Surface API")

# Only needed as a fallback -- the frontend talks to this same-origin via
# Next.js rewrites in dev, but CORS is left open for localhost so the API
# can also be hit directly (curl, a different frontend port, etc.).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _records(df: pd.DataFrame) -> list[dict]:
    """DataFrame -> JSON-safe list of records (NaN -> None)."""
    return df.replace({np.nan: None}).to_dict(orient="records")


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/vol-surface", response_model=VolSurfaceResponse)
def vol_surface(req: VolSurfaceRequest):
    config = ChainCleaningConfig(
        max_spread_frac=req.max_spread_frac,
        require_volume_or_oi=req.require_volume_or_oi,
    )
    try:
        result = run_pipeline(req.ticker, max_expiries=req.max_expiries, cleaning_config=config)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline failed: {e}")

    solved = result["solved_options"]
    convergence_rate = float(solved["iv_converged"].mean() * 100) if len(solved) else 0.0

    return VolSurfaceResponse(
        ticker=req.ticker,
        cleaning_report=CleaningReport(**result["cleaning_report"]),
        forward_fits=_records(result["forward_fits"].reset_index()),
        convergence_rate=convergence_rate,
        surface_points=_records(result["surface"]),
        calendar_violations=_records(result["calendar_violations"]),
        butterfly_violations=_records(result["butterfly_violations"]),
    )
