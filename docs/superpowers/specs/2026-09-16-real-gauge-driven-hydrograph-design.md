# Design: real gauge-driven hydrograph, wired end-to-end (roadmap step 9)

Status: approved by user, pre-implementation-plan.
Date: 2026-09-16

## Context

This is roadmap step 9 in `docs/project-plan.md`. Two prerequisites are already done:

- Step 8 (`compute_stable_dt` in `backend/simulation/engine.py`) derives a real, adaptive elapsed
  timestep from Manning flow velocities under a CFL-style stability condition, using the real
  `dx = 30m` cell size from step 3.
- The engine-ahead-of-schedule `inflow` parameter on `step()` supports an open system: a per-cell
  source array added to `H` once per step, with the conserved invariant becoming
  `final volume == initial + cumulative inflow`.

Neither is reachable through the API or frontend today — a user running the actual app still only
gets a closed-system, single-seeded-pool run. This step makes the real May 2024 flood event (ANA/SGB
gauge station `86879300`, Porto Fluvial de Estrela, inside this project's own 6km ROI) drivable
end-to-end: gauge readings → per-step inflow → `POST /simulations` / the WebSocket stream →
the frontend showing an open-system run.

Decisions below were made collaboratively (see brainstorming session) and are locked in; this spec
records them, not re-opens them.

## Decisions locked in

1. **Stage → inflow conversion**: use a rating curve (stage → discharge, m³/s) for station
   `86879300`, not a proportional/threshold approximation. ANA maintains rating-curve-derived
   discharge for its fluviometric stations as standard practice; the exact curve/table for this
   station is an acquisition-time detail to pin down while building `download_hydrograph.py`, not an
   open design question.
2. **Injection point**: inflow is applied to a mask of river-channel cells on one ROI boundary edge
   (found via the already-processed `Z`, not the gauge's literal lat/lon — the gauge itself sits
   inside the ROI, not at a boundary, so "inject where the gauge is" would be a conceptual mismatch
   with "water entering from upstream").
3. **Event duration / pacing**: no downsampling of the event and no real-time throttling. The
   hydrograph's own duration determines how many engine steps a gauge-driven run takes; the run
   proceeds as fast as the engine can compute, however long that takes in wall-clock time.
4. **Run modes**: today's closed-system, seeded-pool run stays exactly as-is (useful as a
   network-free synthetic smoke test). Gauge-driven is a new, additive mode, not a replacement.

## Components

### 1. `backend/scripts/download_hydrograph.py` (new, network-touching)

Mirrors `download_dem.py`/`download_landcover.py`'s existing split. Fetches the 15-minute stage
record for station `86879300` covering the May 2024 event window from ANA's Hidroweb/telemetria API,
saves the raw series to `data/raw/`. This is the only file in this feature that touches the network.

### 2. `backend/ingestion/hydrograph.py` (new, local-only)

- `stage_to_discharge(stage_series, rating_curve)`: applies the station's rating curve to convert
  the raw stage series (meters) into discharge (m³/s). The rating curve itself is a small, versioned
  lookup/table checked into the repo (same spirit as `MANNING_N_BY_CLASS` in `landcover.py` — a
  citable, static reference table, not fetched at runtime).
- `build_hydrograph(...)`: runs acquisition-independent processing and returns a queryable time
  series object exposing `discharge_at(elapsed_seconds)` via interpolation — needed because the
  engine's `dt` is adaptive (0.2s–18s observed in step 8), not fixed 15-minute steps, so the
  simulation will query this at arbitrary elapsed times, not by index into the raw 15-min readings.
- `find_boundary_inflow_mask(Z, edge)`: locates the river-channel cells (lowest-elevation run) along
  one ROI boundary edge, returning a boolean/weight mask the same shape as `Z`'s boundary row/column.
- `discharge_to_inflow(discharge_m3s, dt, mask, cell_area)`: converts a discharge value + timestep
  into the per-cell volume array `step()`'s `inflow` parameter expects, distributed across the mask.

### 3. Engine loop wiring — `backend/api/routers/simulations.py`

