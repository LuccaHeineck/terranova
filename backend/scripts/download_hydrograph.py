"""One-off CLI: download the raw irregular-interval, sub-hourly telemetric stage
(water level) record for ANA/SGB gauge station 86879300 (Porto Fluvial de Estrela)
covering the May 2024 flood event window.

Fetches raw XML from ANA's older, no-API-key telemetria1ws SOAP/ASMX service's
`DadosHidrometeorologicos` operation (see `config.settings.ANA_TELEMETRIA_URL`'s
docstring comment for why this operation, not `HidroSerieHistorica` or the newer
OAuth hidrowebservice) and saves the response body unparsed - same "network fetch
only" split as `download_dem.py`/`download_landcover.py`; `ingestion/hydrograph.py`
does all XML parsing. Run as a module from `backend/`:

    .venv/bin/python -m scripts.download_hydrograph

No API key required.
"""

import requests

from config import settings


def download_hydrograph() -> None:
    params = {
        "codEstacao": settings.HYDROGRAPH_STATION_CODE,
        "dataInicio": settings.HYDROGRAPH_EVENT_START.strftime("%d/%m/%Y"),
        "dataFim": settings.HYDROGRAPH_EVENT_END.strftime("%d/%m/%Y"),
    }

    settings.RAW_DIR.mkdir(parents=True, exist_ok=True)
    response = requests.get(settings.ANA_TELEMETRIA_URL, params=params, timeout=60)
    response.raise_for_status()

    settings.HYDROGRAPH_RAW_PATH.write_bytes(response.content)
    print(f"Saved {len(response.content):,} bytes to {settings.HYDROGRAPH_RAW_PATH}")


if __name__ == "__main__":
    download_hydrograph()
