"""One-off CLI: download the raw DEM tile for the Lajeado/Estrela ROI.

Fetches a GeoTIFF from the OpenTopography REST API, already clipped server-side to
the bounding box in `config.settings` - no separate clipping step needed. Run as a
module from `backend/`:

    .venv/bin/python -m scripts.download_dem

Requires OPENTOPOGRAPHY_API_KEY (see `config.settings.get_opentopography_api_key`).
"""

import requests

from config import settings


def download_dem() -> None:
    params = {
        "demtype": settings.DEM_SOURCE,
        "south": settings.ROI_SOUTH,
        "north": settings.ROI_NORTH,
        "west": settings.ROI_WEST,
        "east": settings.ROI_EAST,
        "outputFormat": "GTiff",
        "API_Key": settings.get_opentopography_api_key(),
    }

    settings.RAW_DIR.mkdir(parents=True, exist_ok=True)
    response = requests.get(settings.OPENTOPOGRAPHY_API_URL, params=params, timeout=60)
    response.raise_for_status()

    settings.DEM_RAW_PATH.write_bytes(response.content)
    print(f"Saved {len(response.content):,} bytes to {settings.DEM_RAW_PATH}")


if __name__ == "__main__":
    download_dem()
