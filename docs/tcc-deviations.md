# TCC vs. Implementation — Decision Log

This tracks every point where the actual implementation (TCC II) diverged from, extended, or had to
fill a gap left by what `TCC1LuccaHeineck.pdf` / `docs/tcc-summary.md` described or implied. It exists
so the TCC II write-up can accurately say "the proposal said X, we did Y, here's why" instead of the
thesis silently matching a proposal it no longer exactly follows. Organized in build order, matching
`docs/project-plan.md`'s roadmap steps. Read that file for the full technical detail behind each item
here; this file is specifically the **comparison to TCC1**, not a general changelog.

Each entry: **What TCC1 said/implied** → **What was actually built** → **Why**.

---

## 0. Development process itself

**TCC1 (Quadro 7):** Jun Q1 Docker/repo/WebSocket setup → Jun Q2 DEM/roughness → Jul Q3 transition
rules → Jul Q4 optimization/timestep → Aug Q5 React UI → Aug Q6 WebSocket integration → Sep Q7-Q8 real
data/calibration → Oct Q9-Q10 metrics/GPU → Nov writing. Infrastructure first, algorithm validation
folded into the middle.

**Built:** The opposite order — the transition rule was implemented and validated on synthetic grids
first (steps 1-2), *then* real DEM/land-cover data (steps 3-4), *then* FastAPI (step 5), *then* the
frontend (step 6), *then* Docker (step 7), with real-timestep/real-event work (steps 8-9) coming after
all of that, and CSI/RMSE validation (step 11, after performance work in step 10) still ahead.

**Why:** The transition rule is the one piece of highest academic risk — if the physics/math were
wrong, everything built around it (API, sockets, containers) would need rework. Validating it in
isolation on small arbitrary grids, with exact mass-conservation as the correctness check, before
spending time on infrastructure, was a deliberate choice to front-load risk rather than follow the
proposal's literal calendar order. Documented at the top of `docs/project-plan.md` from the start.

---

## 1-2. Core transition rule

**TCC1's documented equation:** `Q_i = (1/n_i) * h_i^(5/3) * sqrt(S_i)`, Moore neighborhood, mass
conservation as the correctness check, diagonal/orthogonal distance distinction.

**Built:** The equation as documented, but with several additions/clarifications TCC1 doesn't specify:

- **`outflow_fraction` cap** — each cell releases at most a fraction of its depth per step. This is a
  pure numerical-stability engineering choice for the explicit (Jacobi-style) update scheme, not part
  of the TCC's equation. Without it, `H` could go negative.
- **Substep decomposition** (`_MAX_STABLE_SUBSTEP_FRACTION`) — releasing the full `outflow_fraction` in
  one synchronous pass produced a checkerboard/speckle artifact (neighbors overshooting each other,
  the same instability family as violating a CFL condition). Fixed by internally splitting one
  requested `outflow_fraction` into several smaller synchronous sub-updates. External behavior/signature
  unchanged; purely an internal stability fix.
- **Step 1 used bare slope, not `sqrt(slope)`** — a simplification error relative to TCC1's own
  equation, caught and corrected when Manning weighting was added in step 2.
