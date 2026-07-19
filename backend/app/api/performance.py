"""Performance endpoint — latest tracked strategy performance."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..feedback.outcomes import get_latest_perf_text
from ..models import PerfSummary
from ..schemas import PerfOut

router = APIRouter()


@router.get("/performance", response_model=PerfOut, tags=["performance"])
def get_performance(db: Session = Depends(get_db)):
    row = db.scalar(select(PerfSummary).order_by(PerfSummary.generated_at.desc()))
    if row is None:
        # no tracked history yet — return a transient empty one with a fresh narrative
        return PerfOut(narrative=get_latest_perf_text(db))
    # PerfOut's field_validators handle the JSON-string -> dict coercion.
    return PerfOut.model_validate(row)
