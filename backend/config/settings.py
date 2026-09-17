"""Project settings: paths, region of interest, and DEM acquisition parameters.

Pure settings module - no imports from `simulation/`, `ingestion/`, or `api/` (see
`docs/ARCHITECTURE.md`). Everything else may import this, never the other way around.
"""

import os
from datetime import datetime
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

# ANA/SGB fluviometric gauge station 86879300, Porto Fluvial de Estrela (Taquari
# river) - inside this project's own ROI. Feeds roadmap step 9's gauge-driven
# hydrograph.
HYDROGRAPH_STATION_CODE = "86879300"

# The May 2024 RS flood event window at this station, with a few days of lead-in
# before the rise and past the peak/initial recession. Verify against the real
# downloaded series in Task 1, Step 3 below - if the series is clipped mid-rise
# or mid-recession, widen these and re-run download_hydrograph.py.
HYDROGRAPH_EVENT_START = datetime(2024, 4, 27)
HYDROGRAPH_EVENT_END = datetime(2024, 5, 10)

# ANA's older SOAP/ASMX telemetry service - no API key required, unlike the
# newer OAuth-based hidrowebservice (which requires emailing hidro@ana.gov.br
# for access; see https://www.ana.gov.br/hidrowebservice/manual). Confirmed
# live 2026-09-16.
#
# NOTE: this is the `DadosHidrometeorologicos` operation, not
# `HidroSerieHistorica` (an earlier draft of this constant pointed there).
# HidroSerieHistorica returns ANA's monthly *conventional-station* summary
# table (one row per fixed reading-hour-of-day, with Cota01..Cota31 columns
# holding that hour's value for each day of the month) - not a real
# timestamped series, and for this station/window it silently dropped the
# April rows entirely. DadosHidrometeorologicos returns actual irregular
# sub-hourly telemetric readings (CodEstacao/DataHora/Vazao/Nivel/Chuva per
# row) and covers the full requested window exactly - see
# `scripts/download_hydrograph.py`'s docstring and `ingestion/hydrograph.py`'s
# header comment (Task 2) for the verified schema details.
ANA_TELEMETRIA_URL = "https://telemetriaws1.ana.gov.br/ServiceANA.asmx/DadosHidrometeorologicos"

HYDROGRAPH_RAW_PATH = RAW_DIR / "estrela_stage_may2024.xml"

# Which ROI boundary edge the river enters from upstream. Determined empirically
# in Task 3 from the real processed Z (the edge whose channel cells have the
# highest minimum elevation is upstream - water flows downhill along the
# channel toward the opposite edge). Verified against the real DEM:
# north min=12.0, south min=11.0, west min=23.0, east min=26.0 - east has the
# highest minimum, so it is upstream (corrected from an earlier unverified
# "south" assumption made before the real DEM was available).
HYDROGRAPH_INFLOW_EDGE = "east"

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
