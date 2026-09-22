import numpy as np
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from api.main import app
from api.routers.simulations import get_bounds, get_roughness, get_terrain

# Deliberately not using `with TestClient(app) as client:` - that would run
# the app's real lifespan (build_elevation_matrix/build_roughness_matrix),
# which needs the real DEM/land-cover files on disk. Plain instantiation never
# triggers ASGI lifespan events, so combined with the dependency overrides
# below, these tests stay network- and file-free like the rest of the suite.
TEST_Z = np.array([[10.0, 10.0, 10.0], [10.0, 0.0, 10.0], [10.0, 10.0, 10.0]])
TEST_N = np.full((3, 3), 0.05)
TEST_BOUNDS = (-51.99, -29.505, -51.93, -29.455)

app.dependency_overrides[get_terrain] = lambda: TEST_Z
app.dependency_overrides[get_roughness] = lambda: TEST_N
app.dependency_overrides[get_bounds] = lambda: TEST_BOUNDS

client = TestClient(app)

from ingestion.hydrograph import Hydrograph
from api.routers.simulations import get_boundary_elevation, get_boundary_roughness, get_hydrograph, get_inflow_mask

TEST_HYDROGRAPH = Hydrograph(elapsed_seconds=np.array([0.0, 10.0]), discharge_m3s=np.array([1.0, 1.0]))
TEST_INFLOW_MASK = np.array([[False, True, False], [False, False, False], [False, False, False]])
# South-edge outlet (below TEST_Z's own lowest real value, 0.0) so gauge-driven
# runs actually lose some volume through it - roadmap step 10's outlet fix.
# None by default (matches production before the lifespan loads real values -
# `get_boundary_elevation`/`get_boundary_roughness`'s own un-overridden real
# implementations already return None in these tests, since the lifespan
# never runs) - only overridden to a real outlet in the dedicated test below.
TEST_BOUNDARY_ELEVATION = np.pad(TEST_Z, 1, mode="constant", constant_values=np.inf)
TEST_BOUNDARY_ELEVATION[-1, 2] = -5.0
TEST_BOUNDARY_ROUGHNESS = np.pad(TEST_N, 1, mode="constant", constant_values=1.0)
TEST_BOUNDARY_ROUGHNESS[-1, 2] = 0.04

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
    assert frame["cumulative_outflow"] == 0.0  # no outlet configured (get_boundary_elevation returns None)
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

    app.dependency_overrides[get_terrain] = lambda: sloped_Z
    app.dependency_overrides[get_hydrograph] = lambda: long_hydrograph
    app.dependency_overrides[get_boundary_elevation] = lambda: boundary_elevation
    app.dependency_overrides[get_boundary_roughness] = lambda: boundary_roughness
    try:
        run_id = client.post("/simulations", json={"mode": "gauge_driven", "frame_interval": 1}).json()["run_id"]

        with client.websocket_connect(f"/simulations/{run_id}/stream") as websocket:
            last_frame = None
            message = websocket.receive_json()
            while not message.get("done"):
                last_frame = message
                message = websocket.receive_json()

        assert last_frame is not None, "run ended without ever sending a data frame"
        assert last_frame["cumulative_outflow"] > 0.0, "some volume should have left through the outlet"
        assert last_frame["volume"] == pytest.approx(last_frame["cumulative_inflow"] - last_frame["cumulative_outflow"])
    finally:
        app.dependency_overrides[get_terrain] = lambda: TEST_Z
        app.dependency_overrides[get_hydrograph] = lambda: TEST_HYDROGRAPH
        del app.dependency_overrides[get_boundary_elevation]
        del app.dependency_overrides[get_boundary_roughness]


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
