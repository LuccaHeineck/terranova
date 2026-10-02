import time

import numpy as np
import pytest
from affine import Affine
from fastapi.testclient import TestClient
from rasterio.warp import transform as warp_transform
from starlette.websockets import WebSocketDisconnect

from api.main import app
from api.routers.simulations import get_grids, get_hydrograph
from api.routers.validation import get_validation_reference
from api.state import Grid, ValidationReference
from ingestion.hydrograph import Hydrograph
from simulation.engine import seed_pool_at_lowest_point, step

# Deliberately not using `with TestClient(app) as client:` - that would run
# the app's real lifespan (build_elevation_matrix/build_roughness_matrix),
# which needs the real DEM/land-cover files on disk. Plain instantiation never
# triggers ASGI lifespan events, so combined with the dependency overrides
# below, these tests stay network- and file-free like the rest of the suite.
TEST_Z = np.array([[10.0, 10.0, 10.0], [10.0, 0.0, 10.0], [10.0, 10.0, 10.0]])
TEST_N = np.full((3, 3), 0.05)
TEST_BOUNDS = (-51.99, -29.505, -51.93, -29.455)
TEST_INFLOW_MASK = np.array([[False, True, False], [False, False, False], [False, False, False]])
TEST_HYDROGRAPH = Hydrograph(elapsed_seconds=np.array([0.0, 10.0]), discharge_m3s=np.array([1.0, 1.0]))
# The real 30m grid's georeference (SIRGAS 2000 / UTM 22S, top-left corner near
# Lajeado), so seed-location tests go through a real lat/lon -> UTM reprojection.
TEST_CRS = "EPSG:31982"
TEST_TRANSFORM = Affine(30.0, 0.0, 404043.3, 0.0, -30.0, 6741197.92)


def _grid(
    Z, N=None, inflow_mask=None, boundary_elevation=None, boundary_roughness=None, dx=30.0, bounds=TEST_BOUNDS,
    landcover=None,
):
    """A synthetic stand-in for api.state.Grid. No outlet by default (walled on
    every side, the same as the engines' own default), so tests that need one
    pass it explicitly. Land cover defaults to all Pasture (class 15)."""
    return Grid(
        Z=Z,
        N=np.full(Z.shape, 0.05) if N is None else N,
        landcover=np.full(Z.shape, 15, dtype=np.uint8) if landcover is None else landcover,
        dx=dx,
        bounds=bounds,
        crs=TEST_CRS,
        transform=Affine(dx, 0.0, TEST_TRANSFORM.c, 0.0, -dx, TEST_TRANSFORM.f),
        inflow_mask=TEST_INFLOW_MASK if inflow_mask is None else inflow_mask,
        boundary_elevation=boundary_elevation,
        boundary_roughness=boundary_roughness,
    )


# Different shapes and bounds than the 30m grid, so tests can tell which one a
# request was served from.
TEST_Z_60 = np.full((4, 4), 10.0)
TEST_Z_60[2, 2] = 0.0
TEST_BOUNDS_60 = (-51.985, -29.502, -51.935, -29.458)
TEST_INFLOW_MASK_60 = np.zeros((4, 4), dtype=bool)
TEST_INFLOW_MASK_60[0, 1] = True
TEST_Z_90 = np.array([[10.0, 10.0], [10.0, 0.0]])
TEST_BOUNDS_90 = (-51.98, -29.50, -51.94, -29.46)
TEST_GRIDS = {
    30: _grid(TEST_Z),
    60: _grid(TEST_Z_60, inflow_mask=TEST_INFLOW_MASK_60, dx=60.0, bounds=TEST_BOUNDS_60),
    90: _grid(TEST_Z_90, inflow_mask=np.array([[True, False], [False, False]]), dx=90.0, bounds=TEST_BOUNDS_90),
}

app.dependency_overrides[get_grids] = lambda: TEST_GRIDS
app.dependency_overrides[get_hydrograph] = lambda: TEST_HYDROGRAPH

client = TestClient(app)


def _receive_until_done(websocket) -> list[dict]:
    frames = []
    message = websocket.receive_json()
    while not message.get("done"):
        frames.append(message)
        message = websocket.receive_json()
    return frames


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
    assert frame["cumulative_outflow"] == 0.0  # no outlet configured (TEST_GRIDS is walled)
    assert frame["volume"] == pytest.approx(frame["cumulative_inflow"])
    assert done == {"done": True}


