"""In-process holder for the currently loaded grids and hydrograph.

Loaded once at API startup (see `main.py`'s lifespan) rather than re-read from
disk on every request - `ingestion.dem.build_elevation_matrix` and
`ingestion.landcover.build_roughness_matrix` do real raster I/O and shouldn't
run per-request. Exposed as FastAPI dependencies rather than read directly
from `app.state` so tests can substitute small synthetic arrays via
`app.dependency_overrides`, without needing the real DEM/land-cover files on
disk or triggering the app's lifespan at all.

`GRIDS` holds one `Grid` per served resolution: the live 30m grid (steps 3-4),
the 90m validation grid (step 10), added so the temporal and fast engines can
be compared at the real May 2024 peak in minutes rather than hours
(docs/tcc-deviations.md section 21), and a 60m grid in between for interactive
runs (scored against May 2024 too, docs/tcc-deviations.md section 24). Each grid bundles everything that
depends only on its own terrain - including the outlet boundary override (step
10) and the north-edge inflow mask (step 9) - so there's no best-effort case
for any of it.

`HYDROGRAPH` (roadmap step 9) is loaded best-effort: if the raw gauge file is
missing or unparseable the lifespan leaves it `None` rather than failing
startup, and `simulations.py` turns a gauge-driven or fast request into a 503
while seeded-pool runs keep working.

`VALIDATION_REFERENCE` is the observed May 2024 extent and the Estrela
coverage-gap exclusion on the 90m validation grid (docs/tcc-deviations.md
section 16.2), so a client can score and draw a run against it. Also
best-effort: without the raw SGB stage layers it stays `None` and
`GET /validation/may2024` answers 503.
"""

from dataclasses import dataclass

import numpy as np
from affine import Affine

from ingestion.hydrograph import Hydrograph


@dataclass
class Grid:
    Z: np.ndarray
    N: np.ndarray
    # MapBiomas class ID per cell, the classes N was looked up from - served to the
    # frontend's roughness layer and cell inspector, since N alone can't name them.
    landcover: np.ndarray
    dx: float  # cell size, m
    bounds: tuple[float, float, float, float]  # west, south, east, north (EPSG:4326)
    # The grid's own projected CRS and affine transform (row/col <-> CRS coordinates),
    # for placing a WGS84 point on an exact cell - see ingestion.dem.lonlat_to_cell.
    crs: str
    transform: Affine
    inflow_mask: np.ndarray
    # Padded (rows+2, cols+2) outlet overrides for simulation.engine.step /
    # fast_engine.classify_steady_flood; None means walled on every side.
    boundary_elevation: np.ndarray | None
    boundary_roughness: np.ndarray | None


@dataclass
class ValidationReference:
    resolution: int  # the served grid it is aligned to, m
    stage_m: float  # the reference layer's river stage
    observed: np.ndarray  # bool: flooded in the SGB/CPRM reference at the peak
    excluded: np.ndarray  # bool: left out of scoring by the coverage-gap correction


GRIDS: dict[int, Grid] = {}
HYDROGRAPH: Hydrograph | None = None
VALIDATION_REFERENCE: ValidationReference | None = None


def get_grids() -> dict[int, Grid]:
    return GRIDS


def get_hydrograph() -> Hydrograph | None:
    return HYDROGRAPH


def get_validation_reference() -> ValidationReference | None:
    return VALIDATION_REFERENCE
