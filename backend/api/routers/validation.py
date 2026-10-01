"""The observed May 2024 flood extent a run is validated against.

Serves what `ingestion.flood_extent.build_validation_reference` loaded at
startup (`api.state.VALIDATION_REFERENCE`): the SGB/CPRM reference extent at the
peak stage and the cells the Estrela coverage-gap correction leaves out of
scoring (docs/tcc-deviations.md section 16.2), both on the 90m validation grid.
The client scores each frame itself - the same confusion counts as
`validation.metrics` - so the numbers follow the timeline without a request per
frame.
"""

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.state import ValidationReference, get_validation_reference

router = APIRouter()


class ObservedExtent(BaseModel):
    resolution: int
    grid_shape: tuple[int, int]
    stage_m: float
    # Row-major flat cell indices (row * cols + col), the order frames' depth grids use.
    observed_cells: list[int]
    excluded_cells: list[int]


def _flat_indices(mask: np.ndarray) -> list[int]:
    return np.flatnonzero(mask).tolist()


@router.get("/validation/may2024", response_model=ObservedExtent)
def observed_may2024(
    reference: ValidationReference | None = Depends(get_validation_reference),
) -> ObservedExtent:
    if reference is None:
        raise HTTPException(
            status_code=503,
            detail="The observed May 2024 extent is not loaded: run scripts/download_flood_extent.py and restart.",
        )
    return ObservedExtent(
        resolution=reference.resolution,
        grid_shape=reference.observed.shape,
        stage_m=reference.stage_m,
        observed_cells=_flat_indices(reference.observed),
        excluded_cells=_flat_indices(reference.excluded),
    )
