"""One-off CLI: download the raw land-cover tile for the Lajeado/Estrela ROI.

Unlike `download_dem.py`, no server-side clipping API is used: MapBiomas publishes
the classification as a single public, unauthenticated, tiled Cloud-Optimized
GeoTIFF for all of Brazil (~800 MB) on Google Cloud Storage. Opening it through
GDAL's `/vsicurl/` HTTP driver and reading only the window that covers our ROI
pulls just the overlapping tiles over the network, not the whole file - no API
key needed (simpler than step 3's OpenTopography key). Run as a module from
`backend/`:

    .venv/bin/python -m scripts.download_landcover
"""

import rasterio
from rasterio.windows import from_bounds

from config import settings


def download_landcover() -> None:
    url = "/vsicurl/" + settings.MAPBIOMAS_LULC_URL_TEMPLATE.format(year=settings.MAPBIOMAS_YEAR)

    settings.RAW_DIR.mkdir(parents=True, exist_ok=True)
    with rasterio.open(url) as src:
        window = from_bounds(
            settings.ROI_WEST, settings.ROI_SOUTH, settings.ROI_EAST, settings.ROI_NORTH, src.transform
        )
        data = src.read(1, window=window)
        transform = src.window_transform(window)

        profile = {
            "driver": "GTiff",
            "dtype": data.dtype,
            "width": data.shape[1],
            "height": data.shape[0],
            "count": 1,
            "crs": src.crs,
            "transform": transform,
        }
        with rasterio.open(settings.LANDCOVER_RAW_PATH, "w", **profile) as dst:
            dst.write(data, 1)

    print(f"Saved {settings.LANDCOVER_RAW_PATH}")


if __name__ == "__main__":
    download_landcover()
