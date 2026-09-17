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

`find_boundary_inflow_mask` and `discharge_to_inflow` turn a `Hydrograph`
discharge value into the per-cell `inflow` array `simulation.engine.step`
expects: the former locates the river-channel cells on one real ROI boundary
edge from the terrain `Z` itself (the gauge's own coordinates sit inside the
ROI, not on a boundary), the latter splits a discharge over `dt_seconds`
uniformly across those cells.

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
