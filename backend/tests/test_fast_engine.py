import numpy as np
import pytest

from config import settings
from simulation.fast_engine import CONVEYING, DRY, EXITING, INUNDATED, classify_steady_flood


def _south_outlet(Z: np.ndarray, cols: list[int], drop: float) -> np.ndarray:
    """Padded wall-everywhere boundary with an outlet below the given south-edge columns."""
    boundary = np.pad(Z, 1, constant_values=np.inf)
    for c in cols:
        boundary[-1, c + 1] = Z[-1, c] - drop
    return boundary


def _v_valley(rows=12, cols=9, dx=10.0, bed_slope=0.01, bank_step=1.0):
    """A single-cell-wide channel down the middle column, falling `bed_slope`
    per meter southward, with banks rising `bank_step` m per column away from
    it - so no bank cell is ever downstream of the channel."""
    mid = cols // 2
    r, c = np.mgrid[0:rows, 0:cols].astype(float)
    Z = (rows - 1 - r) * bed_slope * dx + np.abs(c - mid) * bank_step + 5.0
    N = np.full((rows, cols), 0.05)
    inflow = np.zeros((rows, cols), dtype=bool)
    inflow[0, mid] = True
    boundary = _south_outlet(Z, [mid], drop=bed_slope * dx)
    return Z, N, dx, inflow, boundary, mid


def test_discharge_continuity_with_outlet():
    """All routed discharge leaves through the outlet - this engine's analogue
    of the temporal engine's exact mass conservation."""
    rows, cols = 15, 15
    r, c = np.mgrid[0:rows, 0:cols].astype(float)
    Z = (rows - 1 - r) * 0.5 + 0.1 * np.abs(c - cols // 2)
    N = np.full((rows, cols), 0.04)
    inflow = np.zeros((rows, cols), dtype=bool)
    inflow[0, 6:9] = True

    result = classify_steady_flood(Z, N, 30.0, 500.0, inflow, boundary_elevation=_south_outlet(Z, [6, 7, 8], 1.0))

    assert result.retained_m3s == 0.0
    assert result.outflow_m3s == pytest.approx(500.0, rel=1e-12)


def test_walled_domain_retains_all_discharge():
    """With no outlet there is nowhere for flow to go: all of it is reported
    as retained, never silently lost."""
    Z, N, dx, inflow, _, _ = _v_valley()
    result = classify_steady_flood(Z, N, dx, 80.0, inflow)
    assert result.outflow_m3s == 0.0
    assert result.retained_m3s == pytest.approx(80.0, rel=1e-12)


def test_conveying_depth_is_manning_normal_depth():
    """Hand-computed Manning normal depth, h = (Q n / (w sqrt(S)))^(3/5) with
    w = dx, for a single-cell channel of known uniform bed slope."""
    Z, N, dx, inflow, boundary, mid = _v_valley(bed_slope=0.01)
    Q, n, S = 100.0, 0.05, 0.01
    expected = (Q * n / (dx * np.sqrt(S))) ** 0.6

    result = classify_steady_flood(Z, N, dx, Q, inflow, boundary_elevation=boundary)

    for row in range(Z.shape[0]):
        assert result.discharge[row, mid] == pytest.approx(Q, rel=1e-12)
        assert result.depth[row, mid] == pytest.approx(expected, rel=1e-12)


def test_manning_roughness_steers_discharge_toward_smoother_neighbor():
    """Two downstream neighbors at equal slope and distance but 4:1 roughness
    receive a 4:1 discharge split (weights sqrt(S)/n_dest, the same
    convention as engine._single_update)."""
    Z = np.full((3, 5), 20.0)
    Z[1, 2] = 10.0  # source
    Z[1, 1] = Z[1, 3] = 5.0  # equal drop, both orthogonal
    Z[1, 0] = Z[1, 4] = 4.0  # paths on to the west/east outlets
    N = np.full((3, 5), 0.05)
    N[1, 1], N[1, 3] = 0.02, 0.08
    inflow = np.zeros((3, 5), dtype=bool)
    inflow[1, 2] = True
    boundary = np.pad(Z, 1, constant_values=np.inf)
    boundary[2, 0] = boundary[2, 6] = 3.0  # outside (1,0) and (1,4)

    result = classify_steady_flood(Z, N, 10.0, 50.0, inflow, boundary_elevation=boundary)

    assert result.discharge[1, 1] / result.discharge[1, 3] == pytest.approx(4.0, rel=1e-12)
    assert result.outflow_m3s == pytest.approx(50.0, rel=1e-12)


def test_four_states_on_a_v_valley():
    """Channel cells convey (the last one exits); banks below the channel's
    water surface are inundated to exactly that surface; higher banks stay dry."""
    Z, N, dx, inflow, boundary, mid = _v_valley(bank_step=1.0)
    result = classify_steady_flood(Z, N, dx, 100.0, inflow, boundary_elevation=boundary)
    channel_depth = (100.0 * 0.05 / (dx * np.sqrt(0.01))) ** 0.6  # ~2.63 m

    row = 5
    assert result.state[row, mid] == CONVEYING
    assert result.state[-1, mid] == EXITING
    for offset in (1, 2):  # banks 1 m and 2 m above the bed: below the ~2.63 m surface
        for c in (mid - offset, mid + offset):
            assert result.state[row, c] == INUNDATED
            assert result.depth[row, c] == pytest.approx(channel_depth - offset, rel=1e-12)
            assert result.wse[row, c] == pytest.approx(result.wse[row, mid], rel=1e-12)
    for c in (mid - 3, mid + 3, 0, Z.shape[1] - 1):  # 3 m+ above the bed: above the surface
        assert result.state[row, c] == DRY
        assert result.depth[row, c] == 0.0


def test_larger_discharge_floods_a_superset():
    Z, N, dx, inflow, boundary, _ = _v_valley(bank_step=0.5)
    small = classify_steady_flood(Z, N, dx, 20.0, inflow, boundary_elevation=boundary)
    large = classify_steady_flood(Z, N, dx, 200.0, inflow, boundary_elevation=boundary)

    assert np.all(large.flooded[small.flooded])
    assert large.flooded.sum() > small.flooded.sum()
    assert np.all(large.depth >= small.depth - 1e-12)


def test_flat_terrain_terminates_and_conserves_discharge():
    """Perfectly flat terrain has no downhill neighbor anywhere; the flood
    visitation order must still route everything to the outlet."""
    Z = np.zeros((8, 8))
    N = np.full((8, 8), 0.03)
    inflow = np.zeros((8, 8), dtype=bool)
    inflow[0, 3] = True
    result = classify_steady_flood(Z, N, 30.0, 40.0, inflow, boundary_elevation=_south_outlet(Z, [5], drop=1.0))
    assert result.retained_m3s == 0.0
    assert result.outflow_m3s == pytest.approx(40.0, rel=1e-12)


def test_depression_on_flow_path_is_filled_to_its_spill_level():
    """At steady state a pit on the flow path must be full before water moves
    on: its water surface is at least the spill level, not its own bed."""
    Z, N, dx, inflow, boundary, mid = _v_valley()
    spill = Z[5, mid]
    Z = Z.copy()
    Z[6, mid] = spill - 3.0  # a 3 m pit, lower than the next cell downstream
    boundary = _south_outlet(Z, [mid], drop=0.1)
    result = classify_steady_flood(Z, N, dx, 100.0, inflow, boundary_elevation=boundary)
    spill_level = Z[7, mid]  # the pit drains over the next cell downstream
    pond_depth = spill_level - Z[6, mid]
    assert result.wse[6, mid] > spill_level
    assert result.depth[6, mid] > pond_depth
    assert result.outflow_m3s == pytest.approx(100.0, rel=1e-12)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"peak_discharge_m3s": -1.0},
        {"dx": 0.0},
        {"N": np.zeros((12, 9))},
        {"inflow_mask": np.zeros((12, 9), dtype=bool)},
        {"boundary_elevation": np.zeros((3, 3))},
    ],
)
def test_rejects_invalid_input(kwargs):
    Z, N, dx, inflow, boundary, _ = _v_valley()
    args = {"Z": Z, "N": N, "dx": dx, "peak_discharge_m3s": 10.0, "inflow_mask": inflow, "boundary_elevation": boundary}
    args.update(kwargs)
    with pytest.raises(ValueError):
        classify_steady_flood(**args)