`POST /simulations` gains a `mode` field: `"seeded_pool"` (default, today's unchanged behavior) or
`"gauge_driven"` (new). Gauge-driven requests do not accept `steps` — the hydrograph's own duration
determines when the run ends, so `steps` is rejected/ignored for this mode (a pydantic validator, not
a silent ignore, to avoid confusing a user who passes both).

Per-iteration loop for `"gauge_driven"`:
1. `dt = compute_stable_dt(Z, H, N, dx)`
2. `discharge = hydrograph.discharge_at(elapsed_time)`
3. `inflow = discharge_to_inflow(discharge, dt, boundary_mask, cell_area)`
4. `H = step(Z, H, N, outflow_fraction, inflow=inflow)`
5. `elapsed_time += dt`
6. Every `frame_interval` steps, send `{"step", "depth", "volume", "elapsed_time", "cumulative_inflow"}`
   — `elapsed_time` and `cumulative_inflow` are new fields (present only in gauge-driven mode) so the
   frontend can show *why* volume is rising instead of it looking like a conservation bug.
7. Loop ends when `elapsed_time` reaches the hydrograph's recorded duration; final frame includes
   `{"done": true}` as today.

No changes to `simulation/engine.py` itself — this step is wiring only, consistent with the engine
already supporting everything needed (`inflow`, `compute_stable_dt`).

### 4. Frontend

- `ConfigPanel`: a mode toggle (`Synthetic seeded pool` / `Real May 2024 event`). Seeded-pool mode
  keeps today's fields unchanged. Gauge-driven mode drops the `steps` input (event-determined) and
  keeps `frame_interval`.
- `LogPanel`: log line adds elapsed real time (formatted, not raw seconds) when present on a frame;
  volume rising is expected/labeled as such in gauge-driven mode rather than implying an error.
- `types/simulation.ts`: extend the frame type with the two new optional fields.

No new dependencies, no new components — this reuses `useSimulationRun`'s existing state machine and
`FloodMap`'s existing rendering path unchanged (a frame is still `{step, depth, volume}` plus two
optional fields).

## Data flow summary

```
ANA Hidroweb API --(download_hydrograph.py, network)--> data/raw/*.csv
                                                              |
                                                    ingestion/hydrograph.py
                                                    (rating curve, interpolation,
                                                     boundary mask, unit conversion)
                                                              |
                                    api/routers/simulations.py's WS loop, per iteration:
                                    compute_stable_dt -> discharge_at(elapsed_time) ->
                                    discharge_to_inflow -> step(..., inflow=...) -> elapsed_time += dt
                                                              |
                                    frame {step, depth, volume, elapsed_time, cumulative_inflow}
                                                              |
                                          frontend: ConfigPanel mode toggle, LogPanel elapsed-time log
```

## Error handling

- Missing/unparseable rating curve data for the station at ingestion time: raise clearly at
  `build_hydrograph()` time (fail loud, matching `landcover.py`'s "unmapped class raises `ValueError`"
  precedent) — no silent fallback to a guessed curve.
- A `"gauge_driven"` request when the hydrograph data hasn't been ingested/processed yet (i.e. missing
  processed file on disk): the API should reject with a clear 4xx at `POST /simulations` time, not
  fail mid-stream over the WebSocket — mirrors how `Z`/`N` are loaded once at `lifespan` startup, not
  per-request.
- `discharge_at(elapsed_time)` past the end of the recorded event: undefined/out-of-range lookups are
  an error, not an extrapolation — the loop's own termination condition (elapsed_time reaches the
  hydrograph's recorded duration) is what prevents ever calling this out of range; if it did happen it
  indicates a real bug in the elapsed-time accounting, not a case to be handled gracefully.

## Testing

Network-free, matching the project's existing pattern (`test_ingestion.py`, `test_landcover.py`):

- `backend/tests/test_hydrograph.py` (new): a tiny synthetic stage series + a small fake rating
  curve — verifies `stage_to_discharge` math, `discharge_at` interpolation between raw sample points,
  `find_boundary_inflow_mask` picks the correct low-elevation edge cells on a small synthetic `Z`, and
  `discharge_to_inflow`'s unit conversion (m³/s × dt → volume, split across the mask, summing back to
  the expected total).
- `backend/tests/test_api.py`: new `"gauge_driven"` mode cases via `dependency_overrides` (a tiny
  synthetic hydrograph fixture, no real ANA network calls) — request validation (`steps` rejected in
  this mode), frame shape includes the two new fields, mass-conservation invariant holds as
  `final == initial + cumulative_inflow` mid-stream, and run termination at the hydrograph's recorded
  duration.
- No frontend test framework exists yet (deferred per existing project decision) — frontend changes
  verified manually in-browser per this project's stated verification practice, same as step 6.

## Explicitly out of scope for this step

- CSI/RMSE validation against observed flood extent (roadmap step 10).
- Performance benchmarking / GPU exploration (roadmap step 11).
- Rain input as a source term — remains a separate, advisor-level scope decision, not folded into
  this step.
- Von Neumann neighborhood toggle.
- Real-time-synced playback pacing (explicitly rejected above — runs proceed as fast as computed).