def test_stream_simulation_gauge_driven_with_outlet_loses_volume_through_it():
    # A dedicated sloped terrain (north-high to south-low) and a longer
    # hydrograph, both local to this test: the default single-frame
    # TEST_HYDROGRAPH (a single 10s step) never gives inflow a chance to
    # redistribute anywhere before the run ends (inflow is added *after*
    # redistribution each step - see step()'s docstring), so it could never
    # reach an outlet regardless of terrain. A longer duration forces several
    # real engine steps, enough for water to actually travel downhill to the
    # south-edge outlet.
    sloped_Z = np.array([[10.0, 10.0, 10.0], [5.0, 5.0, 5.0], [0.0, 0.0, 0.0]])
    boundary_elevation = np.pad(sloped_Z, 1, mode="constant", constant_values=np.inf)
    boundary_elevation[-1, 2] = -5.0  # south-edge outlet, below the sloped terrain's own lowest row
    boundary_roughness = np.pad(TEST_N, 1, mode="constant", constant_values=1.0)
    boundary_roughness[-1, 2] = 0.04
    long_hydrograph = Hydrograph(elapsed_seconds=np.array([0.0, 3000.0]), discharge_m3s=np.array([1.0, 1.0]))

    app.dependency_overrides[get_grids] = lambda: {
        30: _grid(sloped_Z, boundary_elevation=boundary_elevation, boundary_roughness=boundary_roughness)
    }
    app.dependency_overrides[get_hydrograph] = lambda: long_hydrograph
    try:
        run_id = client.post("/simulations", json={"mode": "gauge_driven", "frame_interval": 1}).json()["run_id"]

        with client.websocket_connect(f"/simulations/{run_id}/stream") as websocket:
            frames = _receive_until_done(websocket)

        assert frames, "run ended without ever sending a data frame"
        last_frame = frames[-1]
        assert last_frame["cumulative_outflow"] > 0.0, "some volume should have left through the outlet"
        assert last_frame["volume"] == pytest.approx(last_frame["cumulative_inflow"] - last_frame["cumulative_outflow"])
    finally:
        app.dependency_overrides[get_grids] = lambda: TEST_GRIDS
        app.dependency_overrides[get_hydrograph] = lambda: TEST_HYDROGRAPH


def test_create_simulation_rejects_gauge_driven_when_hydrograph_not_loaded():
    app.dependency_overrides[get_hydrograph] = lambda: None
    try:
        response = client.post("/simulations", json={"mode": "gauge_driven", "frame_interval": 1})
        assert response.status_code == 503
    finally:
        app.dependency_overrides[get_hydrograph] = lambda: TEST_HYDROGRAPH


def test_health_still_ok():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_simulation_returns_run_id_and_grid_shape():
    response = client.post("/simulations", json={"steps": 5, "frame_interval": 5})

    assert response.status_code == 200
    body = response.json()
    assert "run_id" in body
    assert body["grid_shape"] == [3, 3]
    assert body["bounds"] == {"west": -51.99, "south": -29.505, "east": -51.93, "north": -29.455}


@pytest.mark.parametrize("params", [{"steps": 0, "frame_interval": 5}, {"steps": 5, "frame_interval": 5, "outflow_fraction": 0.0}])
def test_create_simulation_rejects_invalid_params(params):
    response = client.post("/simulations", json=params)

    assert response.status_code == 422


def test_stream_simulation_sends_frames_then_done():
    run_id = client.post("/simulations", json={"steps": 5, "frame_interval": 5}).json()["run_id"]

    with client.websocket_connect(f"/simulations/{run_id}/stream") as websocket:
        frame = websocket.receive_json()
        done = websocket.receive_json()

    assert frame["step"] == 5
    assert np.array(frame["depth"]).shape == (3, 3)
    assert frame["volume"] == pytest.approx(400.0)
    assert done == {"done": True}


def test_stream_simulation_rejects_unknown_run_id():
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/simulations/does-not-exist/stream"):
            pass