# The one test in this suite that needs real data: a regression pinning the
# fast mode's first real May 2024 result (docs/tcc-deviations.md section 19),
# so a future change to fast_engine.py that moves it is caught rather than
# silently shifting a documented number. Skipped, not failed, when the raw
# files haven't been downloaded; naive scoring only, so it never needs the
# network (the Estrela-gap correction queries SGB live). Note: like
# examples/validate_may2024.py, building the 90m grid (re)writes
# data/processed/*_90m.tif as a side effect.
_RAW_FILES = [settings.DEM_RAW_PATH, settings.LANDCOVER_RAW_PATH, settings.HYDROGRAPH_RAW_PATH, settings.FLOOD_EXTENT_RAW_PATH]


@pytest.mark.skipif(not all(p.exists() for p in _RAW_FILES), reason="real May 2024 raw data not downloaded")
def test_may2024_fast_mode_regression():
    from ingestion.dem import build_elevation_matrix
    from ingestion.flood_extent import build_observed_flood_mask
    from ingestion.hydrograph import build_hydrograph, find_boundary_inflow_mask, find_boundary_outlet, load_raw_stage_series
    from ingestion.landcover import build_roughness_matrix
    from validation.metrics import confusion_counts, csi

    Z = build_elevation_matrix(processed_path=settings.DEM_VALIDATION_PROCESSED_PATH,
                               resolution=settings.VALIDATION_RESOLUTION_METERS)
    N = build_roughness_matrix(reference_path=settings.DEM_VALIDATION_PROCESSED_PATH,
                               processed_path=settings.LANDCOVER_VALIDATION_PROCESSED_PATH)
    elapsed, stage = load_raw_stage_series(settings.HYDROGRAPH_RAW_PATH)
    peak_q = build_hydrograph().discharge_at(float(elapsed[int(np.argmax(stage))]))
    inflow = find_boundary_inflow_mask(Z, settings.HYDROGRAPH_INFLOW_EDGE)
    boundary_elevation, boundary_roughness = find_boundary_outlet(Z, N, settings.HYDROGRAPH_OUTLET_EDGE)

    result = classify_steady_flood(Z, N, settings.VALIDATION_RESOLUTION_METERS, peak_q, inflow,
                                   boundary_elevation=boundary_elevation, boundary_roughness=boundary_roughness)
    observed = build_observed_flood_mask(reference_path=settings.DEM_VALIDATION_PROCESSED_PATH)

    assert result.retained_m3s == 0.0
    assert result.outflow_m3s == pytest.approx(peak_q, rel=1e-9)
    assert confusion_counts(result.flooded, observed) == (731, 2109, 100)
    assert csi(result.flooded, observed) == pytest.approx(0.2486, abs=5e-5)
