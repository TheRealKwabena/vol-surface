"""Pydantic request/response models for the vol-surface API.

Deliberately thin: the response bodies mostly carry through whatever
columns vol_surface.pipeline.run_pipeline already produces (as
List[Dict[str, Any]]) rather than re-declaring every DataFrame column as
a typed field, since that set is driven by the pricing/surface code, not
by this API layer.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class VolSurfaceRequest(BaseModel):
    ticker: str = "SPY"
    max_expiries: int = Field(8, ge=1, le=20)
    max_spread_frac: float = Field(0.40, ge=0.05, le=1.0)
    require_volume_or_oi: bool = True


class CleaningReport(BaseModel):
    rows_in: int = 0
    rows_out: int = 0
    rows_dropped: int = 0
    filters: dict[str, int] = {}


class VolSurfaceResponse(BaseModel):
    ticker: str
    cleaning_report: CleaningReport
    forward_fits: list[dict[str, Any]]
    convergence_rate: float
    surface_points: list[dict[str, Any]]
    calendar_violations: list[dict[str, Any]]
    butterfly_violations: list[dict[str, Any]]