def test_stream_simulation_can_only_be_consumed_once():
    run_id = client.post("/simulations", json={"steps": 5, "frame_interval": 5}).json()["run_id"]

    with client.websocket_connect(f"/simulations/{run_id}/stream") as websocket:
        websocket.receive_json()
        websocket.receive_json()

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/simulations/{run_id}/stream"):
            pass


def test_create_simulation_rejects_missing_frame_interval_with_temporal_modes():
    response = client.post("/simulations", json={"steps": 5})

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("resolution", "shape", "bounds"),
    [
        (60, [4, 4], {"west": -51.985, "south": -29.502, "east": -51.935, "north": -29.458}),
        (90, [2, 2], {"west": -51.98, "south": -29.50, "east": -51.94, "north": -29.46}),
    ],
)
def test_create_simulation_serves_the_requested_resolution(resolution, shape, bounds):
    response = client.post("/simulations", json={"mode": "fast", "resolution": resolution})

    assert response.status_code == 200
    body = response.json()
    assert body["grid_shape"] == shape
    assert body["bounds"] == bounds


def test_create_simulation_rejects_unserved_resolution():
    response = client.post("/simulations", json={"mode": "fast", "resolution": 45})

    assert response.status_code == 422


@pytest.mark.parametrize(
    "extra",
    [
        {"steps": 5},
        {"frame_interval": 1},
        {"outflow_fraction": 0.1},
        {"stop_at_peak": True},
        {"neighborhood": "moore"},
        {"neighborhood": "von_neumann"},
    ],
)
def test_create_simulation_rejects_temporal_params_with_fast_mode(extra):
    response = client.post("/simulations", json={"mode": "fast", **extra})

    assert response.status_code == 422


def test_create_simulation_rejects_fast_when_hydrograph_not_loaded():
    app.dependency_overrides[get_hydrograph] = lambda: None
    try:
        response = client.post("/simulations", json={"mode": "fast"})
        assert response.status_code == 503
    finally:
        app.dependency_overrides[get_hydrograph] = lambda: TEST_HYDROGRAPH


def test_create_simulation_rejects_stop_at_peak_with_seeded_pool_mode():
    response = client.post("/simulations", json={"steps": 5, "frame_interval": 5, "stop_at_peak": True})

    assert response.status_code == 422


def test_stream_simulation_fast_sends_one_frame_then_done():
    # North-high to south-low terrain with a south-edge outlet, so the steady
    # discharge has somewhere to go - continuity is then out + retained == in
    # with a non-zero outflow, not trivially all retained.
    sloped_Z = np.array([[10.0, 10.0, 10.0], [5.0, 5.0, 5.0], [0.0, 0.0, 0.0]])
    boundary_elevation = np.pad(sloped_Z, 1, mode="constant", constant_values=np.inf)
    boundary_elevation[-1, 2] = -5.0
    boundary_roughness = np.pad(TEST_N, 1, mode="constant", constant_values=1.0)
    boundary_roughness[-1, 2] = 0.04
    peaked_hydrograph = Hydrograph(
        elapsed_seconds=np.array([0.0, 100.0, 200.0]), discharge_m3s=np.array([1.0, 50.0, 2.0])
    )

    app.dependency_overrides[get_grids] = lambda: {
        30: _grid(sloped_Z, boundary_elevation=boundary_elevation, boundary_roughness=boundary_roughness)
    }
    app.dependency_overrides[get_hydrograph] = lambda: peaked_hydrograph
    try:
        run_id = client.post("/simulations", json={"mode": "fast"}).json()["run_id"]

        with client.websocket_connect(f"/simulations/{run_id}/stream") as websocket:
            frames = _receive_until_done(websocket)
    finally:
        app.dependency_overrides[get_grids] = lambda: TEST_GRIDS
        app.dependency_overrides[get_hydrograph] = lambda: TEST_HYDROGRAPH

    assert len(frames) == 1
    frame = frames[0]
    depth = np.array(frame["depth"])
    assert frame["step"] == 0
    assert "elapsed_time" not in frame
    assert depth.shape == (3, 3)
    assert frame["peak_discharge_m3s"] == pytest.approx(50.0)
    assert frame["peak_elapsed_time"] == pytest.approx(100.0)
    assert frame["outflow_m3s"] > 0.0
    assert frame["outflow_m3s"] + frame["retained_m3s"] == pytest.approx(50.0)
    assert frame["flooded_cells"] == int((depth > 0.01).sum())
    assert frame["volume"] == pytest.approx(depth.sum())
    assert frame["compute_seconds"] >= 0.0


