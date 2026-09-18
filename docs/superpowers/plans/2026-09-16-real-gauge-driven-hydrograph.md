# Real gauge-driven hydrograph (roadmap step 9) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the real May 2024 Taquari flood event (ANA/SGB gauge station `86879300`, Porto
Fluvial de Estrela) end-to-end — gauge stage readings → discharge → per-cell `inflow` → the
WebSocket stream → the frontend — so a user can run a real, gauge-driven flood through the actual
app, not just through a Python script.

**Architecture:** A new `backend/ingestion/hydrograph.py` module converts the raw gauge stage
record into a queryable discharge time series and a per-cell boundary inflow array, following the
exact two-file acquisition/processing split already established by `dem.py`/`landcover.py`.
`api/routers/simulations.py` gains a `mode` field (`"seeded_pool"` unchanged, new
`"gauge_driven"`) that drives the existing engine's `compute_stable_dt`/`inflow` machinery in a
loop until the hydrograph's recorded duration is reached. The frontend gets a mode toggle and
shows elapsed real time instead of only step count for gauge-driven runs.

**Tech Stack:** Python/NumPy/FastAPI (backend, unchanged), React/TypeScript/Vite (frontend,
unchanged), `requests` for the new ANA network call (already a dependency).

**Spec:** `docs/superpowers/specs/2026-09-16-real-gauge-driven-hydrograph-design.md`

## Global Constraints

- No downsampling of the event and no real-time playback throttling — a gauge-driven run proceeds
  as fast as the engine computes, however long that takes in wall-clock time.
- The existing closed-system, seeded-pool run (`mode: "seeded_pool"`) must keep working exactly as
  today — this is an additive mode, not a replacement.
- Inflow is injected via river-channel cells on one ROI boundary edge (found from the real `Z`),
  never at the gauge's literal lat/lon (the gauge sits inside the ROI, not at a boundary).
- Stage → discharge conversion uses a real rating curve, not a proportional/threshold
  approximation.
- No changes to `backend/simulation/engine.py` — `step()` and `compute_stable_dt()` already
  support everything this feature needs; this plan is wiring only.
- All new backend tests must be network-free, matching every existing test file in
  `backend/tests/` (`dependency_overrides`/synthetic fixtures, never a real ANA call in `pytest`).
- No new frontend test framework — frontend changes are verified manually in-browser, matching
  step 6/7's own stated verification practice (this repo has no frontend test framework yet).

---

## Known risk, flagged up front (RESOLVED during Task 1 — see ledger)

Task 1 hit a live external API (ANA's `telemetria1ws` SOAP/ASMX service) whose exact XML response
schema could not be verified from inside the planning session. Task 1's implementer ran the
originally-drafted `HidroSerieHistorica` operation for real, found it returned the wrong data shape
(a monthly summary, not a timestamped series), located and switched to the correct
`DadosHidrometeorologicos` operation via the service's live WSDL, and confirmed the real schema
against an actual 610-row download covering the full requested window. Task 1's report also
surfaced a real `Vazao` (discharge) field on some rows, which changed Task 2's design — see Task 2's
ruling note below. Task 2's code/tests in this plan already reflect the confirmed real schema and
the `Vazao`-based ruling, not the original speculative draft.

---

### Task 1: Acquire the raw gauge stage record

**Files:**
- Modify: `backend/config/settings.py`
- Create: `backend/scripts/download_hydrograph.py`

**Interfaces:**
- Consumes: `settings.RAW_DIR` (existing).
- Produces: `settings.HYDROGRAPH_STATION_CODE`, `settings.HYDROGRAPH_EVENT_START`,
  `settings.HYDROGRAPH_EVENT_END`, `settings.ANA_TELEMETRIA_URL`,
  `settings.HYDROGRAPH_RAW_PATH` (all consumed by Task 2); a real file on disk at
  `HYDROGRAPH_RAW_PATH`.

- [ ] **Step 1: Add hydrograph settings constants**

Add to `backend/config/settings.py`, near the existing `MAPBIOMAS_*`/`OPENTOPOGRAPHY_*` constants:

```python
from datetime import datetime

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
# for access; see https://www.ana.gov.br/hidrowebservice/manual). Confirm this
# still resolves and returns data for the station/window above before relying
# on it for real - ANA has migrated/retired services before.
ANA_TELEMETRIA_URL = "https://telemetriaws1.ana.gov.br/ServiceANA.asmx/HidroSerieHistorica"

HYDROGRAPH_RAW_PATH = RAW_DIR / "estrela_stage_may2024.xml"

# Which ROI boundary edge the river enters from upstream. Determined empirically
# in Task 3 from the real processed Z (the edge whose channel cells have the
# highest minimum elevation is upstream - water flows downhill along the
# channel toward the opposite edge). This value is a starting assumption only -
# Task 3 requires running the actual check and correcting this if it disagrees.
HYDROGRAPH_INFLOW_EDGE = "south"
```

- [ ] **Step 2: Write the download script**

Create `backend/scripts/download_hydrograph.py`:

```python
"""One-off CLI: download the raw 15-minute stage (water level) record for ANA/SGB
gauge station 86879300 (Porto Fluvial de Estrela) covering the May 2024 flood event
window.

Fetches raw XML from ANA's older, no-API-key telemetria1ws SOAP/ASMX service (see
`config.settings.ANA_TELEMETRIA_URL`'s docstring comment for why this one, not the
newer OAuth hidrowebservice) and saves the response body unparsed - same
"network fetch only" split as `download_dem.py`/`download_landcover.py`;
`ingestion/hydrograph.py` does all XML parsing. Run as a module from `backend/`:

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
        "tipoDados": "1",  # 1 = Cotas (stage/level, cm) per ANA's documented convention
        "nivelConsistencia": "1",
    }

    settings.RAW_DIR.mkdir(parents=True, exist_ok=True)
    response = requests.get(settings.ANA_TELEMETRIA_URL, params=params, timeout=60)
    response.raise_for_status()

    settings.HYDROGRAPH_RAW_PATH.write_bytes(response.content)
    print(f"Saved {len(response.content):,} bytes to {settings.HYDROGRAPH_RAW_PATH}")


if __name__ == "__main__":
    download_hydrograph()
```

- [ ] **Step 3: Run it for real and inspect the response**

Run: `cd backend && .venv/bin/python -m scripts.download_hydrograph`

Expected: a non-trivial file (more than a few hundred bytes, not a SOAP fault/error XML) saved to
`data/raw/estrela_stage_may2024.xml`.

Open the saved file and read it. Record, as a comment at the top of `ingestion/hydrograph.py`
(written in Task 2), the real answers to:
- What is the root element and the per-reading row element's tag name? (Legacy ASMX services
  serializing a .NET `DataSet` typically use a `<DocumentElement>` or `<NewDataSet>` root with
  repeated `<Table>` child elements, one per reading - confirm whether that's what you see.)
- What is the exact tag name holding the timestamp, and what format is it in (e.g.
  `dd/MM/yyyy HH:mm:ss`)?
- What is the exact tag name holding the stage reading, and what units (ANA typically reports
  `Cota` in **centimeters**, not meters - confirm and note the conversion factor needed)?

If the request fails, returns a SOAP fault, or the station/date range yields no rows: check
`https://www.ana.gov.br/hidrowebservice/manual` for whether `telemetria1ws` has been retired, and
whether the station code, date format, or `tipoDados` value need adjusting. Do not proceed to
Task 2 until a real, non-empty response has been inspected.

- [ ] **Step 4: Commit**

```bash
git add backend/config/settings.py backend/scripts/download_hydrograph.py
git commit -m "feat: add ANA gauge stage download script for station 86879300"
```

---

### Task 2: Parse the raw record into a queryable discharge hydrograph

**Files:**
- Create: `backend/ingestion/hydrograph.py`
- Test: `backend/tests/test_hydrograph.py`

**Interfaces:**
- Consumes: the real, confirmed raw XML schema from Task 1's report (root `<DataTable>`, real data
  under `<diffgr:diffgram><DocumentElement xmlns="">`, row tag `<DadosHidrometereologicos>` — note
  ANA's own spelling, `<DataHora>` as `"yyyy-MM-dd HH:mm:ss "` with a trailing space, `<Nivel>` in
  centimeters, rows in descending time order, one observed row with an empty `<Nivel />`).
