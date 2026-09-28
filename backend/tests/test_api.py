import time

import numpy as np
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from api.main import app
from api.routers.simulations import get_grids, get_hydrograph
from api.state import Grid
from ingestion.hydrograph import Hydrograph

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


def _grid(Z, N=None, inflow_mask=None, boundary_elevation=None, boundary_roughness=None, dx=30.0, bounds=TEST_BOUNDS):
    """A synthetic stand-in for api.state.Grid. No outlet by default (walled on
    every side, the same as the engines' own default), so tests that need one
    pass it explicitly."""
    return Grid(
        Z=Z,
        N=np.full(Z.shape, 0.05) if N is None else N,
        dx=dx,
        bounds=bounds,
        inflow_mask=TEST_INFLOW_MASK if inflow_mask is None else inflow_mask,
        boundary_elevation=boundary_elevation,
        boundary_roughness=boundary_roughness,
    )


# A different shape and bounds than the 30m grid, so tests can tell which one a
# request was served from.
TEST_Z_90 = np.array([[10.0, 10.0], [10.0, 0.0]])
TEST_BOUNDS_90 = (-51.98, -29.50, -51.94, -29.46)
TEST_GRIDS = {
    30: _grid(TEST_Z),
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


def test_create_simulation_serves_the_requested_resolution():
    response = client.post("/simulations", json={"mode": "fast", "resolution": 90})

    assert response.status_code == 200
    body = response.json()
    assert body["grid_shape"] == [2, 2]
    assert body["bounds"] == {"west": -51.98, "south": -29.50, "east": -51.94, "north": -29.46}


def test_create_simulation_rejects_unserved_resolution():
    response = client.post("/simulations", json={"mode": "fast", "resolution": 60})

    assert response.status_code == 422


@pytest.mark.parametrize(
    "extra",
    [{"steps": 5}, {"frame_interval": 1}, {"outflow_fraction": 0.1}, {"stop_at_peak": True}],
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
