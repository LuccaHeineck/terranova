"""One-off CLI: download the real SGB/CPRM (via IPH-UFRGS) flood-extent polygons
for Lajeado - the stage layer closest to the May 2024 peak, plus the two lower
stage layers the Estrela coverage-gap correction compares it against
(`config.settings.FLOOD_EXTENT_STAGE_LAYERS`, docs/tcc-deviations.md section 16.2).

Fetches GeoJSON from a public, no-auth ArcGIS REST MapServer query endpoint (see
`config.settings.SGB_LAJEADO_MAPSERVER_URL`'s docstring comment for the layer
choice and why `resultRecordCount` must not be passed) and saves each response
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
    params = {"where": "1=1", "outFields": "*", "f": "geojson"}
    settings.RAW_DIR.mkdir(parents=True, exist_ok=True)

    for layer_id, (stage_m, raw_path) in settings.FLOOD_EXTENT_STAGE_LAYERS.items():
        url = f"{settings.SGB_LAJEADO_MAPSERVER_URL}/{layer_id}/query"
        response = requests.get(url, params=params, timeout=60)
        response.raise_for_status()
        raw_path.write_bytes(response.content)
        print(f"Saved {len(response.content):,} bytes (layer {layer_id}, {stage_m:.2f}m) to {raw_path}")


if __name__ == "__main__":
    download_flood_extent()