- Produces: `Hydrograph` (dataclass: `elapsed_seconds: np.ndarray`, `discharge_m3s: np.ndarray`,
  `duration_seconds` property, `discharge_at(elapsed_seconds: float) -> float` method),
  `stage_to_discharge(stage_m, rating_curve) -> np.ndarray`,
  `load_raw_stage_series(raw_path) -> tuple[np.ndarray, np.ndarray]`,
  `find_calibration_pairs(raw_path) -> list[tuple[float, float]]`,
  `build_hydrograph(raw_path=settings.HYDROGRAPH_RAW_PATH) -> Hydrograph` — all consumed by
  Task 4's `api/state.py`.

**Ruling (controller, preflight-during-execution — see ledger):** Task 1's real download revealed
that ANA's response carries a `Vazao` (discharge, m³/s) field directly on some rows alongside
`Nivel` (stage) — real, ANA-computed discharge for this exact station, not something this task
needs to independently research from an external source. This supersedes the original plan's
"research and hardcode an externally-cited `RATING_CURVE_POINTS` table" instruction: instead,
`find_calibration_pairs` extracts real (stage, discharge) pairs directly from the same downloaded
file wherever `Vazao` is present, and `build_hydrograph` uses those as the rating curve for the
rest of the series. Because those real pairs may not span the full observed stage range for this
event (`Vazao` is only present on a subset of rows), `stage_to_discharge` clips to the nearest
calibrated endpoint outside that range (flat extrapolation, via plain `np.interp` semantics) instead
of raising — a documented simplification in the same spirit as `simulation.engine`'s
`_NO_FLOW_FALLBACK_DT_SECONDS`. This is more accurate than an independently-sourced generic curve
and removes the previous plan's external-research risk entirely.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_hydrograph.py`:

