"""The real May 2024 gauge hydrograph that drives gauge-driven and fast runs.

Serves what `ingestion.hydrograph.build_hydrograph` loaded at startup
(`api.state.HYDROGRAPH`): discharge at station 86879300 (Porto Fluvial de
Estrela) over the event, on the same elapsed-time axis the gauge-driven frames'
`elapsed_time` uses, so a client can chart the record and mark where a run's
timeline is on it.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.state import get_hydrograph
from config.settings import HYDROGRAPH_STATION_CODE
from ingestion.hydrograph import Hydrograph

router = APIRouter()


class HydrographRecord(BaseModel):
    station_code: str
    # Seconds since the record's first reading - t = 0 of a gauge-driven run.
    elapsed_seconds: list[float]
    discharge_m3s: list[float]
    peak_elapsed_seconds: float
    peak_discharge_m3s: float


@router.get("/hydrograph", response_model=HydrographRecord)
def get_hydrograph_record(hydrograph: Hydrograph | None = Depends(get_hydrograph)) -> HydrographRecord:
    if hydrograph is None:
        raise HTTPException(
            status_code=503,
            detail="The gauge hydrograph is not loaded: run scripts/download_hydrograph.py and restart.",
        )
    return HydrographRecord(
        station_code=HYDROGRAPH_STATION_CODE,
        elapsed_seconds=hydrograph.elapsed_seconds.tolist(),
        discharge_m3s=hydrograph.discharge_m3s.tolist(),
        peak_elapsed_seconds=hydrograph.peak_elapsed_seconds,
        peak_discharge_m3s=hydrograph.peak_discharge_m3s,
    )