- **Manning weighting scope, clarified where TCC1 is silent**: since `h_i` is the same across all 8
  outgoing directions, it cancels out of the normalized transport-factor ratio — so `N` was implemented
  as affecting only *which direction* the already-capped release prefers, not *how much* leaves the
  cell (a true discharge-rate cap would need a real `dx`/`dt`, which didn't exist until step 3/8).
  Documented as a deliberate scoping decision, not a literal transcription of the TCC's formula.
- **`n_i` = the *destination* neighbor's roughness**, not the source cell's. TCC1's summary doesn't say
  which cell's roughness applies when water crosses a boundary between two different land-cover types —
  this was an undocumented gap the implementation had to fill.
- **A finding, not a deviation**: in a closed system given enough steps, final equilibrium shape is
  *identical* regardless of roughness — roughness only affects the transient path/speed, not where a
  fixed-volume closed system eventually settles (a flat surface has no slope left for `N` to act on).
  Confirmed by direct array diff. Worth citing as a validated physical-consistency result.

**Cell states (Inactive/Transport/Accumulation) — not implemented.** TCC1's CA-theory section
describes these three per-cell states as a processing optimization. The actual engine does not classify
cells this way; it applies one dense vectorized NumPy update to the whole grid every step. This is a
genuine simplification relative to TCC1's stated theory, not called out anywhere in `project-plan.md`
until now — worth an explicit sentence in the write-up (likely framed as: NumPy's dense vectorized
operations already outperform Python-level state branching at this grid size, so the optimization
wasn't needed yet; revisit if step 10's performance work finds otherwise).

---

## 3. Real DEM ingestion

**TCC1:** "SRTM / TOPODATA (INPE)," clip to ROI, sink filling, ~30m resolution.

**Built:**
- **SRTMGL1 via the OpenTopography REST API**, not TOPODATA's manual portal. Same underlying SRTM data
  class TCC1 names, but scriptable/reproducible/HTTPS (`download_dem.py`), and already clipped
  server-side. TOPODATA's actual portal is manual/click-through, which doesn't fit a reproducible
  pipeline.
- **Reprojection to a metric CRS** (SIRGAS 2000 / UTM 22S, EPSG:31982) with square 30m pixels — a
  necessary step TCC1 doesn't mention, required because the engine's neighbor-distance math (`hypot`)
  only holds in a projected CRS, not raw lat/lon degrees.
- **Corner nodata-slivers cropping** — an artifact of reprojection rotating the ROI box slightly;
  not something TCC1 anticipates, found and fixed during implementation.
- **Sink filling: a hand-rolled priority-flood algorithm** (Barnes et al. 2014, stdlib `heapq`), not a
  hydrology library (`pysheds`/`richdem` were tried first). Reason: `pysheds`'s `numba` JIT step fails
  to compile on this project's Python 3.14 (a numba/CPython version bug, unrelated to the DEM itself).
  Priority-flood was simple enough (~30 lines) to implement directly rather than downgrade Python.

---

## 4. Real land-cover / roughness

**TCC1:** "MapBiomas... looked up into Manning roughness matrix N via a static category→coefficient
dictionary." Doesn't specify a source for the coefficients themselves, a resampling method, or a target
year.

**Built:**
- **Year 2024 chosen deliberately** (not "whatever's newest") to match the May 2024 validation event —
  a decision TCC1's data table doesn't make explicit but the validation goal implies. Creates a known,
  accepted data-vintage mismatch (DEM stays SRTM-era, ~2000) that's documented but not resolved.
- **Direct COG streaming** (`/vsicurl/`, ~40KB pulled instead of the ~800MB whole-Brazil file) — an
  engineering choice TCC1 doesn't need to specify at the proposal level.
- **Nearest-neighbor resampling** to align to the DEM's grid, not bilinear (bilinear would blend
  categorical class IDs into meaningless fractional values) — a correctness decision TCC1's one-line
  description doesn't surface.
- **Coefficient source filled in**: TCC1 says "a static category→coefficient dictionary" but MapBiomas
  publishes no roughness table of its own. The actual values were cross-walked from a citable
  NRCS-Kansas table (adopted for HEC-RAS 2D modeling, rooted in Chow 1959), scoped to the ~10 classes
  actually observed in the ROI rather than MapBiomas's full ~29-class national legend. Two documented
  simplifications: Forest Plantation treated as Forest Formation, Mosaic of Uses treated as generic
  Cultivated Crops. Any class outside the table raises an error rather than guessing.

---

## 5. Backend API

**TCC1:** FastAPI REST + WebSocket; "every N iterations, encode frame as base64 PNG and broadcast...
also persist H[t] to disk for later validation."

**Built:**
- **JSON numeric arrays, not base64 PNG.** A direct, acknowledged deviation from TCC1's stated data
  flow — simpler and directly testable without a frontend; PNG was deferred until something (the
  frontend, step 6) actually needed an image, and it turned out client-side canvas rendering (see
  section 6) made server-side PNG encoding unnecessary entirely, so this was never revisited.
- **No persistence of `H[t]` to disk.** TCC1's data-flow explicitly names this for later validation;
  it has not been built. Step 11 (CSI/RMSE) will need to decide whether to add it or compare
  differently (e.g. against final/periodic in-memory state only). Worth flagging as an open gap, not a
  silent drop.
- **In-memory, single-use run registry** (`run_id` → consumed exactly once on WebSocket connect, no
  persistence layer at all) — consistent with the "no DB" stack decision in `plan.md`, but the specific
  register-then-stream-once pattern is an implementation detail TCC1 never specifies at this level.
- **API serves only the one real Lajeado/Estrela grid**, no synthetic-grid option — an architectural
  boundary decision (`api/` never depends on `examples/`) not discussed in TCC1 at all.

---

## 6. Frontend

**TCC1:** "React + TypeScript + Vite... a config panel (initial river stage, rainfall/volume params,
neighborhood type), a Leaflet map (OpenStreetMap base layer)... log/metrics panel."