```python
import numpy as np
import pytest

from ingestion.hydrograph import Hydrograph, find_calibration_pairs, load_raw_stage_series, stage_to_discharge

# Shape confirmed against a real download in Task 1 (see task-1-report.md) - root
# <DataTable xmlns="http://MRCS/"> wraps an inline xs:schema block (no readings,
# skip) and a <diffgr:diffgram><DocumentElement xmlns=""> holding the real rows.
# Note the row tag's real spelling (`DadosHidrometereologicos`, extra "re" - ANA's
# own inconsistency, not a typo) and the trailing space inside <DataHora> text.
_SAMPLE_XML = """<?xml version="1.0" encoding="utf-8"?>
<DataTable xmlns="http://MRCS/">
  <xs:schema id="NewDataSet" xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:msdata="urn:schemas-microsoft-com:xml-msdata" />
  <diffgr:diffgram xmlns:msdata="urn:schemas-microsoft-com:xml-msdata" xmlns:diffgr="urn:schemas-microsoft-com:xml-diffgram-v1">
    <DocumentElement xmlns="">
      <DadosHidrometereologicos diffgr:id="r1" msdata:rowOrder="0">
        <CodEstacao>86879300</CodEstacao>
        <DataHora>2024-05-01 00:30:00 </DataHora>
        <Vazao />
        <Nivel>1300.00</Nivel>
        <Chuva />
      </DadosHidrometereologicos>
      <DadosHidrometereologicos diffgr:id="r2" msdata:rowOrder="1">
        <CodEstacao>86879300</CodEstacao>
        <DataHora>2024-05-01 00:15:00 </DataHora>
        <Vazao>5000.00</Vazao>
        <Nivel>1250.00</Nivel>
        <Chuva />
      </DadosHidrometereologicos>
      <DadosHidrometereologicos diffgr:id="r3" msdata:rowOrder="2">
        <CodEstacao>86879300</CodEstacao>
        <DataHora>2024-05-01 00:00:00 </DataHora>
        <Vazao>10000.00</Vazao>
        <Nivel>1200.00</Nivel>
        <Chuva />
      </DadosHidrometereologicos>
    </DocumentElement>
  </diffgr:diffgram>
</DataTable>
"""


def test_stage_to_discharge_interpolates_linearly_between_breakpoints():
    curve = [(0.0, 0.0), (10.0, 100.0), (20.0, 500.0)]

    discharge = stage_to_discharge(np.array([5.0, 15.0]), rating_curve=curve)

    assert discharge.tolist() == pytest.approx([50.0, 300.0])


def test_stage_to_discharge_clips_to_nearest_endpoint_outside_curve_range():
    curve = [(0.0, 0.0), (10.0, 100.0)]

    discharge = stage_to_discharge(np.array([-5.0, 15.0]), rating_curve=curve)

    assert discharge.tolist() == pytest.approx([0.0, 100.0])


def test_load_raw_stage_series_parses_real_ana_response_shape(tmp_path):
    raw_path = tmp_path / "raw.xml"
    raw_path.write_text(_SAMPLE_XML)

    elapsed_seconds, stage_m = load_raw_stage_series(raw_path)

    # Rows arrive in descending time order in the real feed; the parser must
    # re-sort ascending before computing elapsed time.
    assert elapsed_seconds.tolist() == pytest.approx([0.0, 900.0, 1800.0])
    assert stage_m.tolist() == pytest.approx([12.0, 12.5, 13.0])  # cm -> m


def test_load_raw_stage_series_skips_rows_with_empty_nivel(tmp_path):
    raw_path = tmp_path / "raw.xml"
    raw_path.write_text(_SAMPLE_XML.replace("<Nivel>1200.00</Nivel>", "<Nivel />"))

    elapsed_seconds, stage_m = load_raw_stage_series(raw_path)

    assert len(elapsed_seconds) == 2
    assert stage_m.tolist() == pytest.approx([12.0, 13.0])


def test_find_calibration_pairs_extracts_rows_with_both_nivel_and_vazao(tmp_path):
    raw_path = tmp_path / "raw.xml"
    raw_path.write_text(_SAMPLE_XML)

    pairs = find_calibration_pairs(raw_path)

    # Only the 2 rows with a non-empty <Vazao> contribute; sorted by stage.
    assert pairs == [(12.0, 10000.0), (12.5, 5000.0)]


def test_hydrograph_discharge_at_interpolates_between_samples():
    hydrograph = Hydrograph(
        elapsed_seconds=np.array([0.0, 900.0, 1800.0]),
        discharge_m3s=np.array([100.0, 200.0, 300.0]),
    )

    assert hydrograph.discharge_at(450.0) == pytest.approx(150.0)
    assert hydrograph.duration_seconds == pytest.approx(1800.0)


def test_hydrograph_discharge_at_raises_outside_recorded_range():
    hydrograph = Hydrograph(elapsed_seconds=np.array([0.0, 900.0]), discharge_m3s=np.array([100.0, 200.0]))

    with pytest.raises(ValueError, match="range"):
        hydrograph.discharge_at(1000.0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_hydrograph.py -v`
