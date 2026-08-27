"""In-process holder for the currently loaded terrain/roughness arrays.

Loaded once at API startup (see `main.py`'s lifespan) rather than re-read from
disk on every request - `ingestion.dem.build_elevation_matrix` and
`ingestion.landcover.build_roughness_matrix` do real raster I/O and shouldn't
run per-request. Exposed as FastAPI dependencies rather than read directly
from `app.state` so tests can substitute small synthetic arrays via
`app.dependency_overrides`, without needing the real DEM/land-cover files on
disk or triggering the app's lifespan at all.
"""

import numpy as np

Z: np.ndarray | None = None
N: np.ndarray | None = None


def get_terrain() -> np.ndarray:
    return Z


def get_roughness() -> np.ndarray:
    return N