**Built:**
- **Plain Leaflet, not `react-leaflet`** — an implementation-library choice TCC1's one-word "Leaflet"
  doesn't pin down either way.
- **Basemap switched from OpenStreetMap to Esri's Dark Gray Canvas.** This is a direct deviation from
  TCC1's explicitly named "OpenStreetMap base layer." Found during step 6 testing: OSM's busy colored
  roads/labels/blue-water tiles visually competed with the flood overlay (the same problem that first
  forced the flood color ramp to change from blue-tinted to orange-red, since it was invisible against
  OSM's own blue river). Rather than keep fighting OSM's palette, the basemap itself was swapped for a
  low-saturation canvas basemap purpose-built to recede behind data overlays. Worth an explicit
  sentence in the write-up since it contradicts TCC1's literal wording, even though it serves the same
  stated purpose (a base layer under the flood overlay).
- **Config panel fields differ from TCC1's named set.** TCC1 names "initial river stage, rainfall/volume
  params, neighborhood type." The actual `ConfigPanel` exposes `steps`/`frame_interval`/
  `outflow_fraction`, plus (as of step 9) a `seeded_pool`/`gauge_driven` mode toggle. None of TCC1's
  three named params exist as literal UI fields:
  - "Initial river stage" → replaced conceptually by the step-9 gauge-driven mode, which derives its
    own driving signal from the real ANA gauge record rather than a user-typed stage value.
  - "Rainfall/volume params" → not built; rain input is a known, deliberately deferred idea (see
    section 9) needing an advisor conversation before it's added, since it touches the TCC's documented
    closed-system base model.
  - "Neighborhood type" (Moore vs. von Neumann) → not built; the engine is Moore-only. Listed as a
    possible future feature, not committed.
- **Client-side depth-to-image rendering**, mirroring the API's JSON-not-PNG decision above — no
  backend image-encoding work was ever added.

---

## 7. Docker Compose

**TCC1/`plan.md`:** Docker Compose, matches directly — no conceptual deviation. Two purely technical
fixes were needed along the way (a missing `libexpat1` system library for rasterio's wheel; a `data/`
bind-mount gap between the backend container and the repo-root data folder) — implementation bugs, not
decisions worth a thesis comparison, noted here only for completeness.

---

## 8. Real timestep (`dt`) — an addition TCC1 doesn't name as a step

**TCC1:** Never explicitly calls for deriving a real elapsed-time `dt` from Manning velocities as its
own step. It's implied only indirectly: the related-work table flags Jahanbazi & Egger 2017's
adaptive-timestep method (which explicitly *removes* the CFL constraint) as **explicitly deprioritized**
future work in TCC1 ("removal of the CFL criterion").

**Built:** `compute_stable_dt` — derives `dt` from a CFL-style stability bound using real Manning
overland-flow velocities and the real `dx = 30m` cell size, recomputed fresh every step (not a fixed
constant). This is a genuinely new engine capability, motivated by an implementation-level need TCC1
didn't foresee at the proposal stage: converting abstract step counts into physically meaningful
elapsed time, a hard prerequisite for mapping a real hydrograph's 15-minute cadence onto simulation
steps (step 9). It is *consistent* with TCC1's stated scope, not a deviation from it — a literal,
recomputed CFL bound is exactly the kind of "keep CFL, don't remove it" approach TCC1's own literature
review frames as in-scope, as opposed to Jahanbazi & Egger's beyond-CFL method, which stays out of
scope. Worth presenting in the write-up as "a necessary addition consistent with the reviewed
literature," not as scope creep.

---

## 9. Boundary inflow / open-system extension — added ahead of the numbered roadmap

**TCC1:** The base model is explicitly closed — "no rain, no infiltration... total volume must stay
exactly constant," matching the informal PoC exactly. This is stated as *the* correctness invariant.

**Built:** `step()` gained an optional `inflow` parameter — a per-cell external source array added to
`H` once per step, making the domain an open system. The conserved invariant becomes `final volume ==
initial + cumulative injected volume` — still exact and checkable, just a different invariant than
TCC1's stated one.

**Why the deviation was necessary:** investigating how step 11's real-event validation would actually
work surfaced a real gap — a real event like May 2024 is driven by the river rising continuously over
~72 hours, and no strictly closed, single-seeded-pool system can represent that. This is a deliberate,
documented extension beyond TCC1's base model, not a silent one.

**Explicitly not rain.** The parameter is generic (any per-cell array), but its only actual use is
river-boundary inflow. Rain input remains a separate, still-unbuilt idea in the "possible future
features" backlog, deliberately not folded into steps 8-11 — flagged in `project-plan.md` as something
that would need an advisor conversation, since it changes what the thesis is claiming to model, unlike
boundary inflow which represents the same TCC-described river-stage physics, just applied continuously
instead of as a single initial pool.

---

## 10. Real gauge-driven hydrograph (step 9)

**TCC1's data table:** "Historical flood levels — ANA/SGB telemetry, HWM — daily/hourly — Validation
ground truth (**used only in post-processing/calibration, not in the engine**)."

**Built:** The same category of ANA gauge data (station `86879300`, Porto Fluvial de Estrela) is now
used as a **live driving input to the engine** — converted into a discharge series, then a per-cell
`inflow`, streamed step-by-step through `POST /simulations`/the WebSocket loop. This is a genuine
conceptual expansion beyond what TCC1's data-flow table states.

**Why this matters for the write-up, explicitly:** TCC1 draws a clean line — real gauge/HWM data is
validation-only, never touches the engine's own computation. The actual implementation crosses that
line: the engine is now *driven* by real gauge data, not just checked against it afterward. This isn't
circular validation — the separate SGB/CPRM stage-indexed flood-extent shapefiles (step 11) remain the
actual CSI comparison target, a dataset not yet used for anything — but the same station's data now
serves two different roles across the project (driving input here; a different, disjoint real dataset
for spatial validation later), which is worth being explicit and upfront about rather than letting a
reader assume TCC1's original validation-only framing still holds.

**Sub-decisions within step 9, also worth noting:**
- **Real `Vazao` (discharge) field found directly on the ANA record** — the implementation plan
  originally called for researching an external rating curve to convert stage → discharge; once real
  discharge values turned up already computed by ANA for this exact station/event, the plan was
  deliberately abandoned mid-implementation in favor of the real data. Arguably a better-grounded
  choice than what TCC1's plan first called for, worth presenting as a positive pivot, not a shortcut.
- **ANA API operation switch**: `HidroSerieHistorica` (planned) turned out to return the wrong data
  shape (a monthly summary), corrected to `DadosHidrometeorologicos` after inspecting the live WSDL.
- **Inflow boundary edge correction**: an initial heuristic-based guess (`"east"`) was wrong; corrected
  to `"north"` after checking against the real DEM's channel-elevation cells. An implementation bug
  caught by review, not a TCC-comparison point, but a concrete example of the project's validation
  process catching a real mistake before it silently affected results — useful for a "methodology"
  section of the write-up.

**Limitation flagged here, resolved in step 10 below:** the engine's closed-boundary (walls-on-all-sides)
design — which TCC1's own base model requires for exact mass conservation — was never a problem for a
single seeded pool, but met a real ~14-day hydrograph for the first time in step 9. A full run's total
real inflow (~9.1e9 m³) into the closed 183×192 ROI implies a mean depth of ~288m against a 96m maximum
terrain elevation — the entire ROI eventually floods, since there is nowhere for water to leave. Trying
the other suggested mitigation first (validating only a partial time window) was tested directly and
found *not* to work either — see section 11 below for both the test and the actual fix.

---

## 11. Outlet boundary condition — resolving the closed-boundary limitation section 10 flagged

**TCC1:** The base model is explicitly closed on all sides ("no rain, no infiltration... total volume
must stay exactly constant"), and step 9's own validation-plan note assumed this could be worked around
for CSI purposes either via "an outlet boundary condition, or validating only an early/partial time
window" — two options, never tested against each other.

**What was tried first, and found not to work:** a real (not extrapolated) run through the actual flood
peak (day 5.56 of the 14-day event, at 90m resolution) was let run to completion specifically to test
the "partial time window" option. Result: by the time it reaches the peak — 40% of the way through the
event, not even the full duration — the entire ROI is *already* flooded to a mean depth of 113.88m and
a max of 147.27m, against terrain that only reaches ~96m. The over-flooding happens well before the
peak, so restricting the time window doesn't avoid it; that mitigation was assumed workable in step 9's
note but never actually measured until this step.

**What was built instead:** `simulation.engine.step` gained two new optional parameters,
`boundary_elevation`/`boundary_roughness` (full padded-shape overrides of the default all-wall
boundary), letting specific boundary cells act as a real outlet instead of a wall — water flows toward
a lower "virtual outside" elevation exactly like any other downhill neighbor, through the *existing*
weighted-redistribution math (no new redistribution logic was needed: `_single_update` already only
returns the cropped interior of its scratch array, so anything that reaches the boundary was always
silently discarded - it just never happened before because a `+inf` wall is never downhill from a real
cell). Omitting both parameters reproduces the original all-wall behavior exactly (verified via a
dedicated regression test), so this is a strict, backward-compatible superset of `step()`'s existing
contract, not a breaking change - the same pattern already established for `inflow` in section 9.

**Outlet location**: the south edge's channel cells - reusing `find_boundary_inflow_mask`'s existing
channel-detection heuristic (already generic across all four edges) rather than writing new geometry
logic, on the same edge step 9's own two-stage rule already identified as downstream (lower minimum
elevation than the north inflow edge).

**Outlet magnitude - a documented modeling choice, not a literal physical measurement**: each outlet
cell's "virtual outside" elevation is its own real elevation minus a fixed margin (reusing
`_CHANNEL_ELEVATION_MARGIN_METERS`, the same constant already used to define "channel-scale" elevation
differences elsewhere in `ingestion/hydrograph.py`), rather than extrapolating the observed slope from
the last one or two interior cells - real sink-filled DEM data only guarantees *some* monotonic
downhill path to the border exists, not that any two specific adjacent cells along one column are
themselves monotonic, so a local two-cell gradient risked being noisy or even uphill. A fixed margin is
simpler and robust to that, at the cost of not being derived from a real discharge-capacity calculation
(e.g. a rating curve or channel cross-section) - the outlet's drainage rate is only as physically
grounded as "the channel keeps sloping downward past the edge at the same scale it already does inside
the ROI," not a calibrated capacity limit. **Confirmed by a real, complete run through the actual May
2024 peak (see `docs/project-plan.md`'s step 10 for the full numbers)**: max depth 16.43m and only
~11.5% of the ROI flooded, against the no-outlet run's 147.27m max and the entire grid submerged - the
fixed-margin outlet, simple as it is, keeps the flood extent physically plausible and localized to the
river channel rather than just delaying the same over-flooding. An unexpected bonus, not something this
fix set out to achieve: the same run also completed **~5x faster** (23.1 min vs. 1.92h to reach the same
point) - a closed, over-filling basin builds increasingly extreme depth/velocity gradients as it backs
up, which is exactly what forces the adaptive CFL timestep ever smaller; a system that can actually
drain never reaches that pathological state. Correctness and performance turned out to be the same fix
here, worth stating plainly in the write-up rather than treating them as two separate results.

**Exact accounting, not approximate**: the new invariant (`final == initial + cumulative_inflow -
cumulative_outflow`) is derived by the caller (`api/routers/simulations.py::_run_gauge_driven`) via
volume bookkeeping around each `step()` call (`outflow_this_step = H_before.sum() + inflow.sum() -
H_after.sum()`), the same way `cumulative_inflow` was already tracked outside the engine - `step()`'s
return signature is unchanged, no new return value was needed.

---

## 12. Not yet built, relative to TCC1's stated plan (as of this session)

- **CSI/RMSE validation metrics** — TCC1's core validation plan; scaffolded (`validation/` exists,
  empty) but not implemented. Step 11, after step 10's performance work.