Expected: FAIL with `ImportError`/`ModuleNotFoundError` (`ingestion.hydrograph` doesn't exist yet).

- [ ] **Step 3: Write the implementation**

Create `backend/ingestion/hydrograph.py`:

```python
"""Turn the raw ANA/SGB gauge record for station 86879300 (Porto Fluvial de
Estrela) into a queryable discharge hydrograph.

Raw XML shape (confirmed against a real download - see
`.superpowers/sdd/2026-09-16-real-gauge-driven-hydrograph/task-1-report.md`):
root `<DataTable xmlns="http://MRCS/">` wraps an inline `<xs:schema>` block (the
dataset's schema, not data - skipped) and a
`<diffgr:diffgram><DocumentElement xmlns="">` holding the real rows, one
`<DadosHidrometereologicos>` element per reading (note ANA's own spelling, an
extra "re" versus the operation name), each with `<DataHora>` ("yyyy-MM-dd
HH:mm:ss ", trailing space), `<Nivel>` (stage, centimeters - occasionally an
empty `<Nivel />`), `<Vazao>` (discharge, m3/s - present only on a subset of
rows), and `<Chuva>` (rainfall, unused here). Rows arrive in descending time
order.

Pipeline: `load_raw_stage_series` parses the raw XML into (elapsed_seconds,
stage_m) - local-only, mirroring `dem.py`/`landcover.py`'s "network script saves
raw bytes, ingestion module does all parsing" split. `find_calibration_pairs`
extracts real (stage, discharge) pairs from the same file wherever ANA's own
`Vazao` is present - this station's real, already-computed discharge, not an
independently sourced generic curve (see the plan's Task 2 ruling for why this
differs from earlier drafts of this task). `stage_to_discharge` applies that
curve to the full stage series (`np.interp` clips outside the curve's calibrated
range rather than raising - real `Vazao` coverage may not span this event's full
observed stage range). `build_hydrograph` runs all of this and returns a
`Hydrograph`, queryable at arbitrary elapsed times via linear interpolation -
needed because the engine's `dt` (from `simulation.engine.compute_stable_dt`) is
adaptive, not fixed to the raw feed's irregular sample spacing.

Reads from `data/raw/`. Depends on `config/` for paths. No CA logic here, no
imports from `simulation/` - see `docs/ARCHITECTURE.md`.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree

import numpy as np

from config import settings


def _read_rows(raw_path: Path) -> list[ElementTree.Element]:
    """Shared row-extraction for both `load_raw_stage_series` and
    `find_calibration_pairs` - parse once, skip past the `<xs:schema>` block
    to the real `<DocumentElement>` under the diffgram, return its rows.
    """
    tree = ElementTree.parse(raw_path)
    document_element = next(tree.getroot().iter("DocumentElement"))
    return document_element.findall("DadosHidrometereologicos")


def load_raw_stage_series(raw_path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Parse the raw XML `download_hydrograph.py` saves into
    (elapsed_seconds, stage_m), elapsed_seconds measured from the earliest
    reading. Rows with an empty `<Nivel />` (observed rarely in the real feed)
    are skipped - there is no stage reading to use.
    """
    readings = []
    for row in _read_rows(raw_path):
        nivel_text = row.find("Nivel").text
        if not nivel_text:
            continue
        timestamp = datetime.strptime(row.find("DataHora").text.strip(), "%Y-%m-%d %H:%M:%S")
        readings.append((timestamp, float(nivel_text) / 100.0))  # cm -> m

    readings.sort(key=lambda reading: reading[0])  # feed arrives in descending time order
    start = readings[0][0]
    elapsed_seconds = np.array([(timestamp - start).total_seconds() for timestamp, _ in readings])
    stage_m = np.array([stage for _, stage in readings])
    return elapsed_seconds, stage_m


def find_calibration_pairs(raw_path: Path) -> list[tuple[float, float]]:
    """Extract real (stage_m, discharge_m3s) pairs from rows where ANA's own
    `Vazao` field is present alongside `Nivel` - this station's real,
    already-computed discharge for this event, used as the rating curve by
    `build_hydrograph` instead of an independently sourced one.
    """
    pairs: dict[float, list[float]] = {}
    for row in _read_rows(raw_path):
        nivel_text = row.find("Nivel").text
        vazao_text = row.find("Vazao").text
        if not nivel_text or not vazao_text:
            continue
        stage_m = float(nivel_text) / 100.0
        pairs.setdefault(stage_m, []).append(float(vazao_text))

    if len(pairs) < 2:
        raise ValueError(
            f"found only {len(pairs)} distinct stage/discharge pair(s) with a real "
            "Vazao reading in this file - need at least 2 to build a rating curve"
        )

    # Average duplicate stage readings so the curve stays strictly increasing
    # (required for np.interp).
    return sorted((stage, sum(values) / len(values)) for stage, values in pairs.items())


def stage_to_discharge(stage_m: np.ndarray, rating_curve: list[tuple[float, float]]) -> np.ndarray:
    """Piecewise-linear interpolation of stage (m) to discharge (m3/s) via
    `rating_curve` breakpoints. A stage outside the curve's calibrated range is
    clipped to the nearest endpoint's discharge (flat extrapolation - `np.interp`'s
    default behavior outside its domain) rather than raising: a documented
    simplification, the same kind of pragmatic engineering choice as
    `simulation.engine`'s `_NO_FLOW_FALLBACK_DT_SECONDS`, made necessary because
    real field-measured discharge (`find_calibration_pairs`) doesn't necessarily
    span this event's full observed stage range.
    """
    stages = np.array([p[0] for p in rating_curve])
    discharges = np.array([p[1] for p in rating_curve])
    return np.interp(stage_m, stages, discharges)


@dataclass
class Hydrograph:
    """A discharge time series, queryable at arbitrary elapsed times."""

    elapsed_seconds: np.ndarray
    discharge_m3s: np.ndarray

    @property
    def duration_seconds(self) -> float:
        return float(self.elapsed_seconds[-1])

    def discharge_at(self, elapsed_seconds: float) -> float:
        if not (0 <= elapsed_seconds <= self.duration_seconds):
            raise ValueError(
                f"elapsed_seconds {elapsed_seconds} is outside the hydrograph's "
                f"recorded range [0, {self.duration_seconds}]"
            )
        return float(np.interp(elapsed_seconds, self.elapsed_seconds, self.discharge_m3s))


def build_hydrograph(raw_path: Path = settings.HYDROGRAPH_RAW_PATH) -> Hydrograph:
    """Run the full raw-XML -> parse -> rating-curve -> Hydrograph pipeline."""
    elapsed_seconds, stage_m = load_raw_stage_series(raw_path)
    rating_curve = find_calibration_pairs(raw_path)
    discharge_m3s = stage_to_discharge(stage_m, rating_curve)
    return Hydrograph(elapsed_seconds=elapsed_seconds, discharge_m3s=discharge_m3s)
```

**Sanity-check with the real downloaded file before moving on** (not a unit test — the tests above
use synthetic fixtures): run
`.venv/bin/python -c "from ingestion.hydrograph import build_hydrograph; h = build_hydrograph(); print('duration_s=', h.duration_seconds); print('peak discharge m3s=', max(h.discharge_m3s)); print('discharge at start=', h.discharge_at(0.0))"`
from `backend/`, and confirm the peak discharge is a physically plausible Taquari-basin flood value
(thousands of m³/s, not near-zero or absurdly large — Task 1's report noted an observed `Vazao` of
`13774.62` near the event's peak, so the derived series' max should be in that neighborhood, not
wildly different).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_hydrograph.py -v`
Expected: PASS (all 7 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/ingestion/hydrograph.py backend/tests/test_hydrograph.py
git commit -m "feat: parse ANA gauge stage record into a queryable discharge hydrograph"
```

---

### Task 3: Boundary inflow mask and discharge-to-inflow conversion

**Files:**
- Modify: `backend/ingestion/hydrograph.py`
- Modify: `backend/config/settings.py` (`HYDROGRAPH_INFLOW_EDGE`, if Step 1 below finds it wrong)
- Modify: `backend/tests/test_hydrograph.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `find_boundary_inflow_mask(Z, edge, margin_m=2.0) -> np.ndarray` (boolean mask, same
  shape as `Z`), `discharge_to_inflow(discharge_m3s, dt_seconds, mask, cell_area_m2) -> np.ndarray`
  (float array, same shape as `mask`) — both consumed by Task 4's `api/routers/simulations.py`.

- [ ] **Step 1: Determine the real upstream edge**

Run this against the real processed DEM (regenerate it first if `data/processed/lajeado_estrela_z.tif`
doesn't exist locally: `cd backend && .venv/bin/python -c "from ingestion.dem import build_elevation_matrix; build_elevation_matrix()"`):

```bash
cd backend && .venv/bin/python -c "
import rasterio
with rasterio.open('../data/processed/lajeado_estrela_z.tif') as src:
    z = src.read(1)
for edge, strip in [('north', z[0, :]), ('south', z[-1, :]), ('west', z[:, 0]), ('east', z[:, -1])]:
    print(edge, strip.min())
"
```

The edge with the **highest** minimum elevation is upstream (water flows downhill along the
channel toward the opposite edge). If this disagrees with `settings.HYDROGRAPH_INFLOW_EDGE`'s
current value (`"south"`, an unverified starting assumption from Task 1), update it now.

- [ ] **Step 2: Write the failing tests**

Add to `backend/tests/test_hydrograph.py`:

```python
from ingestion.hydrograph import discharge_to_inflow, find_boundary_inflow_mask


def test_find_boundary_inflow_mask_locates_channel_on_given_edge():
    # A 5x5 synthetic terrain: the north edge has a clear low notch (the channel)
    # at columns 2-3, everywhere else is much higher.
    Z = np.full((5, 5), 100.0)
    Z[0, 2:4] = 10.0

    mask = find_boundary_inflow_mask(Z, edge="north")

    expected = np.zeros((5, 5), dtype=bool)
    expected[0, 2:4] = True
    assert np.array_equal(mask, expected)


def test_find_boundary_inflow_mask_rejects_invalid_edge():
    Z = np.full((5, 5), 100.0)

    with pytest.raises(ValueError, match="edge"):
        find_boundary_inflow_mask(Z, edge="northwest")


def test_discharge_to_inflow_splits_volume_uniformly_across_mask():
    mask = np.array([[True, False, True], [False, False, False], [False, False, False]])

    inflow = discharge_to_inflow(discharge_m3s=9.0, dt_seconds=100.0, mask=mask, cell_area_m2=900.0)

    # total volume = 9.0 m3/s * 100s = 900 m3; / 900 m2 cell area = 1.0 depth-unit
    # total, split evenly across the 2 masked cells.
    assert inflow[mask].tolist() == pytest.approx([0.5, 0.5])
    assert inflow[~mask].tolist() == pytest.approx([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])


def test_discharge_to_inflow_rejects_empty_mask():
    mask = np.zeros((3, 3), dtype=bool)

    with pytest.raises(ValueError, match="mask"):
        discharge_to_inflow(discharge_m3s=9.0, dt_seconds=100.0, mask=mask, cell_area_m2=900.0)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_hydrograph.py -v`
Expected: FAIL (`find_boundary_inflow_mask`/`discharge_to_inflow` not defined).

- [ ] **Step 4: Write the implementation**

Add to `backend/ingestion/hydrograph.py`:

```python
# Channel cells on a boundary edge are identified as those within this many
# meters of that edge's minimum elevation - wide enough to capture the real
# channel's width (a few cells), not just its single lowest pixel.
_CHANNEL_ELEVATION_MARGIN_METERS = 2.0


def find_boundary_inflow_mask(
    Z: np.ndarray,
    edge: str,
    margin_m: float = _CHANNEL_ELEVATION_MARGIN_METERS,
) -> np.ndarray:
    """Boolean mask, same shape as `Z`, marking the river-channel cells on one ROI
    boundary `edge` ("north"/"south"/"east"/"west") - where upstream inflow should
    enter, found from the real terrain rather than the gauge's literal coordinates
    (which sit inside the ROI, not on a boundary).
    """
    edges = {
        "north": Z[0, :],
        "south": Z[-1, :],
        "west": Z[:, 0],
        "east": Z[:, -1],
    }
    if edge not in edges:
        raise ValueError(f"edge must be one of {sorted(edges)}, got {edge!r}")

    strip = edges[edge]
    channel = strip <= strip.min() + margin_m
    if not channel.any():
        raise ValueError(f"no channel cells found on edge {edge!r}")

    mask = np.zeros_like(Z, dtype=bool)
    if edge == "north":
        mask[0, :] = channel
    elif edge == "south":
        mask[-1, :] = channel
    elif edge == "west":
        mask[:, 0] = channel
    else:
        mask[:, -1] = channel
    return mask


def discharge_to_inflow(
    discharge_m3s: float,
    dt_seconds: float,
    mask: np.ndarray,
    cell_area_m2: float,
) -> np.ndarray:
    """Convert a discharge (m3/s) sustained over `dt_seconds` into the per-cell
    depth-increment array `simulation.engine.step`'s `inflow` parameter expects,
    split uniformly across `mask`'s True cells.

    Uniform split, not width- or depth-weighted: `mask` is already scoped to the
    channel's real cells (see `find_boundary_inflow_mask`), and depth-weighting
    would need an assumed channel cross-section shape this project has no data to
    justify. `cell_area_m2` converts real m3 into the same depth-summed unit
    convention `H`/`step()`'s `inflow` already use (this project does not track
    true physical m3 elsewhere either - see `docs/project-plan.md`).
    """
    if not mask.any():
        raise ValueError("mask has no True cells to inject inflow into")

    total_volume_m3 = discharge_m3s * dt_seconds
    total_depth_units = total_volume_m3 / cell_area_m2

    inflow = np.zeros(mask.shape)
    inflow[mask] = total_depth_units / mask.sum()
    return inflow
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_hydrograph.py -v`
Expected: PASS (all 11 tests — 7 from Task 2 + 4 new here).

- [ ] **Step 6: Commit**

```bash
git add backend/ingestion/hydrograph.py backend/tests/test_hydrograph.py backend/config/settings.py
git commit -m "feat: locate boundary inflow channel cells and convert discharge to per-cell inflow"
```

---

### Task 4: Wire gauge-driven mode through the API

**Files:**
- Modify: `backend/api/state.py`
- Modify: `backend/api/main.py`
- Modify: `backend/api/routers/simulations.py`
- Modify: `backend/tests/test_api.py`

**Interfaces:**
- Consumes: `ingestion.hydrograph.Hydrograph`, `build_hydrograph`, `find_boundary_inflow_mask`,
  `discharge_to_inflow` (Tasks 2-3); `simulation.engine.compute_stable_dt` (already exists).
- Produces: `SimulationParams.mode: Literal["seeded_pool", "gauge_driven"]`; WebSocket frames for
  gauge-driven runs gain `elapsed_time: float` and `cumulative_inflow: float` fields — consumed by
  Task 5's frontend types. `POST /simulations` returns `503` if `mode="gauge_driven"` is requested
  before the hydrograph has been downloaded/loaded (per the spec's error-handling section — this
  must not take down `seeded_pool` requests too).

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_api.py` (after the existing imports/fixtures):

```python
from ingestion.hydrograph import Hydrograph
from api.routers.simulations import get_hydrograph, get_inflow_mask

TEST_HYDROGRAPH = Hydrograph(elapsed_seconds=np.array([0.0, 10.0]), discharge_m3s=np.array([1.0, 1.0]))
TEST_INFLOW_MASK = np.array([[False, True, False], [False, False, False], [False, False, False]])

app.dependency_overrides[get_hydrograph] = lambda: TEST_HYDROGRAPH
app.dependency_overrides[get_inflow_mask] = lambda: TEST_INFLOW_MASK


def test_create_simulation_rejects_steps_with_gauge_driven_mode():
    response = client.post("/simulations", json={"mode": "gauge_driven", "steps": 5, "frame_interval": 1})

    assert response.status_code == 422


def test_create_simulation_rejects_missing_steps_with_seeded_pool_mode():
    response = client.post("/simulations", json={"mode": "seeded_pool", "frame_interval": 1})

    assert response.status_code == 422


def test_stream_simulation_gauge_driven_sends_elapsed_time_and_terminates_at_hydrograph_duration():
    run_id = client.post("/simulations", json={"mode": "gauge_driven", "frame_interval": 1}).json()["run_id"]

    with client.websocket_connect(f"/simulations/{run_id}/stream") as websocket:
        frame = websocket.receive_json()
        done = websocket.receive_json()

    assert frame["elapsed_time"] == pytest.approx(10.0)
    assert frame["cumulative_inflow"] > 0.0
    assert frame["volume"] == pytest.approx(frame["cumulative_inflow"])
    assert done == {"done": True}


def test_create_simulation_rejects_gauge_driven_when_hydrograph_not_loaded():
    app.dependency_overrides[get_hydrograph] = lambda: None
    try:
        response = client.post("/simulations", json={"mode": "gauge_driven", "frame_interval": 1})
        assert response.status_code == 503
    finally:
        app.dependency_overrides[get_hydrograph] = lambda: TEST_HYDROGRAPH
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_api.py -v`
Expected: FAIL (`get_hydrograph`/`get_inflow_mask` don't exist; `mode` field not recognized so the
validation tests fail differently than expected, e.g. 200 instead of 422/503).

- [ ] **Step 3: Add the new state holders and dependencies**

Modify `backend/api/state.py`:

```python
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
```

- [ ] **Step 4: Load the hydrograph and mask at startup**

Modify `backend/api/main.py`:

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api import state
from api.routers import health, simulations
from config.settings import CORS_ALLOWED_ORIGINS, HYDROGRAPH_INFLOW_EDGE
from ingestion.dem import build_elevation_matrix, get_geographic_bounds
from ingestion.hydrograph import build_hydrograph, find_boundary_inflow_mask
from ingestion.landcover import build_roughness_matrix


@asynccontextmanager
async def lifespan(app: FastAPI):
    state.Z = build_elevation_matrix()
    state.N = build_roughness_matrix()
    state.BOUNDS = get_geographic_bounds()
    # Loaded best-effort, not required for the app to start: gauge-driven mode is
    # additive to the existing seeded-pool mode (see the spec's "Run modes"
    # decision), so a missing/not-yet-downloaded hydrograph file must not break
    # seeded_pool requests too. `create_simulation` below rejects gauge_driven
    # requests with a clear 4xx instead if this stayed None.
    try:
        state.HYDROGRAPH = build_hydrograph()
        state.INFLOW_MASK = find_boundary_inflow_mask(state.Z, HYDROGRAPH_INFLOW_EDGE)
    except FileNotFoundError:
        state.HYDROGRAPH = None
        state.INFLOW_MASK = None
    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health.router)