def test_stream_simulation_fast_uses_requested_resolution():
    run_id = client.post("/simulations", json={"mode": "fast", "resolution": 90}).json()["run_id"]

    with client.websocket_connect(f"/simulations/{run_id}/stream") as websocket:
        frames = _receive_until_done(websocket)

    assert np.array(frames[0]["depth"]).shape == (2, 2)


def test_stream_simulation_gauge_driven_stop_at_peak_ends_at_the_peak():
    peaked_hydrograph = Hydrograph(
        elapsed_seconds=np.array([0.0, 100.0, 200.0]), discharge_m3s=np.array([1.0, 50.0, 2.0])
    )
    app.dependency_overrides[get_hydrograph] = lambda: peaked_hydrograph
    try:
        run_id = client.post(
            "/simulations", json={"mode": "gauge_driven", "frame_interval": 1, "stop_at_peak": True}
        ).json()["run_id"]

        with client.websocket_connect(f"/simulations/{run_id}/stream") as websocket:
            frames = _receive_until_done(websocket)
    finally:
        app.dependency_overrides[get_hydrograph] = lambda: TEST_HYDROGRAPH

    assert frames[-1]["elapsed_time"] == pytest.approx(100.0)


def test_stream_simulation_stops_computing_when_client_disconnects():
    # No frame is due until step 1,000,000, so before the per-step disconnect
    # check the server could only have noticed the client leaving at the very
    # end - minutes of computing for nobody. Closing the TestClient socket waits
    # for the route to return, so the elapsed time is the time to stop.
    run_id = client.post("/simulations", json={"steps": 1_000_000, "frame_interval": 1_000_000}).json()["run_id"]

    start = time.perf_counter()
    with client.websocket_connect(f"/simulations/{run_id}/stream"):
        pass

    assert time.perf_counter() - start < 5.0


# --- seeded_pool: seed volume and seed location -----------------------------

# Big enough for an interior 5x5 patch; a bowl whose lowest point (4, 4) is unambiguous.
SEED_Z = np.add.outer((np.arange(9) - 4.0) ** 2, (np.arange(9) - 4.0) ** 2)


def _latlon_of(transform, row: float, col: float) -> dict:
    """WGS84 lat/lon of a fractional grid position, via the inverse of the path under test."""
    x, y = transform * (col, row)
    (lon,), (lat,) = warp_transform(TEST_CRS, "EPSG:4326", [x], [y])
    return {"lat": lat, "lon": lon}


@pytest.fixture
def seed_grid():
    grid = _grid(SEED_Z, inflow_mask=np.zeros(SEED_Z.shape, dtype=bool))
    app.dependency_overrides[get_grids] = lambda: {30: grid}
    try:
        yield grid
    finally:
        app.dependency_overrides[get_grids] = lambda: TEST_GRIDS


def _run_seeded(params: dict) -> tuple[dict, list[dict]]:
    created = client.post("/simulations", json={"steps": 3, "frame_interval": 1, **params})
    assert created.status_code == 200, created.text
    with client.websocket_connect(f"/simulations/{created.json()['run_id']}/stream") as websocket:
        frames = _receive_until_done(websocket)
    return created.json(), frames


def test_seeded_pool_default_is_unchanged(seed_grid):
    """No seed fields: 400 at the lowest point, bit-for-bit what the route did before they existed."""
    created, frames = _run_seeded({})

    Z, N = seed_grid.Z, seed_grid.N
    H = np.zeros_like(Z)
    seed_pool_at_lowest_point(Z, H, 400.0)
    for _ in range(3):
        H = step(Z, H, N)
    assert created["seed_cell"] == [4, 4]
    assert np.array_equal(np.array(frames[-1]["depth"]), H)
    assert all(frame["volume"] == pytest.approx(400.0) for frame in frames)


def test_seeded_pool_custom_volume_is_conserved(seed_grid):
    _, frames = _run_seeded({"seed_volume": 1234.5})

    assert [frame["volume"] for frame in frames] == pytest.approx([1234.5] * 3)