- **GPU/CuPy performance benchmarking** — TCC1's stack rationale names CuPy-compatibility as a design
  goal; the NumPy code has been kept vectorized/CuPy-compatible throughout, but nothing has actually
  been run on a GPU yet. Folded into step 10, tried only after CPU-side fixes land.
- **Persisting `H[t]` frames to disk** — named explicitly in TCC1's data-flow diagram, not built (see
  section 5).
- **Base64 PNG frame encoding** — named explicitly in TCC1's data-flow diagram, not built; JSON arrays
  + client-side rendering used instead (see sections 5-6).
- **Rainfall/volume config-panel input** — named explicitly in TCC1's frontend section, deliberately
  deferred pending an advisor conversation about scope (see section 9).
- **Neighborhood-type (Moore/von Neumann) toggle** — named explicitly in TCC1's frontend section, not
  built; engine is Moore-only.
- **Automated pytest suite (50 tests across engine/ingestion/API, as of step 9)** — not something TCC1
  describes at all; TCC1's own informal PoC validation was print-statement/manual-inspection based
  (Quadro 6's metrics table). Worth mentioning in the write-up as a methodological upgrade in TCC II
  over TCC1's own informal validation approach, not a deviation in the "diverged from the plan" sense.

---

*Keep this file updated alongside `docs/project-plan.md` whenever a new roadmap step introduces another
point of comparison to TCC1 — the goal is that by the time the thesis is written, every "we said X, we
did Y" question already has its answer and rationale sitting here instead of needing to be
reconstructed from git history.*