app.include_router(simulations.router)
```

- [ ] **Step 5: Add `mode` to `SimulationParams` and branch the WebSocket loop**

Replace the full contents of `backend/api/routers/simulations.py`:

```python
"""REST + WebSocket routes for running the CA flood simulation.

Serves the real Lajeado/Estrela grid only (loaded once at startup, see
`api/state.py`) - no synthetic-grid option here, since `api/` may only depend
on `config/`, `ingestion/`, `simulation/`, `validation/` per
`docs/ARCHITECTURE.md` (never `examples/`, which nothing else imports), and by
this roadmap step there's already a real, ingested dataset worth serving.

A run is created via `POST /simulations` (validated parameters, no simulation
work happens yet) and consumed exactly once via
`WS /simulations/{run_id}/stream`. Two modes: `"seeded_pool"` (closed system, a
single water pool seeded at the terrain's lowest point - unchanged since step 5)
and `"gauge_driven"` (open system, driven by the real May 2024 gauge hydrograph
via `simulation.engine`'s `inflow`/`compute_stable_dt`, roadmap step 9). There's
no persistence layer for this project (see docs/project-plan.md), so a pending
run only exists in an in-memory dict between those two calls.
"""

import uuid
from typing import Literal

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field, model_validator

from api.state import get_bounds, get_hydrograph, get_inflow_mask, get_roughness, get_terrain
from config.settings import TARGET_RESOLUTION_METERS
from ingestion.hydrograph import Hydrograph, discharge_to_inflow
from simulation.engine import compute_stable_dt, seed_pool_at_lowest_point, step