def test_seeded_pool_custom_location_centers_the_pool_on_that_cell(seed_grid):
    # Cell (2, 6)'s center: off the lowest point, but far enough in for a whole 5x5 patch.
    created, frames = _run_seeded({"seed_location": _latlon_of(seed_grid.transform, 2.5, 6.5), "steps": 1})

    assert created["seed_cell"] == [2, 6]
    depth = np.array(frames[0]["depth"])
    assert np.unravel_index(np.argmax(depth), depth.shape) == (2, 6)
    assert frames[0]["volume"] == pytest.approx(400.0)


def test_seeded_pool_location_just_inside_a_cell_corner_maps_to_that_cell(seed_grid):
    """The containing cell (floor), not the nearest cell center (round)."""
    created, _ = _run_seeded({"seed_location": _latlon_of(seed_grid.transform, 3.02, 5.97)})

    assert created["seed_cell"] == [3, 5]


def test_seeded_pool_location_outside_the_grid_is_rejected(seed_grid):
    # Half a cell past the grid's east edge.
    response = client.post(
        "/simulations",
        json={"steps": 3, "frame_interval": 1, "seed_location": _latlon_of(seed_grid.transform, 4.5, 9.5)},
    )

    assert response.status_code == 422
    assert "outside the 30 m grid" in response.json()["detail"]


@pytest.mark.parametrize("seed_volume", [0.0, -5.0, 10_000.1])
def test_seeded_pool_rejects_out_of_range_volume(seed_volume):
    response = client.post("/simulations", json={"steps": 3, "frame_interval": 1, "seed_volume": seed_volume})

    assert response.status_code == 422


@pytest.mark.parametrize(
    "params",
    [
        {"mode": "gauge_driven", "frame_interval": 1, "seed_volume": 400.0},
        {"mode": "gauge_driven", "frame_interval": 1, "seed_location": {"lat": -29.48, "lon": -51.96}},
        {"mode": "fast", "seed_volume": 400.0},
        {"mode": "fast", "seed_location": {"lat": -29.48, "lon": -51.96}},
    ],
)
def test_seed_params_are_rejected_outside_seeded_pool_mode(params):
    response = client.post("/simulations", json=params)

    assert response.status_code == 422


def test_non_seeded_runs_report_no_seed_cell():
    response = client.post("/simulations", json={"mode": "fast"})

    assert response.json()["seed_cell"] is None


def test_list_grids_returns_every_served_grid_with_its_footprint():
    response = client.get("/grids")

    assert response.status_code == 200
    grids = response.json()
    assert [grid["resolution"] for grid in grids] == [30, 60, 90]
    assert grids[0]["grid_shape"] == [3, 3]
    assert grids[0]["bounds"] == {"west": -51.99, "south": -29.505, "east": -51.93, "north": -29.455}
    footprint = grids[0]["footprint"]
    assert len(footprint) == 4
    top_left = _latlon_of(TEST_TRANSFORM, 0, 0)
    assert footprint[0] == pytest.approx([top_left["lat"], top_left["lon"]])


def test_grid_inputs_serves_elevation_and_landcover_row_major():
    response = client.get("/grids/30/inputs")

    assert response.status_code == 200
    body = response.json()
    assert body["resolution"] == 30
    assert body["grid_shape"] == [3, 3]
    assert body["dx"] == 30.0
    assert body["elevation"] == TEST_Z.ravel().tolist()
    assert body["landcover"] == [15] * 9
    assert body["classes"] == [{"id": 15, "name": "Pasture", "manning_n": 0.030}]


def test_grid_inputs_lists_only_the_classes_present_with_their_roughness():
    landcover = np.array([[24, 15, 15], [33, 15, 24], [15, 15, 15]], dtype=np.uint8)  # Urban, Pasture, Water
    Z = np.array([[1.234, 2.0, 3.0], [4.0, 5.0, 6.0], [7.0, 8.0, 9.006]])
    original = app.dependency_overrides[get_grids]
    app.dependency_overrides[get_grids] = lambda: {30: _grid(Z, landcover=landcover)}
    try:
        body = client.get("/grids/30/inputs").json()
    finally:
        app.dependency_overrides[get_grids] = original

    assert body["landcover"] == [24, 15, 15, 33, 15, 24, 15, 15, 15]
    assert body["elevation"][0] == 1.23
    assert body["elevation"][-1] == 9.01
    assert body["classes"] == [
        {"id": 15, "name": "Pasture", "manning_n": 0.030},
        {"id": 24, "name": "Urban Area", "manning_n": 0.150},
        {"id": 33, "name": "River, Lake and Ocean", "manning_n": 0.040},
    ]


