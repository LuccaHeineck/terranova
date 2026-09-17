"""In-process holder for the currently loaded terrain/roughness arrays.

Loaded once at API startup (see `main.py`'s lifespan) rather than re-read from
disk on every request - `ingestion.dem.build_elevation_matrix` and
`ingestion.landcover.build_roughness_matrix` do real raster I/O and shouldn't
run per-request. Exposed as FastAPI dependencies rather than read directly
from `app.state` so tests can substitute small synthetic arrays via
`app.dependency_overrides`, without needing the real DEM/land-cover files on
disk or triggering the app's lifespan at all.

`HYDROGRAPH`/`INFLOW_MASK` (roadmap step 9's gauge-driven mode) are held the same
way but loaded best-effort: if the raw gauge file is missing or unparseable the
lifespan leaves both as `None` rather than failing startup, and `simulations.py`
turns a gauge-driven request into a 503 while seeded-pool runs keep working.
"""

import numpy as np

from ingestion.hydrograph import Hydrograph

Z: np.ndarray | None = None
N: np.ndarray | None = None
BOUNDS: tuple[float, float, float, float] | None = None
HYDROGRAPH: Hydrograph | None = None
INFLOW_MASK: np.ndarray | None = None


def get_terrain() -> np.ndarray:
    return Z


def get_roughness() -> np.ndarray:
    return N


def get_bounds() -> tuple[float, float, float, float]:
    return BOUNDS


def get_hydrograph() -> Hydrograph | None:
    return HYDROGRAPH


def get_inflow_mask() -> np.ndarray | None:
    return INFLOW_MASK