router = APIRouter()

SEED_VOLUME = 400.0


class SimulationParams(BaseModel):
    mode: Literal["seeded_pool", "gauge_driven"] = "seeded_pool"
    steps: int | None = Field(default=None, gt=0)
    frame_interval: int = Field(gt=0)
    outflow_fraction: float = Field(default=0.5, gt=0, le=1)

    @model_validator(mode="after")
    def _validate_steps_matches_mode(self) -> "SimulationParams":
        if self.mode == "seeded_pool" and self.steps is None:
            raise ValueError("steps is required when mode is 'seeded_pool'")
        if self.mode == "gauge_driven" and self.steps is not None:
            raise ValueError(
                "steps must not be given when mode is 'gauge_driven' - the gauge "
                "hydrograph's own duration determines run length"
            )
        return self


class Bounds(BaseModel):
    west: float
    south: float
    east: float
    north: float


class SimulationCreated(BaseModel):
    run_id: str
    grid_shape: tuple[int, int]
    bounds: Bounds


_pending_runs: dict[str, SimulationParams] = {}


@router.post("/simulations", response_model=SimulationCreated)
def create_simulation(
    params: SimulationParams,
    Z: np.ndarray = Depends(get_terrain),
    bounds: tuple[float, float, float, float] = Depends(get_bounds),
    hydrograph: Hydrograph | None = Depends(get_hydrograph),
) -> SimulationCreated:
    if params.mode == "gauge_driven" and hydrograph is None:
        raise HTTPException(
            status_code=503,
            detail="gauge-driven data not loaded - run scripts/download_hydrograph.py and restart the API",
        )

    run_id = str(uuid.uuid4())
    _pending_runs[run_id] = params
    west, south, east, north = bounds
    return SimulationCreated(
        run_id=run_id,
        grid_shape=Z.shape,
        bounds=Bounds(west=west, south=south, east=east, north=north),
    )


