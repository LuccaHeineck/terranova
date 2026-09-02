"""Project settings: paths, region of interest, and DEM acquisition parameters.

Pure settings module - no imports from `simulation/`, `ingestion/`, or `api/` (see
`docs/ARCHITECTURE.md`). Everything else may import this, never the other way around.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent

DATA_DIR = Path(os.environ.get("TERRANOVA_DATA_DIR", str(REPO_ROOT / "data")))
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"

# Region of interest: a small ~6km test box straddling the Taquari river between
# Lajeado and Estrela, RS. Deliberately small for a fast first real-DEM pass -
# widen later (once step 8's real flood-extent ground truth narrows down the area
# that actually matters) by changing these four numbers and re-running
# `scripts/download_dem.py`; nothing else depends on the ROI's size.
ROI_WEST = -51.99
ROI_SOUTH = -29.505
ROI_EAST = -51.93
ROI_NORTH = -29.455

DEM_SOURCE = "SRTMGL1"
DEM_RAW_PATH = RAW_DIR / "lajeado_estrela_srtmgl1.tif"
DEM_PROCESSED_PATH = PROCESSED_DIR / "lajeado_estrela_z.tif"

# SIRGAS 2000 / UTM zone 22S - the standard projected, metric CRS for RS, Brazil.
# The engine assumes square grid cells (see MOORE_OFFSETS/hypot in engine.py), which
# only holds true in a projected CRS, not in the raw GeoTIFF's geographic EPSG:4326.
TARGET_CRS = "EPSG:31982"
TARGET_RESOLUTION_METERS = 30.0

# MapBiomas Collection 10 land-cover classification, used to build the Manning
# roughness matrix N. Year 2024 (not "whatever's newest") deliberately matches the
# May 2024 flood event that step 8 will validate against - land cover and the
# validation ground truth should describe the same year, even though the DEM
# itself is SRTM-era (~2000), a known limitation not addressed at this step.
MAPBIOMAS_YEAR = 2024
MAPBIOMAS_LULC_URL_TEMPLATE = (
    "https://storage.googleapis.com/mapbiomas-public/initiatives/brasil/"
    "collection_10/lulc/coverage/brazil_coverage_{year}.tif"
)
LANDCOVER_RAW_PATH = RAW_DIR / "lajeado_estrela_landcover.tif"
LANDCOVER_PROCESSED_PATH = PROCESSED_DIR / "lajeado_estrela_n.tif"

OPENTOPOGRAPHY_API_URL = "https://portal.opentopography.org/API/globaldem"

CORS_ALLOWED_ORIGINS = os.environ.get(
    "CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
).split(",")


def get_opentopography_api_key() -> str:
    """Read the OpenTopography API key from the environment.

    Raised lazily (only when actually needed for a download), not at import time,
    so the rest of the app can be imported/tested without the key set.
    """
    key = os.environ.get("OPENTOPOGRAPHY_API_KEY")
    if not key:
        raise RuntimeError(
            "OPENTOPOGRAPHY_API_KEY is not set. Get a free key at "
            "https://opentopography.org (My Account -> API Key) and set it in "
            "backend/.env or the environment."
        )
    return key
