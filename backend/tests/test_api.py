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