async def _run_seeded_pool(websocket: WebSocket, params: SimulationParams, Z: np.ndarray, N: np.ndarray) -> None:
    H = np.zeros_like(Z)
    seed_pool_at_lowest_point(Z, H, SEED_VOLUME)
    initial_volume = H.sum()

    for t in range(1, params.steps + 1):
        H = step(Z, H, N, outflow_fraction=params.outflow_fraction)
        assert H.min() >= -1e-9, f"negative depth at step {t}: {H.min()}"
        assert abs(H.sum() - initial_volume) < 1e-6, f"volume drifted at step {t}: {H.sum()} vs {initial_volume}"
        if t % params.frame_interval == 0 or t == params.steps:
            await websocket.send_json({"step": t, "depth": H.tolist(), "volume": float(H.sum())})


async def _run_gauge_driven(
    websocket: WebSocket,
    params: SimulationParams,
    Z: np.ndarray,
    N: np.ndarray,
    hydrograph: Hydrograph,
    inflow_mask: np.ndarray,
) -> None:
    H = np.zeros_like(Z)
    cell_area_m2 = TARGET_RESOLUTION_METERS ** 2
    elapsed_time = 0.0
    cumulative_inflow = 0.0
    t = 0

    while elapsed_time < hydrograph.duration_seconds:
        dt = compute_stable_dt(Z, H, N, TARGET_RESOLUTION_METERS)
        # Clip so the final iteration lands exactly on the hydrograph's end, never
        # past it - Hydrograph.discharge_at raises outside its recorded range.
        dt = min(dt, hydrograph.duration_seconds - elapsed_time)

        discharge = hydrograph.discharge_at(elapsed_time)
        inflow = discharge_to_inflow(discharge, dt, inflow_mask, cell_area_m2)

        H = step(Z, H, N, outflow_fraction=params.outflow_fraction, inflow=inflow)
        elapsed_time += dt
        cumulative_inflow += inflow.sum()
        t += 1

        assert H.min() >= -1e-9, f"negative depth at step {t}: {H.min()}"
        assert abs(H.sum() - cumulative_inflow) < 1e-6, f"volume drifted at step {t}: {H.sum()} vs {cumulative_inflow}"

        if t % params.frame_interval == 0 or elapsed_time >= hydrograph.duration_seconds:
            await websocket.send_json(
                {
                    "step": t,
                    "depth": H.tolist(),
                    "volume": float(H.sum()),
                    "elapsed_time": elapsed_time,
                    "cumulative_inflow": float(cumulative_inflow),
                }
            )


@router.websocket("/simulations/{run_id}/stream")
async def stream_simulation(
    websocket: WebSocket,
    run_id: str,
    Z: np.ndarray = Depends(get_terrain),
    N: np.ndarray = Depends(get_roughness),
    hydrograph: Hydrograph | None = Depends(get_hydrograph),
    inflow_mask: np.ndarray | None = Depends(get_inflow_mask),
) -> None:
    # Popped rather than just read: a run can only be streamed once, matching
    # the "no persistence layer" decision - reconnecting with the same run_id
    # isn't a supported resume mechanism.
    params = _pending_runs.pop(run_id, None)
    if params is None:
        await websocket.close(code=4004, reason="unknown run_id")
        return

    await websocket.accept()

    try:
        if params.mode == "seeded_pool":
            await _run_seeded_pool(websocket, params, Z, N)
        else:
            await _run_gauge_driven(websocket, params, Z, N, hydrograph, inflow_mask)
        await websocket.send_json({"done": True})
    except WebSocketDisconnect:
        pass
    finally:
        await websocket.close()
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/ -v`
Expected: PASS, full suite (35 existing + 11 from Tasks 2-3 + 4 new here = 50).

- [ ] **Step 7: Commit**

```bash
git add backend/api/state.py backend/api/main.py backend/api/routers/simulations.py backend/tests/test_api.py
git commit -m "feat: add gauge-driven simulation mode to the API"
```

---

### Task 5: Frontend mode toggle and elapsed-time display

**Files:**
- Modify: `frontend/src/types/simulation.ts`
- Modify: `frontend/src/components/ConfigPanel.tsx`
- Modify: `frontend/src/hooks/useSimulationRun.ts`

**Interfaces:**
- Consumes: the API's `mode` field and the two new optional frame fields from Task 4.
- Produces: nothing further consumed by other tasks (this is the last task).

- [ ] **Step 1: Extend the TypeScript types**

Modify `frontend/src/types/simulation.ts`:

```typescript
export interface SimulationParams {
  mode?: 'seeded_pool' | 'gauge_driven'
  steps?: number
  frame_interval: number
  outflow_fraction?: number
}