def test_grid_inputs_rejects_an_unserved_resolution():
    assert client.get("/grids/45/inputs").status_code == 404


# --- neighborhood (temporal engine only) ------------------------------------------------------------------


def test_explicit_moore_neighborhood_streams_the_same_frames_as_the_default(seed_grid):
    _, default_frames = _run_seeded({})
    _, moore_frames = _run_seeded({"neighborhood": "moore"})

    assert [f["depth"] for f in moore_frames] == [f["depth"] for f in default_frames]


def test_von_neumann_seeded_pool_streams_and_conserves_mass(seed_grid):
    _, moore_frames = _run_seeded({})
    _, frames = _run_seeded({"neighborhood": "von_neumann"})

    assert all(frame["volume"] == pytest.approx(400.0) for frame in frames)
    assert frames[-1]["depth"] != moore_frames[-1]["depth"]


def test_von_neumann_gauge_driven_keeps_its_volume_balance():
    run_id = client.post(
        "/simulations", json={"mode": "gauge_driven", "frame_interval": 1, "neighborhood": "von_neumann"}
    ).json()["run_id"]

    with client.websocket_connect(f"/simulations/{run_id}/stream") as websocket:
        frames = _receive_until_done(websocket)

    assert frames[-1]["volume"] == pytest.approx(frames[-1]["cumulative_inflow"] - frames[-1]["cumulative_outflow"])


def test_create_simulation_rejects_an_unknown_neighborhood():
    response = client.post("/simulations", json={"steps": 3, "frame_interval": 1, "neighborhood": "hexagonal"})

    assert response.status_code == 422


def test_von_neumann_rejects_an_outflow_fraction_above_its_verified_range():
    from simulation.engine import VON_NEUMANN_MAX_OUTFLOW_FRACTION

    base = {"steps": 3, "frame_interval": 1, "neighborhood": "von_neumann"}
    assert client.post("/simulations", json={**base, "outflow_fraction": VON_NEUMANN_MAX_OUTFLOW_FRACTION}).status_code == 200
    too_high = client.post("/simulations", json={**base, "outflow_fraction": VON_NEUMANN_MAX_OUTFLOW_FRACTION + 0.01})
    assert too_high.status_code == 422
    # Moore is not restricted.
    moore = {"steps": 3, "frame_interval": 1, "outflow_fraction": 0.5}
    assert client.post("/simulations", json=moore).status_code == 200


def test_observed_may2024_serves_row_major_cell_indices():
    observed = np.array([[True, False, False], [False, True, True]])
    excluded = np.array([[False, False, True], [False, False, False]])
    app.dependency_overrides[get_validation_reference] = lambda: ValidationReference(90, 33.67, observed, excluded)
    try:
        response = client.get("/validation/may2024")
    finally:
        del app.dependency_overrides[get_validation_reference]

    assert response.status_code == 200
    assert response.json() == {
        "resolution": 90,
        "grid_shape": [2, 3],
        "stage_m": 33.67,
        "observed_cells": [0, 4, 5],
        "excluded_cells": [2],
    }


def test_observed_may2024_is_503_when_not_loaded():
    app.dependency_overrides[get_validation_reference] = lambda: None
    try:
        response = client.get("/validation/may2024")
    finally:
        del app.dependency_overrides[get_validation_reference]

    assert response.status_code == 503


def test_hydrograph_serves_the_loaded_record():
    response = client.get("/hydrograph")

    assert response.status_code == 200
    body = response.json()
    assert body["elapsed_seconds"] == [0.0, 10.0]
    assert body["discharge_m3s"] == [1.0, 1.0]
    assert body["peak_discharge_m3s"] == 1.0
    assert body["station_code"] == "86879300"


def test_hydrograph_is_503_when_not_loaded():
    app.dependency_overrides[get_hydrograph] = lambda: None
    try:
        response = client.get("/hydrograph")
    finally:
        app.dependency_overrides[get_hydrograph] = lambda: TEST_HYDROGRAPH

    assert response.status_code == 503
