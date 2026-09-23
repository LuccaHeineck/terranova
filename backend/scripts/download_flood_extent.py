"""One-off CLI: download the real SGB/CPRM (via IPH-UFRGS) flood-extent polygon
for Lajeado at the stage layer closest to the May 2024 peak.

Fetches GeoJSON from a public, no-auth ArcGIS REST MapServer query endpoint (see
`config.settings.SGB_LAJEADO_MAPSERVER_URL`'s docstring comment for the layer
choice and why `resultRecordCount` must not be passed) and saves the response
body unparsed - same "network fetch only" split as
`download_dem.py`/`download_landcover.py`/`download_hydrograph.py`;
`ingestion/flood_extent.py` does all GeoJSON parsing. Run as a module from
`backend/`:

    .venv/bin/python -m scripts.download_flood_extent

No API key required.
"""

import requests

from config import settings


def download_flood_extent() -> None:
    url = f"{settings.SGB_LAJEADO_MAPSERVER_URL}/{settings.FLOOD_EXTENT_LAYER_ID}/query"
    params = {"where": "1=1", "outFields": "*", "f": "geojson"}

    settings.RAW_DIR.mkdir(parents=True, exist_ok=True)
    response = requests.get(url, params=params, timeout=60)
    response.raise_for_status()

    settings.FLOOD_EXTENT_RAW_PATH.write_bytes(response.content)
    print(f"Saved {len(response.content):,} bytes to {settings.FLOOD_EXTENT_RAW_PATH}")


if __name__ == "__main__":
    download_flood_extent()