export interface Bounds {
  west: number
  south: number
  east: number
  north: number
}

export interface SimulationCreated {
  run_id: string
  grid_shape: [number, number]
  bounds: Bounds
}

export interface SimulationFrame {
  step: number
  depth: number[][]
  volume: number
  elapsed_time?: number
  cumulative_inflow?: number
}

export interface SimulationDone {
  done: true
}

export type StreamMessage = SimulationFrame | SimulationDone

export function isDone(message: StreamMessage): message is SimulationDone {
  return (message as SimulationDone).done === true
}
```

- [ ] **Step 2: Add the mode toggle to `ConfigPanel`**

Modify `frontend/src/components/ConfigPanel.tsx`:

```tsx
import { useState } from 'react'
import type { FormEvent } from 'react'
import type { SimulationParams } from '../types/simulation'
import type { SimulationStatus } from '../hooks/useSimulationRun'

interface ConfigPanelProps {
  status: SimulationStatus
  onStart: (params: SimulationParams) => void
}

export function ConfigPanel({ status, onStart }: ConfigPanelProps) {
  const [mode, setMode] = useState<'seeded_pool' | 'gauge_driven'>('seeded_pool')
  const [steps, setSteps] = useState(200)
  const [frameInterval, setFrameInterval] = useState(5)
  const [outflowFraction, setOutflowFraction] = useState(0.5)

  const busy = status === 'starting' || status === 'streaming'

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault()
    const params: SimulationParams = {
      mode,
      frame_interval: frameInterval,
      outflow_fraction: outflowFraction,
      ...(mode === 'seeded_pool' ? { steps } : {}),
    }
    onStart(params)
  }

  return (
    <form onSubmit={handleSubmit} className="flex h-full flex-col gap-4 border-r border-gray-200 bg-gray-50 p-4">
      <h1 className="text-lg font-semibold text-gray-900">Terranova</h1>
      <p className="text-sm text-gray-500">Vale do Taquari flood simulation</p>

      <fieldset className="flex flex-col gap-1 text-sm text-gray-700">
        <legend className="mb-1">Run mode</legend>
        <label className="flex items-center gap-2">
          <input
            type="radio"
            name="mode"
            checked={mode === 'seeded_pool'}
            disabled={busy}
            onChange={() => setMode('seeded_pool')}
          />
          Synthetic seeded pool
        </label>
        <label className="flex items-center gap-2">
          <input
            type="radio"
            name="mode"
            checked={mode === 'gauge_driven'}
            disabled={busy}
            onChange={() => setMode('gauge_driven')}
          />
          Real May 2024 event (gauge-driven)
        </label>
      </fieldset>

      {mode === 'seeded_pool' && (
        <label className="flex flex-col gap-1 text-sm text-gray-700">
          Steps
          <input
            type="number"
            min={1}
            value={steps}
            disabled={busy}
            onChange={(e) => setSteps(Number(e.target.value))}
            className="rounded border border-gray-300 px-2 py-1 disabled:opacity-50"
          />
        </label>
      )}

      <label className="flex flex-col gap-1 text-sm text-gray-700">
        Frame interval
        <input
          type="number"
          min={1}
          value={frameInterval}
          disabled={busy}
          onChange={(e) => setFrameInterval(Number(e.target.value))}
          className="rounded border border-gray-300 px-2 py-1 disabled:opacity-50"
        />
      </label>

      <label className="flex flex-col gap-1 text-sm text-gray-700">
        Outflow fraction
        <input
          type="number"
          min={0.01}
          max={1}
          step={0.01}
          value={outflowFraction}
          disabled={busy}
          onChange={(e) => setOutflowFraction(Number(e.target.value))}
          className="rounded border border-gray-300 px-2 py-1 disabled:opacity-50"
        />
      </label>

      <button
        type="submit"
        disabled={busy}
        className="mt-2 rounded bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
      >
        {busy ? 'Running…' : 'Start simulation'}
      </button>
    </form>
  )
}
```

- [ ] **Step 3: Show elapsed time in the log line**

Modify `frontend/src/hooks/useSimulationRun.ts`, replacing the `onFrame` callback body:

```typescript
onFrame: (frame) => {
  setLatestFrame(frame)
  const elapsedNote =
    frame.elapsed_time !== undefined ? `, elapsed=${(frame.elapsed_time / 60).toFixed(1)}min` : ''
  setLog((prev) => [...prev, `step ${frame.step}: volume=${frame.volume.toFixed(4)}${elapsedNote}`])
},
```

(No changes needed to `LogPanel.tsx` — it already renders whatever strings `log` contains.)

- [ ] **Step 4: Manually verify in the browser**

Run: `cd backend && .venv/bin/uvicorn api.main:app --reload` in one terminal,
`cd frontend && npm run dev` in another.

Open the printed `localhost:5173` URL and check:
1. "Synthetic seeded pool" is selected by default; clicking "Start simulation" behaves exactly as
   before this plan (regression check — steps/frame_interval/outflow_fraction all still work,
   volume stays flat/conserved).
2. Selecting "Real May 2024 event (gauge-driven)" hides the Steps field. Clicking "Start
   simulation" starts a run; the log shows volume rising over time along with an `elapsed=` note in
   minutes; the run eventually reaches `Done` without a frozen UI or an uncaught error banner.
3. Force-stop the backend mid-gauge-driven-run and confirm the existing disconnect-handling error
   banner still appears (regression check for `api/stream.ts`'s existing behavior — unmodified by
   this plan, but worth confirming the new mode doesn't break it).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/simulation.ts frontend/src/components/ConfigPanel.tsx frontend/src/hooks/useSimulationRun.ts
git commit -m "feat(frontend): add gauge-driven run mode toggle and elapsed-time log"
```

---

## After this plan

Update `docs/project-plan.md`'s "Current status" section to mark step 9 done, following the same
detailed-writeup style as steps 1-8's entries (what was built, key decisions, what was verified,
explicit scope notes for anything deferred) — this is a documentation step for whoever executes
this plan to do last, not a coding task, so it isn't broken out as a numbered task above.
