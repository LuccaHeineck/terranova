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
frontend (step 6), *then* Docker (step 7), with real-timestep/real-event work (steps 8-9) and CSI
validation against a real event (step 10) coming after all of that, and performance benchmarking (step
11) still ahead.

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
  - "Neighborhood type" (Moore vs. von Neumann) → built later for the temporal engine (§22). Moore stays
    the default and the only validated neighborhood; von Neumann is an explicitly unvalidated option, and the
    fast engine is Moore-only.
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
circular validation — the separate SGB/CPRM stage-indexed flood-extent data (see section 12 below) is
the actual CSI comparison target, a disjoint real dataset from the driving gauge series — but the same
station now serves two different roles across the project (driving input here; a different dataset for
spatial validation there), which is worth being explicit and upfront about rather than letting a reader
assume TCC1's original validation-only framing still holds.

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

## 12. CSI validation against the real May 2024 flood extent (step 10)

**TCC1:** Validate simulated flood extent against real 2023/2024 flood maps via CSI (Critical Success
Index), comparing simulated vs. observed flooded cells; RMSE against HWM/SWOT depth points for vertical
accuracy. `validation/` was scaffolded from the start of the project for this.

**Built:** `validation/metrics.py` implements CSI, Hit Rate, and False Alarm Rate as pure functions over
boolean NumPy arrays (all three are the same confusion-matrix counts — TP/FP/FN — so implementing HR/FAR
alongside CSI was free). `ingestion/flood_extent.py` (new) ingests real ground truth: SGB/CPRM (via
IPH-UFRGS) publishes real HEC-RAS-2D-modeled flood-extent polygons for Lajeado, indexed by river stage,
as a public, no-auth ArcGIS REST MapServer (`geoportal.sgb.gov.br/server/rest/services/LAJEADO/
MapServer`) — the same "direct scriptable API, no portal scraping" pattern already used for the DEM
(OpenTopography) and land-cover (MapBiomas) ingestion. One layer, `COTA_3367cm`, is stamped 33.67m —
essentially exactly the real May 2024 peak stage this project's own hydrograph already drives from (TCC-
documented as 33.66m) — the natural CSI comparison target. `examples/validate_may2024.py` (new) runs the
real gauge-driven engine (steps 8-9, plus the outlet boundary condition) from a dry grid through the real
observed peak (found directly from the gauge series via `argmax`, not hardcoded), thresholds the
resulting depth array into a "flooded" mask, and scores it against the real SGB polygon rasterized onto
the same grid. See `docs/project-plan.md`'s "Step 10 done" for the actual numbers this run produced.

**Deviation 1 — validation runs at 90m resolution, not the officially-served 30m grid.** A full
gauge-driven run at the live API's 30m resolution takes hours (see section 10/11's step-9 known
limitations); this is a one-off validation script, not a production requirement, so
`config.settings.VALIDATION_RESOLUTION_METERS = 90.0` builds a separate grid
(`ingestion.dem.build_elevation_matrix`'s new optional `resolution` parameter, defaulting to the
existing 30m for every other caller) persisted to its own `data/processed/*_90m.tif` files, never
touching `lajeado_estrela_z.tif`/`_n.tif`. `ingestion.landcover.build_roughness_matrix` needed no change
— it already aligns to whatever reference grid it's given. A deliberate, documented wall-clock tradeoff,
not a claim that 90m is the "right" resolution for this model.

**Deviation 2 — RMSE is not implemented this step.** See section 14 below for why (no confirmed
structured HWM dataset for this small ROI). *(Since formally closed as a data-availability
limitation - see §20.)*

**Deviation 3 — the validation loop is a deliberate duplicate, not a shared function.**
`api/routers/simulations.py::_run_gauge_driven` is an async WebSocket coroutine inside `api/`, which
`examples/` must never import (`docs/ARCHITECTURE.md`'s dependency direction). `validate_may2024.py`
duplicates a trimmed, synchronous version of that same loop (same `dt`-cap/volume-bookkeeping logic,
different stop condition — the real peak instead of the hydrograph's full duration) rather than
introducing a new module boundary `ARCHITECTURE.md` doesn't currently sanction. The same kind of choice
`docs/project-plan.md` already flags as acceptable for `poc_grid.py`/`poc_real_dem.py`'s own independent
loops — named explicitly here rather than left as a silent gap.

---

## 13. Performance investigation: substep decomposition vs. CFL-derived dt (step 11)

**TCC1:** The thesis's core premise is that a macroscopic-CA model runs in seconds-to-minutes against
HEC-RAS 2D's hours-to-days, citing Jamali et al. 2019 (CA-ffé, 250-1,100x faster than traditional models)
and Torres et al. 2022 (~1s vs. 2012s) as the comparison class this project's own performance section
(TCC1's objective (d), `docs/tcc-summary.md`'s validation plan) is expected to land near. Step 9/10's
real gauge-driven runs instead take on the order of tens of minutes to hours even at the engine's own
committed 30m resolution (`docs/development-difficulties.md`'s "the performance wall" and "restricting
to a partial time window" entries record a real, measured 30m run trending toward 7-8h to reach just the
peak) - a real, unresolved gap against that premise, and roadmap step 11's explicit job to investigate.

**Hypothesis investigated:** profiling (cProfile, a representative 90m/30m gauge-driven run) found
`step()`'s internal substep decomposition dominates ~95% of wall-clock time -
`_MAX_STABLE_SUBSTEP_FRACTION` (tuned in step 1, before `compute_stable_dt`'s real CFL-derived `dt`
existed in step 8) forces a fixed `ceil(outflow_fraction / 0.01)` synchronous passes per macro step
(50 at the default `outflow_fraction=0.5`), entirely decoupled from how small the real `dt` for that
step actually is. The hypothesis: reconciling the two - so a macro step driven by a small real `dt`
doesn't still pay for 50 full-grid passes designed for a `dt`-blind heuristic - would recover most of
that cost.

**What was tried:**

- **(a) `outflow_fraction_for_dt(outflow_fraction, dt, dt_cfl)`** (`simulation/engine.py`): scales the
  requested `outflow_fraction` down proportionally whenever the `dt` actually used for a macro step
  (`api/routers/simulations.py::_run_gauge_driven`) is capped below the raw CFL bound `compute_stable_dt`
  would otherwise allow (`dt_cfl`) - e.g. by the 900s inflow-burst cap or a hydrograph's
  remaining-duration clip. Mathematically exact at the calibration anchor (`dt == dt_cfl` reproduces
  `outflow_fraction` unchanged, byte-identical to pre-existing behavior), monotone (can only reduce
  substep count relative to today's baseline, never increase it), and fully tested (unit tests for the
  scaling formula itself, a mocked substep-call-count reduction, and a checkerboard regression swept
  across `dt_ratio in [1.0, 0.5, 0.1, 0.01]`). **Real-world effect measured as negligible**: re-running
  the real May 2024 gauge-driven event to the observed peak at 90m resolution with only this change gave
  82,933 steps, CSI 0.133, ~23.6 min wall-clock - matching the unmodified baseline (82,933 steps, CSI
  0.133, ~22.7 min) to the step. The reason, found empirically rather than assumed: `dt` is rarely capped
  below `dt_cfl` during the fast/wet part of a real event (velocity itself, not an application-level cap,
  is what drives `dt` down there) - which is where most of a real event's runtime is actually spent.
- **(b) Relaxing `_MAX_STABLE_SUBSTEP_FRACTION` from 0.01 to 0.02** (a global, dt-independent halving of
  the substep count for any given `outflow_fraction`): swept against both of `test_engine.py`'s
  calibrated synthetic checkerboard regressions (the varying-roughness grid and the flat-water control)
  and found safe with margin (0.02 passes both; 0.025 already fails the flat-water control). Combined
  with (a), this gave a **real, measured 1.85x speedup at 90m** (82,933 -> 90,620 steps, 22.7 -> 12.3 min
  wall-clock) and even a slightly *improved* CSI (0.133 -> 0.152) - a genuinely good result on the
  calibrated tests. **A visual check against the actual real gauge-driven scenario** (real terrain, real
  hydrograph, real outlet boundary - specifically run because a synthetic-only metric had already been
  flagged as insufficient to trust alone) **showed a real, visible mottled/branching artifact** appearing
  around step 60,000, absent from the pre-fix baseline at the same step. Isolated via a controlled
  ablation (re-running the identical real scenario with only the substep fraction varied): 0.02 alone
  reproduces the artifact; 0.01 alone (with (a)'s dt-scaling still applied) is clean and numerically
  matches the pre-fix trajectory closely. **Reverted to 0.01** - neither calibrated synthetic test (both
  small, idealized grids: a smooth radial bowl and a perfectly flat plane) reproduces whatever real
  terrain, sustained real boundary inflow through a few channel cells, and real heterogeneous roughness
  over tens of thousands of steps does that triggers this specific instability.

**Conclusion - a negative result, not abandoned work:** neither change survives as a validated
performance fix. (a) is correct, safe, and kept (harmless, mathematically exact, fully tested) but
delivers no measurable win. (b) delivered a real win but isn't safe on real data. The wet/fast-flow,
CFL-uncapped regime - which dominates a real multi-day event's runtime - remains the actual unaddressed
bottleneck; closing the gap to TCC1's cited performance class (Jamali et al., Torres et al.) is still
open work for a future roadmap-step-11 pass. **This also flags a real gap in this project's own testing
methodology, not just the engine**: `test_engine.py`'s existing checkerboard regressions, though useful
and worth keeping, are not sufficient evidence of real-world numerical stability on their own - they
missed a failure mode a single visual check against real data caught immediately. Future numerical-
stability changes to `simulation/engine.py` should include a real-terrain check (not just the two
synthetic grids) before being considered validated, not as an afterthought.

**Addendum (later session): a corrected runtime estimate, and a real file-collision bug fixed.** The
full 14-day, 30m-resolution gauge-driven run's wall-clock estimate was revised sharply upward: earlier
framing put it around ~9 hours, but direct measurement on the committed ROI put the real figure closer
to **45–49 hours** — the ~9h figure was itself an underestimate, not a target this section's negative
results failed to reach. This doesn't change the diagnosis above (`dt` is correctly CFL-adaptive; the
substep decomposition remains the identified, unresolved bottleneck) or its conclusion — GPU/CuPy
remains the only untested lever, scheduled for Q10 (October) per TCC1's own Quadro 7, not attempted in
this session. Separately, a real bug was found and fixed while working in this area:
`examples/benchmark_30m_gauge_driven.py` was silently overwriting the 90m validation flood-extent mask
(`lajeado_flood_extent_90m.tif`) under the same filename convention `validate_may2024.py` uses, because
both ultimately call `build_observed_flood_mask` with only `reference_path` overridden. Fixed by giving
the 30m path its own distinct constant, `settings.FLOOD_EXTENT_PROCESSED_PATH`
(`lajeado_flood_extent.tif`, no `_90m` suffix, mirroring the existing
`DEM_PROCESSED_PATH`/`LANDCOVER_PROCESSED_PATH` no-suffix-means-30m convention) — verified no collision
regardless of run order.

---

## 14. Not yet built, relative to TCC1's stated plan (as of this session)

- **RMSE validation metric (depth vs. HWM/SWOT points)** — TCC1's other core validation metric alongside
  CSI (section 12 above). Deliberately deferred, not attempted in step 10: the only real HWM data found
  is a CPRM PDF technical report (`nota_tecnica_levantamento_cheias_2024_rs.pdf`, a statewide May-2024
  survey) with no confirmed structured/tabular extract for this project's small Lajeado/Estrela ROI
  specifically. Extracting a clean point dataset from it (or sourcing SWOT points instead) is future
  work, not blocking step 10's CSI deliverable. *(Since closed, not pursued: see §20 - documented as a
  data-availability limitation.)*
- **GPU/CuPy performance benchmarking** — TCC1's stack rationale names CuPy-compatibility as a design
  goal; the NumPy code has been kept vectorized/CuPy-compatible throughout, but nothing has actually
  been run on a GPU yet. *(Since done, first pass: see §18 - CuPy is kernel-launch-bound on this
  project's grids, 5x slower at 90m and ~2x faster at 30m; a fused-kernel substep is the open follow-up.)* Roadmap step 11 (see section 13 above for the CPU-side investigation attempted
  first, which found the real bottleneck is the substep decomposition, not something GPU parallelism
  alone would fix, given it's dominated by the same fixed-count sequential dependency regardless of
  where each pass executes).
- **Persisting `H[t]` frames to disk** — named explicitly in TCC1's data-flow diagram, not built (see
  section 5).
- **Base64 PNG frame encoding** — named explicitly in TCC1's data-flow diagram, not built; JSON arrays
  + client-side rendering used instead (see sections 5-6).
- **Rainfall/volume config-panel input** — named explicitly in TCC1's frontend section, deliberately
  deferred pending an advisor conversation about scope (see section 9).
- ~~**Neighborhood-type (Moore/von Neumann) toggle**~~ — named explicitly in TCC1's frontend section.
  *Since built for the temporal engine (§22); Moore remains the validated default.*
- **Automated pytest suite (70 tests across engine/ingestion/validation/API, as of step 10)** — not something TCC1
  describes at all; TCC1's own informal PoC validation was print-statement/manual-inspection based
  (Quadro 6's metrics table). Worth mentioning in the write-up as a methodological upgrade in TCC II
  over TCC1's own informal validation approach, not a deviation in the "diverged from the plan" sense.

---

## 15. Outlet-margin sensitivity investigation (exploratory, step 10 follow-up) — a negative result

**Context, not itself a TCC1 comparison point**: step 10's real CSI score (0.133) reflects a simulation
that under-predicts flood *width* — a narrow channel-hugging plume against a much wider real observed
floodplain — with the outlet boundary condition's fixed drainage margin (section 11 above,
`_CHANNEL_ELEVATION_MARGIN_METERS`, used as `find_boundary_outlet`'s `drop_m` default) named there as a
real candidate contributor, alongside a separately-observed sensitivity of this validation to small
pixel-registration shifts (a 1-3 cell shift alone was independently found to move CSI from 0.133 to
0.279). This section tests the drainage-margin half of that explanation as an isolated variable.

**What was tested**: `find_boundary_outlet` already exposes `drop_m` (how far below its own elevation
each outlet cell's "virtual outside" sits — the actual head difference driving outflow through the
outlet) independently of `margin_m` (which boundary cells count as "channel" at all). `drop_m` was swept
across `{0.01, 0.5, 1.0, 2.0 (current default), 5.0, 10.0, 20.0}` at 90m resolution via new, additive
`--outlet-drop-m`/`--results-json`/`--save-masks` CLI flags on `examples/validate_may2024.py` (all
default to exactly today's behavior when omitted — no change to any live default constant), with
`margin_m` and every other parameter (Manning's `N`, `outflow_fraction`, resolution, ROI) held fixed so
the exact same set of outlet cells was used in every run.

**Result — CSI is essentially flat across the whole range**: 0.13327 (0.01/0.5/2.0/10.0m, an exact
four-way tie), 0.13315 (1.0/5.0m, an exact tie one step lower), and 0.13411 at the 20.0m extreme — a
total spread of **0.00096** across a 2,000x range of the lever itself, from a near-zero/no-drainage
extreme to 10x the default. Hit Rate is bit-for-bit identical (0.1793020457280385) in *every* variant:
the outlet only ever touches a handful of south-edge channel cells, so it can shift a few marginal cells
between False Positive/Negative, but the narrow simulated plume's own True Positive footprint — the
actual real-flooded cells it does reach — never changes at all. This directly confirms the modeling
diagnosis: the drainage margin governs how much water reaches the outlet, not how *wide* the plume gets
on the way there, so it was never going to be the lever that closes the width gap.

**Noise-floor check (required before trusting any apparent win, and none was found)**: the shift-search
cross-correlation method (shift the simulated mask by every `(dy, dx) ∈ [-3,3]×[-3,3]`, recompute CSI at
each offset, keep the best) was re-run against both the default (2.0m) baseline and the nominal
best-scorer (20.0m). Both show closely matching shift-sensitivity: 2.0m goes 0.1333 → 0.2792 (+0.1459) at
`(dy=-1, dx=-3)`; 20.0m goes 0.1341 → 0.2773 (+0.1432) at the identical offset — reproducing the
earlier-reported 0.133 → 0.279 jump closely enough to confirm this is the same effect, not a different
artifact. **The entire margin-driven CSI spread (0.00096) is roughly two orders of magnitude smaller than
what a single small registration shift alone produces (+0.14-0.15) on this exact setup.** This is the
key methodological point worth stating plainly, not as a caveat: for this thin, sparse flood mask at 90m
resolution, small-scale registration/alignment noise is a *larger* source of CSI variance than a real
physical parameter's entire plausible range — a future reader comparing CSI values from this validation
across any single-parameter change should treat differences well under ~0.1 as statistically
indistinguishable from alignment noise, not as evidence the change mattered.

**Conclusion — a valid negative result, not escalated**: per this task's own stopping rule, no variant
cleared the noise floor, so no live default constant was touched (the CLI flags are purely additive to
an existing example script), and the investigation was not escalated to ROI widening or finer resolution
even though the result was inconclusive-by-itself for the width under-prediction question — both remain
legitimate directions for separate future work, deliberately not attempted here. `.venv/bin/pytest tests/`
passes unchanged (84/84) since no default behavior changed.

---

## 16. May 2024 CSI validation — full investigation of the CSI 0.133 under-prediction (step 10 follow-ups, several sessions)

**Context.** Step 10's original result (`docs/project-plan.md`'s "Step 10 done") was **CSI 0.133 / Hit
Rate 0.179 / FAR 0.658** at 90m resolution, default/uncalibrated parameters, scored against SGB/CPRM's
`COTA_3367cm` reference flood polygon for the real May 2024 event. This section is a single consolidated
account of everything investigated since then, replacing several sessions' worth of incremental
"continuation" entries that had made it hard to follow. It is organized by explanation, not by session:
what was ruled out, what the real cause turned out to be, how it was corrected, what physical lever was
separately calibrated, and where the search for better reference data landed.

### 16.1 Six alternative explanations ruled out, each with direct evidence

1. **CRS/coordinate/projection bug** — ruled out. The simulated grid and the reference mask are
   byte-identical in CRS, affine transform, and shape.
2. **Rasterization/indexing bug** — ruled out via two direct tests: a pixel-alignment check (exact match
   across sample points) and an `all_touched` sensitivity check (a real effect on cell count, but roughly
   10x too small in magnitude to explain the CSI jump the shift-search noise-floor check in §16.3 finds).
3. **Outlet drainage margin** (`_CHANNEL_ELEVATION_MARGIN_METERS`) — ruled out; see §15 above (a 200x
   sweep, Hit Rate bit-for-bit identical at every value tested — this lever only touches a handful of
   boundary cells and cannot affect which real flooded cells the model reaches).
4. **Clock-time-cutoff artifact** (the model stopping before reaching the real peak stage) — ruled out
   via gauge-cell WSE tracking. The real gauge (ANA station `86879300`, "ESTRELA") was geolocated via
   ANA's public `HidroInventario` API (lat `-29.4717`/lon `-51.965`) and inverted through the validation
   grid's affine transform to grid cell row 20/col 26 (`Z=16.0m`) — now
   `settings.VALIDATION_GAUGE_ROW`/`VALIDATION_GAUGE_COL`, so this doesn't need re-deriving from a
   scratchpad script again. The DEM-vs-gauge vertical datum is separately confirmed unresolvable (ANA's
   published station `Altitude`, `-0.6m`, is implausible against local channel-bed elevations), so only
   relative, same-run WSE dynamics are trustworthy, not absolute stage comparisons. An initial read using
   windows too fine (tens of minutes) misread short-term noise as a plateau; corrected with five ~5.3-hour
   windows across the last 20% of elapsed time, the gauge-cell WSE was still actively, monotonically
   rising — not settling — when the run stops at the real peak's elapsed time. Not a timing-cutoff
   artifact.
5. **Initial condition (dry-grid start, `H=0`)** — ruled out. Seeded `H` with a physically-derived
   baseline depth from Manning's equation using the pre-flood baseline discharge (2,251.8 m³/s, the flat
   period before the rise), deliberately avoiding the unresolved vertical datum from (4). The seeded
   volume was ~0.15% of total event inflow and washed out well before the peak — negligible effect.
6. **Depth-classification threshold** (`_FLOODED_DEPTH_THRESHOLD_M`) — ruled out via depth histograms of
   false-positive vs. true-positive cells: statistically indistinguishable (both median ~9–10m deep),
   ruling out "shallow edge cells" as the FP mechanism.

### 16.2 The real finding: a reference-data scope gap, not a model error

False-positive cells were concentrated in a large, contiguous, terrain-consistent region — elevation-
identical to the correctly-matched true-positive band — that turned out to be **Estrela's side of the
river** (the ROI straddles Lajeado and Estrela). A stage-invariance test confirmed this directly:
querying three SGB stage layers (`COTA_1900cm` 19.00m near-baseflow, `COTA_2600cm` 26.00m mid,
`COTA_3367cm` 33.67m peak), the same 48 cells on Estrela's side are flooded-or-not identically at every
one — that side is frozen at "permanent channel only" in the reference data, regardless of real water
level, while Lajeado's side grows normally across the same three stages (106 → 430 → 783 cells).

**Root cause, confirmed via external research**: SGB's flood-alert modeling system for this reach was
specifically commissioned for **Lajeado** municipality — built from Lajeado's own bathymetric
cross-sections and aerial photogrammetry, calibrated against Lajeado-side flood records from 2007–2024.
Estrela's DEM was used only as a supporting terrain input, never independently validated as its own
flood target. This explains both the service's naming (`SGB_LAJEADO_MAPSERVER_URL`) and its behavior
precisely — a genuine reference-data scope limitation, not a project or modeling error.

**A labeling bug, caught and corrected before being trusted.** An early version of this diagnosis had
the Lajeado/Estrela labels swapped, due to a calibration bug in `check_riverbank_coverage.py`'s
bank-identity logic against the real ANA gauge cell (it assumed the gauge cell's own side was Estrela's,
when the gauge actually sits on Lajeado's bank — Estrela is the side *opposite* the gauge). The same swap
was duplicated into `rescore_stage_invariant.py`'s own bank classifier, which uses the label to decide
*which* side's cells get excluded, not just which name gets printed, making this a real risk of a
substantive bug rather than a cosmetic one. Both were corrected; the "before/after" scores were
numerically identical only by coincidence (a double negation in the original code happened to cancel out
to the physically correct side despite the wrong label) — this was not taken on faith but independently
audited: the bank split was recomputed fresh from the corrected label and cross-checked cell-for-cell
against `check_riverbank_coverage.py`'s own independently-derived figures (2,280 of 3,073 domain-wide
frozen-dry cells on Estrela's side, matching exactly).

**A degenerate correction, tried first and explicitly rejected.** Excluding *every* stage-invariant cell
domain-wide (not scoped to Estrela) looks like the natural generalization, but is mathematically
degenerate: SGB's three stage layers turn out to be perfectly nested (a cell flooded at a lower stage is
always flooded at every higher one), so "frozen across all three stages" and "dry at the peak stage" are
the *same set* under nesting — meaning the domain-wide valid mask can never contain a cell that is both
valid and observed-dry, forcing False Positives to exactly zero at every parameter value regardless of
how the simulation actually performs (confirmed: domain-wide-corrected FAR is `0.0000` and CSI equals
Hit Rate bit-for-bit everywhere). This is a mask-construction artifact, not a usable correction, and is
recorded here so it isn't rediscovered by a future pass at this same dataset.

**The real, usable correction — disaggregated into two independent parts, not bundled.**
1. **Estrela-gap-only**: excludes only the 2,280 confirmed Estrela-side frozen-dry cells (the real
   coverage gap). This is the clean, independently-verified, bank-specific correction.
2. **Bundled**: the above *plus* a separate, non-bank-specific removal of all 154 domain-wide
   frozen-flooded (permanent-channel) cells — of which the majority (106, 68.8%) actually sit on
   **Lajeado's** side, not Estrela's. Bundling this in removes real True Positive credit without
   addressing the coverage gap, and was found to *understate* the correction at the calibration
   plateau's peak (`0.878` vs. the properly-isolated `0.900`) and to fabricate an apparent regression at
   the documented default that isn't real. **Estrela-gap-only is the number to cite; bundled is reported
   alongside it for transparency, not used as "the" correction.**

Visual confirmation (`rescore_stage_invariant.py --out-png`): under the Estrela-gap-only mask, the
observed and simulated flood panels are visually near-identical within the valid region, with a clean,
thin fringe of false negatives/positives tracing the boundary of a large solid true-positive mass —
categorically different from the naive metric's confusion map, which shows a single, large,
geographically distinct FP blob entirely separate from the true-positive band (the same blob a separate
diagnostic, `characterize_fp_region.py`, first isolated as a possible coverage question, now confirmed
to be the Estrela gap directly).

### 16.3 A second, real lever: `outflow_fraction` (interior redistribution rate)

`outflow_fraction` (hard-coded `0.5` in every caller — `step()`'s default, `validate_may2024.py`'s base
value — never tuned against real event data, originally chosen only for numerical stability during early
development) turned out to be non-monotonic with CSI, with a real interior maximum. A broad sweep
followed by a two-stage densification localized a **broad, flat plateau in `[0.07, 0.1]`**, nominal peak
at **`0.085`**.

**Mechanism**: the default (`0.5`) redistributes water toward the outlet too quickly, producing a
narrow, channel-hugging plume that misses most of the real floodplain (low Hit Rate, high FN). Slower
redistribution lets water pool and spread laterally before draining — closer to what the real event's
width required. Below the plateau (toward `0.05`), the plume overshoots the real floodplain boundary
instead (Hit Rate climbs to `0.988`, but simulated extent balloons to 57.7% of the ROI against the real
21.3%, so FP growth outpaces the recall gain and CSI turns back down).

**Confirmed clean, not a stability/accuracy tradeoff**: checkerboard roughness (the same metric
`test_engine.py`'s regressions use) is *lowest*, not highest, at the better-scoring, low-`outflow_fraction`
end — the better-scoring variants are also the more numerically stable ones. A visual check of every
swept variant's depth field found smooth, coherent plumes with no checkerboard/mottling artifact anywhere
in the range.

**Noise-floor checked at `0.085`** (the shift-search cross-correlation method: shift the simulated mask
by every `(dy,dx) ∈ [-3,3]×[-3,3]`, recompute CSI, keep the best): shift-sensitivity is `+0.0000` — the
raw score is not improved by any registration shift at all, the single most registration-robust point
found anywhere in this whole investigation.

Rescoring the same 13-point sweep (already on disk, no new runs) under naive vs. Estrela-gap-only vs.
bundled scoring:

| `outflow_fraction` | naive CSI | **Estrela-gap-only CSI** | bundled CSI |
|---|---|---|---|
| 0.05 | 0.363 | 0.848 | 0.819 |
| 0.07 | 0.390 | 0.891 | 0.868 |
| **0.085** | 0.395 | **0.900** | 0.878 |
| 0.1 | 0.390 | 0.870 | 0.841 |
| 0.115 | 0.383 | 0.836 | 0.800 |
| 0.13 | 0.374 | 0.800 | 0.755 |
| 0.15 | 0.358 | 0.754 | 0.699 |
| 0.2 | 0.323 | 0.662 | 0.588 |
| 0.3 | 0.221 | 0.406 | 0.314 |
| 0.5 (previous default) | 0.133 | 0.179 | 0.059 |
| 0.6 | 0.113 | 0.139 | 0.018 |
| 0.7 | 0.110 | 0.128 | 0.010 |
| 0.8 | 0.101 | 0.116 | 0.006 |

`0.085` remains the top scorer under both naive and gap-only scoring — the correction doesn't shift
which value is best, it widens the separation from its neighbors into a clearer peak (naive top-3 spread
`0.0054`, within this validation's own noise floor; gap-only top-3 spread `0.0299`, a real widening). The
Estrela-gap-only correction is uniformly non-negative at every swept point (it can only remove potential
FPs, never TP/FN credit), so there is no two-sided finding here once bundled and gap-only are properly
separated.

### 16.4 Final result

At `outflow_fraction=0.085` (confusion counts TP=789, FP=1167, FN=42 naively): naive CSI is **0.3949** —
already a 3x improvement over step 10's `0.133` from calibration alone. Applying the Estrela-gap-only
correction (FP drops from 1167 to 46; TP/FN untouched, since a dry-cell exclusion can only remove
potential false positives) gives **CSI 0.8997** — the number to cite as the validated result.

**Adopted as the live default.** This calibration decision has now been implemented:
`outflow_fraction=0.085` is the deployed default in `step()` (`simulation/engine.py`), `POST
/simulations` (`api/routers/simulations.py`), and the frontend's `ConfigPanel` initial value —
replacing the old, never-tuned `0.5` everywhere it operated as the assumed live value, including the
one-off `examples/benchmark_30m_gauge_driven.py` script. `examples/validate_may2024.py` deliberately
keeps its own `base_outflow_fraction=0.5` default (its `--outflow-fraction` flag already makes it
independently overridable) so an unflagged run continues to reproduce the original step-10 baseline
for comparison, rather than silently drifting to a different number. `.venv/bin/pytest tests/` passes
84/84 unchanged after the flip — every test that calls `step()` without an explicit
`outflow_fraction` asserts a property (mass conservation, non-negative depth, a checkerboard-roughness
threshold, directional-steering ratios) that holds for any valid fraction, not a value pinned to the
old default. No other parameter (Manning's `N`, the outlet drainage margin, resolution) was touched.

### 16.5 Search for independent Estrela-side reference data

Given the reference-data limitation in §16.2, five independent sources were checked for real flood-extent
coverage of Estrela's side, in order:

1. **Copernicus EMSN194** (Risk & Recovery Mapping, requested by UFRGS) — ruled out. Covers the Porto
   Alegre/Canoas metro area, ~94km from the ROI, zero overlap.
2. **Copernicus EMSR720** (Rapid Mapping, statewide RS floods activation) — ruled out. All 5 AOIs are
   upstream in the Serra Gaúcha (Guaporé, Encantado, Roca Sales, Santa Tereza, Das Antas Dam), closest
   ~17.6km away, zero overlap.
3. **Copernicus Global Flood Monitoring** (GFM, automated Sentinel-1-based, global archive since 2015) —
   checked, no usable coverage/signal found for this reach.
4. **SWOT satellite** (NASA/CNES) — the one source that worked. A Raster granule from pass 014/533
   (6 May 2024, UTM zone 22J) geometrically covers the full ROI including Estrela. Reprojected onto the
   project's 90m grid, Estrela-side `water_frac` shows real, non-frozen variation (mean 0.274, std
   0.294, 18.9% classified wet at >50% threshold) — comparable in magnitude to Lajeado's in the same
   pass (mean 0.250, 15.1% wet), corroborating that Estrela genuinely experienced flooding of a similar
   order rather than the CA model over-predicting there.
5. **Related literature**: the paper cited in this project's own TCC1 (Sales et al. 2025) turned out to
   be about point-level SWOT virtual gauging stations, not extent mapping. Two more directly relevant
   2025 papers were found (Simoes-Sousa et al., WHOI/GRL, with a public Zenodo dataset; Laipelt et al.,
   GRL, co-authored by the same IPH-UFRGS researchers — Collischonn and Ruhoff — behind SGB's own Lajeado
   product) — the successful SWOT raster check traces to this lead.

**Caveats, stated plainly**: most of the Estrela-side SWOT signal is flagged "suspect" quality (81.6%)
rather than "good" (3.6%) per the product's own quality metadata, and the usable pass is 6 May — four
days after the 2 May peak (recession limb), not a peak-stage comparison.

**Decision**: SWOT is adopted as corroborating evidence for the discussion/limitations narrative
(independent confirmation that Estrela flooded, supporting the reference-data-gap interpretation over a
model-over-prediction interpretation) — **not** integrated as a formal secondary CSI metric. The cost of
building quality-flag-aware masking and formal temporal-mismatch handling for a single suspect-quality,
off-peak pass was judged not worth what it would add. This closes the search for alternative reference
data: five independent sources checked is a thorough, documented search, not an abandoned effort.

---

## 17. Planned architectural direction: hybrid temporal + non-temporal engine (not yet implemented)

**Context**: following the runtime and CSI difficulties above (§13, §16), a hybrid direction was decided
for the engine's future architecture — this is a design decision made this session, not implemented
code, and should not be read as a completed step.

**Direction**: keep the existing temporal, CFL-based CA engine as the core model. It is the project's
differentiator against Torres et al. 2022's non-temporal classification approach — it captures wave-front
arrival timing, which a non-temporal model cannot — and stays the primary validated model. Alongside it,
add a second, separate, explicitly-labeled **non-temporal fast classification mode** (Torres-style
elevation-ordered classification), documenting the speed/accuracy trade-off between the two rather than
replacing the temporal model with the faster one.

**Status**: design-stage only. Not implemented, not yet assigned to a specific roadmap step — noted here
as planned future work so it isn't lost between sessions. *(Since implemented, first pass: the
Torres-inspired non-temporal mode is `simulation/fast_engine.py` - see §19 for its first real result.)*

---

## 18. GPU/CuPy portability — first measurement, and the runtime side of the `0.085` default (step 11, Q10)

**TCC1:** the stack rationale names CuPy-compatibility as a design goal, and TCC1's own Quadro 7 schedules
GPU work for Q10 (see §14). Until this pass nothing had run on a GPU. This section answers one question:
does swapping NumPy for CuPy meaningfully speed up the engine? It first re-baselines under the `0.085`
default adopted in §16.4, so a runtime change from that calibration isn't misattributed to the GPU.

**Setup.** Real May 2024 gauge-driven scenario (real terrain, roughness, hydrograph and outlet), run to
the real observed peak, measured with a new parameterized runner, `examples/benchmark_backends.py`
(`--resolution 30|90`, `--outflow-fraction`, `--backend numpy|cupy`, `--max-steps`, `--assert-every`).
Hardware: i7-13620H (NumPy), RTX 4050 Laptop GPU, 6 GB (CuPy 14.2 / CUDA 13, float64). Timings were
taken uncontended and repeated (repeats agree within ~5%). Concurrent GPU/CPU jobs on this hybrid-core
laptop were found to slow a background NumPy run ~3x, so no two benchmarks were run at the same time.

**Phase 1 — the `0.085` default alone (NumPy, 90m, to the peak):**

| | `0.5` (previous default) | `0.085` (live default) |
|---|---|---|
| macro steps to the peak | 82,936 | 134,639 (1.62x) |
| substeps per macro step | 50 (every step) | 9 (every step) |
| per-step wall-clock (p50) | 16.6 ms | 3.3 ms (~5x cheaper) |
| **wall-clock to the peak** | **23.3 min** | **7.6 min (3.1x faster)** |
| naive CSI (reproduces §16.3's table) | 0.133 | 0.395 |

- The step count still reproduces the documented baseline (82,936 vs. step 10's 82,933; CSI 0.133). The
  naive confusion counts at `0.085` reproduce §16.4 to one cell (TP 789, FP 1,166 vs. 1,167, FN 42). That
  one-cell difference is consistent with the ulp-level sensitivity described below.
- **Why 3.1x rather than the 5.5x fewer substeps suggests**: this is §16.3's own mechanism seen from the
  runtime side. Slower redistribution lets water pool and spread laterally instead of rushing down the
  channel to the outlet, so the grid holds more water (`H.sum()` at the peak is 8.5x higher). Deeper water
  flows faster, and CFL `dt` (`compute_stable_dt`, independent of `outflow_fraction`) shrinks. That costs
  1.62x more macro steps, but each is ~5x cheaper.
- **This is not an over-flooding artifact.** The naive False Positive count (1,167) is almost entirely
  the Estrela reference-data gap (§16.2). After the Estrela-gap correction the real over-prediction is a
  modest **46 cells**, and the validated CSI is **0.8997** (§16.4). So the extra retained water is the
  model reaching floodplain the step-10 default never reached (genuine under-spreading fixed), plus a
  reference gap that has been resolved. It is not the model inventing flood extent.
- A real-terrain visual check (§13's rule) of H snapshots at steps 20k-80k and at the peak agrees with
  §16.3's: smooth, coherent flood fields, no speckle/mottling. Among fully-wet interior cells, the
  fraction that is an isolated local depth extremum is 18.7% at `0.085` vs. 28.5% at `0.5`.
- At 30m, only a 2,000-step sample was measured: 143 -> 31 ms/step (4.6x per step), against the
  45-49 h full 14-day 30m runtime at `0.5` recorded in `docs/project-plan.md`.

**Phase 2 — CuPy.** `simulation/engine.py` is now array-backend-agnostic: `_array_module(a)` returns CuPy
for CuPy arrays and NumPy otherwise, and CuPy is imported only when a CuPy array is actually passed in,
so it stays an optional dependency (installed ad hoc, not in `requirements.txt`). The NumPy path was
verified bit-identical (`H` and `dt`) to the previous engine over 2,000 real steps. It is not wired into
the API.

| per-step p50, `outflow_fraction=0.085` | NumPy | CuPy |
|---|---|---|
| 90m (3,904 cells) | 3.2 ms | 16.5 ms (**5x slower**) |
| 30m (35,136 cells) | 31 ms | 15.9 ms (**~2x faster**) |

- **Launch-bound, not compute-bound**: CuPy's ~16 ms/step is flat across a 9x change in grid size. One
  macro step is ~9 passes of ~80 small elementwise kernels. Per-step host syncs (`dt`'s `float()`,
  validation `any()`s, mass-balance sums) cost only ~4% (measured with `--assert-every 1000`). GPU memory
  use is under 8 MB. Every NumPy op used had a direct CuPy equivalent, so no op needed a workaround.
- **Numerical parity, and a finding about the engine itself**: from an identical input state a CuPy step
  is bit-identical to NumPy's. Free-running trajectories nonetheless separate by ~0.2 m within ~50 steps,
  starting from a single-ulp difference in `dt`. **The same divergence appears NumPy-vs-NumPy when `H` is
  perturbed by one ulp** (8.8 mm after one step, ~0.2 m within 50), so this is the engine amplifying
  ulp-level noise, not a GPU bug. The likely mechanism: weights are `sqrt(slope)/n` (infinite derivative
  at zero slope), normalized, with a release amount that doesn't depend on slope magnitude. On near-flat
  water, ulp-scale drops redirect a cell's whole release. Cross-backend (or cross-machine) parity
  therefore has to be judged on outcomes (wet mask, CSI, step count), not `allclose` on `H`. Wet masks
  matched exactly over 2,000 steps.

**Conclusion.** Phase 1's calibration is the real runtime win on this project's grid sizes (3.1x at 90m).
A naive NumPy -> CuPy array swap adds nothing at 90m and ~2x at 30m, which does not justify a full
migration or live-API integration as-is. The GPU follow-up worth trying is a fused single-kernel substep
(one CuPy `ElementwiseKernel`/`RawKernel` per pass), which targets the launch overhead that dominates
here. It is relevant only at 30m or finer.

---

## 19. Torres-inspired non-temporal fast mode — first result (hybrid architecture, §17)

**TCC1:** the literature review cites Torres et al. (2022) as the closest methodological match and
frames this project's time-stepped engine as that approach "extended to be time-stepped" (see
`docs/tcc-summary.md`). §17 decided to build the non-temporal counterpart as well, as a second,
explicitly separate mode, so the speed/accuracy trade-off between the two could be measured rather
than asserted. This section is that measurement.

**Inspiration, not a reproduction.** The general approach follows Torres, Chávez-Cifuentes & Reinoso
(2022), "A conceptual flood model based on cellular automata for probabilistic risk applications",
*Environmental Modelling & Software* 157:105530. Its public abstract describes a top-down evaluation of
flow through DEM cells under a Moore neighbourhood, with cells classified into four dynamic states, each
with its own rule. The paper's own state definitions and rules are behind a paywall and were not
available, so the rule set below is this project's own design, consistent with that description. It is
labelled "Torres-inspired" everywhere. **No numerical comparison with Torres et al.'s reported results is
made anywhere**: the comparison is against this project's own temporal engine on the same real data.

**Design** (`backend/simulation/fast_engine.py`, `classify_steady_flood`). Dependency-free like
`engine.py`, and imports nothing from it.
- **Forcing: steady peak discharge.** It uses the real hydrograph's discharge at the observed peak,
  23,472 m³/s, the same value the temporal engine injects at that moment. There is no `dt`, no CFL and
  no time integration. A total volume would not work as the forcing: the domain has a real outlet, so a
  volume routed downhill simply drains out. Conveyance is what sets extent for a through-flowing river.
- **Outlet-conditioned routing surface.** The first implementation retained 100% of the discharge after
  10 cells. `ingestion/dem.py`'s sink filling guarantees a non-ascending path to *some* border cell,
  but the domain is walled everywhere except the outlet, so the river's own path dead-ended.
  - Fix: route over a surface re-filled by a priority-flood (Barnes et al. 2014, the step-3 algorithm)
    seeded from the outlet cells only. At steady state under continuous inflow, a depression on the
    flow path is full to its spill level.
  - Routing follows the flood's own visitation order reversed: top-down, from the cells farthest from
    the outlet. Every reachable cell therefore provably has a downstream path out.
- **Routing pass.** Each cell splits its discharge among downstream Moore neighbours by `sqrt(S)/n_dest`,
  the same weighting and convention as `engine._single_update`.
- **Four states:**
  - **CONVEYING:** carries routed discharge. Its water surface is the conditioned elevation plus the
    Manning normal depth `h = (Q·n/(w·√S))^(3/5)`, with `w = dx`, as in `compute_stable_dt`.
  - **EXITING:** a conveying cell that discharges through the outlet.
  - **INUNDATED:** carries no flow, but its terrain is below the water surface of the conveying cell its
    steepest-descent path first reaches. This is a HAND-style lateral backwater rule.
  - **DRY:** everything else.
- **Invariant:** discharge continuity, `outflow + retained == inflow`, is this mode's analogue of mass
  conservation. On the real grid it holds exactly: 23,472.370 m³/s out, 0 retained.
- **Slope floor.** Slope is floored at `_MIN_SLOPE = 1e-4`, the order of large lowland river bed
  slopes, because the conditioned surface has flats where Manning depth would diverge.

**Result** (90m, May 2024 observed peak, `examples/fast_mode_may2024.py`). Temporal figures are §16.4 and
§18 at `outflow_fraction=0.085`:

| | fast (Torres-inspired) | temporal |
|---|---|---|
| naive TP / FP / FN | 731 / 2,109 / 100 | 789 / 1,167 / 42 |
| naive CSI | 0.249 | 0.395 |
| **Estrela-gap-only CSI** (§16.2 correction) | **0.531** | **0.900** |
| gap-only Hit Rate / FAR | 0.880 / 0.428 | 0.949 / 0.056 |
| gap-only FP | 547 | 46 |
| **wall-clock to a final extent** | **~74 ms** (median of 20) | **7.6 min** (§18) |

**About 6,000× faster, at a clearly lower accuracy.** Hit rate is only slightly lower (0.88 vs 0.95):
the fast mode finds most of the real floodplain. The gap is almost entirely over-prediction: 547 real
false positives against the temporal engine's 46. A visual check of the depth and state maps shows a
coherent result: the conveying path traces the real channel from the north inflow to a single exiting
cell at the south outlet, with no speckle or artifacts. The errors have a physically interpretable
pattern:
- **Upstream over-prediction.** Up a north-western side valley, the lateral rule carries the
  high upstream water surface onto high ground. Only the ~106 conveying cells carry the discharge,
  while the real floodplain conveys too, so the steady Manning depth there is too high.
- **Downstream under-prediction.** The 100 false negatives are near the outlet. The real flood there
  is backwater-controlled from downstream, which a local, steady Manning rule cannot represent. This is
  exactly the "dynamic effects" regime where Torres et al.'s own abstract says conceptual models are
  weakest.

**Disclosed sensitivity: the slope floor dominates the result.** 103 of the ~106 conveying cells sit
on the `_MIN_SLOPE` floor, because the conditioned river path is almost entirely flat at 90m. So that
constant effectively sets the channel depth. It was fixed on physical grounds before seeing any score
and was not tuned. A one-off sweep, for disclosure only (hit rate stays 0.84–0.88 throughout; the floor
controls over-prediction):

| `_MIN_SLOPE` | 3e-5 | **1e-4 (used)** | 3e-4 | 1e-3 |
|---|---|---|---|---|
| gap-only CSI | 0.486 | **0.530** | 0.633 | 0.760 |
| flooded cells | 3,102 | 2,840 | 2,387 | 1,840 |

**Conclusion.** The hybrid architecture's premise holds for speed: this mode reaches a final extent in
under a tenth of a second on the 90m grid, which fits the "seconds, not hours" class TCC1 cites. On
accuracy it is a real step down from the calibrated temporal engine (0.53 vs 0.90 gap-corrected), for
two reasons: no backwater or dynamics, and a channel depth governed by an uncalibrated slope floor. That
fits the architecture's framing: a fast screening mode alongside the validated temporal model, not a
replacement.

The natural follow-up is to calibrate `_MIN_SLOPE` (or a floodplain-conveyance width in its place)
the way §16.3 calibrated `outflow_fraction`, using a sweep plus the §15/§16 noise-floor check. It was
deliberately not done here, so this first number stays uncalibrated and comparable. Regression-pinned
in `tests/test_fast_engine.py` (naive TP/FP/FN 731/2,109/100). *(Followed up in §23, which did not
calibrate the floor. The floor was standing in for the floodplain's missing conveyance width. A HAND
rating-curve depth rule replaced the one-cell-wide channel: gap-only CSI 0.53 → 0.896, untuned. This
section's rule is kept as `conveyance="single_cell"`.)*

---

## 20. RMSE against high-water marks — closed as a data-availability limitation

**TCC1:** the validation methodology (section 4.5.2) plans two metrics. CSI covers spatial extent
(implemented; see §12 and §16). RMSE covers vertical accuracy: simulated depth against observed
high-water marks (HWM) at point locations.

**Status: closed, not pursued further.** RMSE against HWM was not implemented, and this is now a
documented limitation rather than open work. **No structured or tabular HWM dataset exists for this
project's small Lajeado/Estrela ROI.** The only source found is a CPRM PDF technical report
(`nota_tecnica_levantamento_cheias_2024_rs.pdf`), a statewide survey of the May 2024 floods. It has no
machine-readable extract of point coordinates and water levels that could be joined to the simulation
grid. Building a point dataset by hand from a PDF would add manual-transcription error to a metric
whose job is to measure small depth errors, so it was not attempted.

The one independent source that did cover this ROI, a NASA/CNES SWOT raster pass (§16.5), gives
water *fraction* per pixel, not point water-surface or depth observations. It is also mostly
"suspect" quality, and it is four days after the peak. So it cannot stand in for HWM in an RMSE either;
it is used only as corroborating evidence for the extent narrative.

**Consequence for the write-up:** validation in this project is extent-only (CSI, with Hit Rate and
False Alarm Rate), and vertical accuracy is not quantified against observations. This should be stated
as a data-availability limitation of the study area, not as a methodological choice. `validation/`
therefore implements only the extent metrics; no RMSE code exists or is planned.

---

## 21. Fast mode in the live API — one frame on the existing stream, and a 90m grid option

**TCC1:** the planned architecture (§5/§6) is a REST call that starts a run, plus a WebSocket that streams
its frames. It predates the hybrid architecture (§17), so it says nothing about a mode with no time
steps. §19 validated the fast mode offline only. This section records how it was put into the app.

**Decision: a third `mode` on the existing contract, not a separate REST endpoint.**
`POST /simulations {"mode": "fast", "resolution": 30|90}` registers the run as before. Then
`WS /simulations/{run_id}/stream` sends **exactly one frame** (`step: 0`, the steady depth grid,
`peak_discharge_m3s`, `outflow_m3s`/`retained_m3s`, `flooded_cells`, `compute_seconds`) followed by
`{"done": true}`. A plain `POST /simulations/fast` that returned the depth grid directly was the
alternative. It would describe a timeless result more literally. It was not chosen, for these reasons:
- The API's shape is "validate and register, then consume once". Run-id lifecycle, single use, the
  4004 unknown-run close, `grid_shape`/`bounds` and the 503 when no hydrograph is loaded all carry over
  unchanged.
- A one-frame stream is already a valid case of the contract. A `seeded_pool` run with `steps=1` looks
  the same.
- The whole frontend pipeline consumes frames: the run state machine, the stream's error handling, the
  map overlay and the log. A REST endpoint would need a second fetch path and a second response type,
  and would buy nothing.

The cost is that a result with no time sits inside a "stream". The protocol states this explicitly:
`step: 0` and no `elapsed_time`. `volume` is still sent. It is the steady depth summed over cells, in
the same unit as the temporal frames, but here it is not a conserved quantity. The fast engine's own
invariant, discharge continuity, is asserted server-side as in `examples/fast_mode_may2024.py`. The
classification runs in a worker thread (`asyncio.to_thread`) because both of its passes are plain
Python loops.

**The live API now also serves the 90m validation grid (`resolution=90`), and gauge-driven runs can
`stop_at_peak`.** At 30m a temporal run needs hours to reach the May 2024 peak (§13/§18). The fast mode
models that peak. So without these two options, no temporal result you could place next to a fast
one in a browser session would be from the same moment. The 90m grid is built by the same
ingestion calls `examples/validate_may2024.py` uses. With both options, the app reproduces §19's
comparison live, on the same grid, at the same moment. 30m remains the default.

**The Estrela-gap correction (§16.2) is not applied in the API, deliberately.** It changes which cells
are *scored*, not the simulated extent, and the API does no scoring. The UI compares the two engines'
extents with each other (cells flooded in both / only one), not against the SGB reference. Putting CSI
in the UI, naive or gap-corrected, is a separate follow-up. The gap correction would first have to move
out of `examples/`, which `api/` may not import.

**Live results** (real servers, driven through a real browser):
- **Fast @ 90m**: 2,840 flooded cells, **exactly §19's naive TP + FP (731 + 2,109)**, so the API path
  reproduces the offline validation cell for cell. Continuity held: 23,472.4 m³/s out, 0 retained. The
  engine took ~0.16–0.33 s per request, against §19's 74 ms median of repeated in-process calls.
- **Temporal gauge-driven @ 90m, `stop_at_peak`**: reached the peak (133.5 h) at step **134,639** with
  **1,955** flooded cells. That is §18's exact step count and §18's naive TP + FP (789 + 1,166), so the
  API's loop reproduces the offline runner cell for cell. It took 20.4 min of wall-clock. §18 measured
  7.6 min uncontended, but in this session `benchmark_backends.py` itself measured ~17 ms/step against
  §18's 3.3 ms, so the difference is machine load, not the API.
- **Compare view, same grid, same moment:** 1,648 cells flooded in both, 1,192 fast only, 307 temporal
  only. The fast-only cells sit up the north-western side valley and on the eastern high ground, the
  lateral-rule over-prediction §19 describes. The temporal-only cells cluster around Estrela and the
  south outlet, the backwater-controlled flooding a local steady Manning rule can't represent. So the
  live view shows the same error pattern §19 found offline: 213 ms vs. 20 min to a final extent, and a
  visibly different extent.
- **Fast @ 30m (not validated against the reference)**: 13,987 of 35,136 cells flooded (39.8%),
  continuity exact, ~1–1.8 s of engine time. §19 was only ever scored at 90m. The 30m result has not been
  scored, and `_MIN_SLOPE`'s dominance (§19) may play out differently on the finer grid. Treat the 30m
  number as a working display, not a validated one.

**Also fixed while verifying this: temporal runs now stop when the client leaves.** Both temporal loops
now `await asyncio.sleep(0)` every engine step, and a watcher task notices the WebSocket disconnect. So
a stopped or abandoned run ends within one step. Before, it computed on until its next frame send, which
at 30m with `frame_interval=500` is over a minute. Other requests are also served during a long run,
not only between frames. This was step 9's documented "no yield points" limitation, and it became
blocking once a user could stop a gauge-driven run and immediately start a fast one: the fast run's
POST sat unanswered until the abandoned run's next frame. It is covered by
`test_stream_simulation_stops_computing_when_client_disconnects`. The per-step cost of the yield is
negligible against a 3–17 ms engine step.

**Follow-up: the fast overlay is drawn as extent only.** The UI now draws the fast mode's result in one
flat "flooded" color, and its legend says the depth is not calibrated. Only the temporal overlay uses the
depth ramp. Fast-mode depths are ~33–65 m, §19's steady Manning channel depth at the untuned
`_MIN_SLOPE` floor, against a ~20 m river rise. Only the fast extent was validated (§19), so shading
those depths would suggest a precision the engine doesn't have. The API is unchanged: the fast frame
still carries the depth grid, which is what `flooded_cells` and the agreement counts are computed from.
The same follow-up added a one-click "Replay May 2024 flood" preset. It runs this section's comparison
(fast, then temporal to the peak, on the 90m grid) exactly as scored above.

**Follow-up: a 60m grid option, unvalidated.** The API also serves a 60m grid (`resolution=60`). It is built
at startup by the same ingestion calls as the 90m one, and it sits between the other two in wall-clock cost.
The fast mode at 60m flooded 5,445 of 8,736 cells, with continuity exact. Like the 30m number above, this
result has not been scored against the SGB reference, so treat it as a working display, not a validated
one. Every validated figure in this document remains a 90m result.

---

## 22. Von Neumann (4-neighbor) option for the temporal engine — built, unvalidated, Moore stays the default

**TCC1:** the transition rule is documented over the 8-cell **Moore** neighborhood (`docs/tcc-summary.md`),
and TCC1's frontend section also names a Moore / von Neumann "neighborhood type" setting (§6, §14).

**What was built:**
- `step()` and `compute_stable_dt()` take `neighborhood="moore"` (the default) or `"von_neumann"` (the 4
  orthogonal neighbors).
  - The CFL search uses the same neighbors as the redistribution, so it only sees slopes water can
    actually flow down under that neighborhood.
  - `POST /simulations` exposes it for the temporal modes only. With `mode: "fast"` it is a 422, like
    the other temporal-only fields; the fast engine stays Moore-only.
  - The config panel has a Neighborhood toggle labelled "Moore (8 neighbors), validated" / "von Neumann
    (4 neighbors), not validated", with the note that the validated May 2024 results apply to Moore only.
  - The May 2024 replay preset sends `neighborhood: "moore"` explicitly.
  - Von Neumann is limited to `outflow_fraction ≤ 0.085`, the range where its numerics were measured
    as sound (see Stability below). The API rejects it above that, and the UI clamps and caps the input.
  - A von Neumann run is named on the temporal pane and in the log. Compare warns when the temporal run's
    neighborhood differs from the (Moore-based) fast engine's.

**Why the default is untouched, and how that was proved.** §18 found that the engine amplifies a single-ulp
difference into ~0.2 m within ~50 steps, so "unchanged" has to mean bit-identical, not `allclose`.
- **Construction:** the Moore path keeps the same offsets list in the same order, so it performs the same
  floating-point operations in the same order.
- **Regression test:** `tests/test_engine_regression.py` runs the live engine against
  `tests/engine_moore_reference.py`, a verbatim frozen copy of `engine.py` from before the change, checked
  with `diff`. Both are driven through the full gauge-driven macro step (CFL dt, 900 s cap,
  `outflow_fraction_for_dt`, boundary inflow, outlet). It asserts exact equality of `H` and `dt` at every
  step:
  - over 500 synthetic steps;
  - over 1,000 real May 2024 steps on the 90m grid;
  - both with no argument and with an explicit `"moore"`.

  A mutation check (only reversing the Moore offsets' order, i.e. the same math summed differently) fails
  it at step 2, with a 1.1e-16 difference.
- **Offline re-validation:** the May 2024 run to the peak (`validate_may2024 --outflow-fraction 0.085`) was
  run before and after the change:

  | | before | after |
  |---|---|---|
  | macro steps | 134,639 | 134,639 |
  | naive TP / FP / FN | 789 / 1,166 / 42 | 789 / 1,166 / 42 |
  | naive CSI | 0.3951 | 0.3951 |
  | Estrela-gap-only TP / FP / FN | 789 / 47 / 42 | 789 / 47 / 42 |
  | gap-only CSI | 0.8986 | 0.8986 |

  The final `H` arrays and the masks are identical (`np.array_equal`).
  - This reproduces §18's naive counts exactly.
  - §16.4's documented 0.8997 (FP 1,167 → 46) is the one-cell variant §18 already noted. It comes from
    before this change and does not come from it.

**Isotropy: what the 4-neighbor stencil does to the spread shape.** On a flat grid with a point source:
- **The stencil itself:** with one substep per step, water reaches exactly the L∞ ball (a square) under Moore
  and exactly the L1 ball (a diamond) under von Neumann after k steps.
- **The spreading front** (the tail at 1e-9 of the peak depth, 20 steps at the default):
  - Moore's contour is octagon-like: it fills 0.87 of its bounding square, with diagonal reach 0.75 of
    axial.
  - von Neumann's leans to a diamond: 0.65 and 0.64.
- **The bulk** (1% of the peak, 80 steps) is near-round under both (fill 0.77–0.80, a disc being 0.785). The
  engine's many substeps per step diffuse the stencil's anisotropy out of the core.
- So a von Neumann flood is diamond-like only at its fringe, not in its bulk. The tests assert the front
  difference and the round bulk, not a bulk diamond.

**Stability on real terrain (the §13 rule).** The substep fraction was not assumed from Moore's 0.01. The
question turned out to need a better method than §13's, and the answer depends on `outflow_fraction`.

- **1. Visual and scalar checks at the live default are clean, but they can't be trusted alone.**
  - At 0.01, von Neumann is visually smooth: 90m snapshots every 20k steps to the peak, a 30m 10k-step
    segment, and cell-level zooms, with no speckle, mottling or odd/even checkerboard.
  - Scalar metrics agree:
    - §18's isolated-extremum fraction is 0.16–0.24, against Moore's 0.19–0.29. Its definition was
      recovered by reproducing §18's 18.7% on the Moore peak: extrema over the 4 orthogonal neighbors,
      among cells with those neighbors wet (18.72%).
    - The orthogonal/diagonal deviation ratio, which rises for odd/even decoupling, is 0.66 for both.
  - **But the positive control failed.** Moore at 0.02, §13's known-bad setting, scores the same on every
    metric at the live default, and looks clean too. At `outflow_fraction=0.085` it is only 5 substeps per
    step, not the 25 of §13's `0.5` regime.
- **2. Step-matched snapshots compare different moments.** In §13's own regime (`outflow_fraction=0.5`),
  runs with different substep fractions take different dt trajectories. So "step 60,000" is 4.47 d in one
  run and 4.70 d in another.
  - The dendritic eastern tributary lobe that Moore 0.02 floods by 4.05 d also floods in the clean 0.01
    run, but between 4.70 and 5.10 d.
  - The real defect of 0.02 is flooding it about 0.7 d early. The "branching artifact at step 60k" of §13
    is partly a timing mismatch between the runs compared.
  - `examples/benchmark_backends.py` therefore gained `--snapshot-days`/`--stop-days` (time-matched
    snapshots) and `--perturb-ulp`, a noise-floor control that nudges the deepest cell by one ulp after
    step 1.
- **3. The test that works: convergence in the substep fraction, at matched simulated times, above a
  noise floor.**

  | wet-mask cells that differ, days 3.0 → 4.7 (`outflow_fraction=0.5`, 90m) | cells |
  |---|---|
  | noise floor, Moore 0.01 vs. 1-ulp perturbed / von Neumann likewise | 0–2 / 0–2 |
  | Moore 0.01 vs. 0.005 (converged) | 3–19 |
  | Moore 0.02 vs. 0.01 (§13's known-bad) | 11–148 |
  | **von Neumann 0.01 vs. 0.005** | **14–167** |
  | **von Neumann 0.005 vs. 0.0025** | **5–138** |

  Wet cells at 4.7 d: Moore 409 / 263 / 244 at 0.02 / 0.01 / 0.005, and von Neumann 535 / 430 / 302 at
  0.01 / 0.005 / 0.0025.
  - **At `outflow_fraction=0.5`, von Neumann has not converged even at a quarter of Moore's substep
    bound.** Each halving still removes 100+ cells, mostly the eastern lobe and a speckled channel
    fringe. So its extra flooding in that regime is partly numerical.
  - A smaller constant is not a verified fix: 0.0025 is already 4× the substeps and still moving.

  At the live default, to the peak:

  | | Moore | von Neumann |
  |---|---|---|
  | 1-ulp noise floor (wet-mask cells) | 3 | 1 |
  | 0.02 vs. 0.01 (cells) | 54 | 29 |
  | 0.01 vs. 0.005 (cells) | 106 | 29 |
  | gap-only CSI at substep 0.02 / 0.01 / 0.005 | 0.892 / 0.899 / 0.869 | 0.752 / 0.749 / 0.754 |

  Here von Neumann is converged at 0.01: 29 cells, CSI within ±0.003. That is tighter than Moore itself.
- **Decision:**
  - `_MAX_STABLE_SUBSTEP_FRACTION_VON_NEUMANN = 0.01`, measured rather than assumed. It is the same
    value as Moore's.
  - It holds only up to `VON_NEUMANN_MAX_OUTFLOW_FRACTION = 0.085`, the live default. That bound was
    measured with the time-matched test above. The test takes the mean number of cells that differ
    between substep 0.01 and 0.005 over 8 matched days (3.0–5.3 d), and compares it with the validated
    Moore engine's at the same `outflow_fraction`:

    | `outflow_fraction` | von Neumann | Moore | at the peak (vN / Moore) |
    |---|---|---|---|
    | **0.085** | **54** | **53** | 29 / 106 |
    | 0.15 | 71 | 55 | 38 / 42 |
    | 0.5 | 96 | 9 | — |

    - The bound is the highest measured value at parity with Moore.
    - 0.15 is only moderately worse (1.3×; worst day 174 against 116), so a looser tolerance would admit
      it. Nothing is admitted on assumption, though, and 0.25 was not given a Moore reference.
  - `POST /simulations` rejects von Neumann above it with a 422. The UI clamps the outflow fraction to
    it when von Neumann is chosen and caps the input there.
  - Moore is unrestricted, as before.
  - Tests pin the value and run the flat-water control under von Neumann (0.013, against Moore's 0.015
    at the same fraction).
  - The varying-roughness grid's Moore-calibrated 0.05 cutoff did not transfer. Von Neumann sits at
    ~0.050 at every fraction (0.0503 at 0.005), which is its lattice anisotropy read by an 8-neighbor
    metric. So that test asserts convergence (halving the fraction changes the metric by < 2%) instead.
- **Two side findings about the validated Moore engine,** measured here and not changed:
  - (a) A 1-ulp-perturbed Moore run scores gap-only **CSI 0.8997**, exactly §16.4's documented value. The
    unperturbed run scores 0.8986. So the 0.8986-vs-0.8997 discrepancy (FP 47 vs. 46) is ulp-level noise,
    as §18 suspected.
  - (b) **Moore's validated CSI depends on the substep fraction:** 0.892 / 0.899 / 0.869 at 0.02 / 0.01 /
    0.005. §16.3 calibrated `outflow_fraction` with the substep bound fixed at 0.01, so the validated
    result is the configuration "Moore, `outflow_fraction=0.085`, substep 0.01", not a converged-limit
    claim. The thesis should state it that way.

**Result: same scenario, both neighborhoods.** The real May 2024 event, 90m grid, run to the observed peak at
the live `outflow_fraction=0.085`:

| | Moore (validated) | von Neumann |
|---|---|---|
| macro steps to the peak | 134,639 | 133,245 |
| flooded cells | 1,955 | 2,583 |
| naive TP / FP / FN | 789 / 1,166 / 42 | 830 / 1,753 / 1 |
| naive CSI | 0.395 | 0.321 |
| gap-only TP / FP / FN | 789 / 47 / 42 | 830 / 277 / 1 |
| **gap-only CSI** | **0.8986** | **0.7491** |
| hit rate (gap-only) | 0.949 | 0.999 |
| water held at the peak (ΣH) | 19,097 | 41,034 (2.15×) |
| max depth | 28.9 m | 38.3 m |
| WSE at the gauge cell (observed peak stage 33.66 m) | 36.4 m | 46.8 m |
| wall-clock to the peak, measured side by side under the same load | 7.41 min | 4.48 min (0.60×) |

Both neighborhoods take almost the same number of macro steps. The substep count is the same, 9, but a von
Neumann substep visits 4 neighbors instead of 8. At 30m the per-step p50 was 22.7 ms against 37.1 ms
(0.61×), also measured side by side. For the uncontended Moore figure, see §18: 7.6 min.

- **Where the extents differ:** the von Neumann extent is a strict superset of Moore's (1,955 both, 0
  Moore-only, 628 von-Neumann-only).
  - The extra cells form a coherent 1–3 cell rim up the valley sides, everywhere along the reach: median
    terrain 41 m against 27 m for the shared cells, and a median depth of 5.0 m there. This is a higher
    water level, not scattered speckle.
  - 357 of them fall in the unscored Estrela-gap zone.
  - Of the 271 that are scored, 41 are real hits (FN 42 → 1) and 230 are new false positives (47 → 277).
- **Likely mechanism** (supported, not proven): the Taquari runs diagonally (NE → SW) across this grid.
  With only orthogonal moves, water has to staircase along the channel toward the outlet, so the reach
  conveys less at a given stage. The run holds 2.15× the water, sends less out through the outlet
  (403,560 against 425,497), and the stage rises until the valley sides flood.
  - Moore's diagonal moves (weighted by the longer diagonal distance) are what let it follow a channel at
    any orientation. That matches TCC1's own reason for distinguishing diagonal distances.

**Conclusion.** Von Neumann is available as the setting TCC1 names, but it is **not validated**.
- On the one event scored, it over-floods relative to Moore: gap-only CSI 0.749 against 0.899.
- Its `outflow_fraction` was calibrated for Moore (§16.3), and was not re-tuned for 4 neighbors. A von
  Neumann calibration would need its own sweep and is not claimed here.
- That sweep is also constrained: above `outflow_fraction=0.085`, von Neumann's result depends more on the
  substep fraction than Moore's does, so higher values are refused rather than served unconverged.
- Every validated number in this file (§16.4, §18, §19's agreement counts, §21) is a Moore result. The UI
  labels a von Neumann run accordingly and never uses it in the replay preset.

---

## 23. Fast mode: floodplain conveyance (a HAND rating curve) replaces the one-cell-wide channel

**TCC1:** says nothing about the fast mode, which is this project's own addition (§17, §19). This section
records why its first depth rule over-flooded and what replaced it. The comparison remains against this
project's own temporal engine, never against Torres et al.'s numbers.

**Diagnosis: a missing physical term, not a mis-tuned parameter.** §19's rule passed the whole
23,472 m³/s peak through ~106 conveying cells, each treated as a channel **one cell wide**
(`h = (Q·n/(dx·√S))^(3/5)`, `dx = 90 m`).
- At `n ≈ 0.035` and `S = 1e-4` that needs ~50 m of depth. The real stage rise was ~20 m. A ~1 km wide
  section needs ~13 m.
- The HAND lateral rule then spread that too-high surface onto the NW side valley and the eastern high
  ground: §19's 547 gap-only false positives.
- §19's slope-floor sweep (gap-only CSI 0.53 → 0.76 at `_MIN_SLOPE = 1e-3`) "worked" only because a
  steeper slope stands in for the missing width. 1e-3 is not a plausible lower-Taquari slope, so that knob
  was not calibrated.

**Change** (`backend/simulation/fast_engine.py`, `conveyance="cross_section"`, now the default). This is
the standard HAND synthetic-rating-curve method (Zheng et al. 2018, "River channel geometry and rating
curve estimation using height above the nearest drainage").
- **Reach cross-sections:** the conveying channel is split into reaches. Every cell whose
  steepest-descent path drains to a reach's conveying cells belongs to that reach's cross-section, with
  its HAND (height above the channel surface it drains to).
- **Divided-channel Manning:** each cell is a strip of width `dx²/L`. The reach's stage `h` solves
  `Q = √S · Σ (1/n_k) · (dx²/L) · (h − HAND_k)^(5/3)` over the wet cells, by bisection. Per-cell `n_k`
  gives floodplain-versus-channel roughness for free.
- **Forcing and slope:** `Q` is the discharge crossing the reach's downstream end. `S` is the
  least-squares fall of the conditioned channel surface across the reach.
- **Unchanged:** routing (pass 1), the four states, discharge continuity, and the lateral rule. The
  routing pass still uses per-cell slopes floored at `_MIN_SLOPE`.
- `conveyance="single_cell"` keeps §19's rule, which still reproduces 731 / 2,109 / 100 exactly.

**Reach length: the sweep, and why it was not used to tune.** The fitted reach slope is only as good as
the DEM's vertical resolution. TOPODATA heights are whole meters: the conditioned channel sits at
11–14 m along the entire ~8.3 km of river in this ROI. At a ~1e-4 slope, a reach must be ~10 km long
before its bed falls by more than one quantization step. Shorter reaches fit their slope (mostly hitting
the floor) and their cross-section to DEM rounding. The final implementation splits the river into equal
reaches at least `MIN_REACH_LENGTH_M` long (90m grid, gap-only TP/FP/FN):

| `min_reach_length_m` | 500 | 1,000 | 2,000 | 3,000–4,000 | **≥ 5,000 (incl. 10,000 used)** |
|---|---|---|---|---|---|
| reaches | 16 | 8 | 4 | 2 | **1** |
| gap-only TP / FP / FN | 723 / 58 / 108 | 687 / 70 / 144 | 674 / 48 / 157 | 729 / 36 / 102 | **800 / 62 / 31** |
| gap-only CSI | 0.813 | 0.763 | 0.767 | 0.841 | **0.896** |
| conveying cells on the slope floor | 92 | 79 | 82 | 53 | **0** |

- **Below the river's length, CSI swings non-monotonically.** A first pass with fixed-length rather than
  equal bins swung the same way (0.74–0.86 between 180 m and 3 km). That is the signature of bin-boundary
  noise. There is no plateau, so §16.3's calibration criterion fails, and no sub-domain value was
  calibrated.
- **The result is the sweep's limit, not an interior optimum.** Every value above ~4.2 km gives one reach
  on this ROI and the identical result.
- **Disclosure:** the sweep was run before `MIN_REACH_LENGTH_M = 10,000` was fixed. The quantization
  argument explains the sweep's shape, but this number was not set blind the way §19's `_MIN_SLOPE` was.
- **On a longer river** (another ROI), the same rule gives several reaches ≥ 10 km, each with its own
  rating curve.

**Two other changes were tried and dropped** (measured with fixed 1 km bins, before the reach rule above):
- **Connectivity-aware wetting:** wet a lateral cell only if the surface exceeds its outlet-conditioned
  spill level `Zf`, not just its terrain. On the single-cell rule this went 0.5305 → 0.5215. With
  cross-sections it was neutral (0.7993 → 0.7971). With one reach, gap-only counts were identical and
  naive CSI moved by 0.002. It removed more real hits than false alarms, so it was dropped.
- **Non-increasing surface downstream:** raise each conveying cell to its highest downstream target.
  With 1 km bins it went 0.7971 → 0.7793 (+28 TP, +56 FP); on the single-cell rule, 0.5305 → 0.4870.
  With one reach it is a no-op: the stage is uniform and `Zf` is already non-increasing along the routing.

**Result** (90m, May 2024 observed peak, `examples/fast_mode_may2024.py`; temporal figures are §16.4/§18):

| | fast, single-cell (§19) | **fast, cross-section** | temporal (`0.085`) |
|---|---|---|---|
| naive TP / FP / FN | 731 / 2,109 / 100 | **800 / 1,223 / 31** | 789 / 1,167 / 42 |
| naive CSI | 0.249 | **0.390** | 0.395 |
| gap-only TP / FP / FN | 731 / 547 / 100 | **800 / 62 / 31** | 789 / 46 / 42 |
| **Estrela-gap-only CSI** | 0.531 | **0.896** | **0.900** |
| gap-only Hit Rate / FAR | 0.880 / 0.428 | **0.963 / 0.072** | 0.949 / 0.056 |
| flooded-cell depth, median / p95 | 33.5 / 54.7 m | **10.0 / 24.0 m** | 9.3 / 22.7 m (`project-plan.md`, visual-polish entry) |
| wall-clock to a final extent | ~74 ms | **~73 ms** | 7.6 min |

**Checks:**
- **Noise floor:** the shift search (`examples/shift_search_noise_floor.py`'s method, ±3 cells) gives
  shift sensitivity **+0.0000** under both naive and gap-only scoring. No registration offset improves
  the score. §19's rule had +0.0195 (naive).
- **The slope floor no longer binds.** The single reach's fitted slope is 1.02e-4: 3 m of fall over
  8.2 km, fitted from the data. Any floor ≤ 1e-4 gives the identical result. Forcing the floor above the
  fitted slope lowers CSI (2e-4 → 0.859, 3e-4 → 0.839). The score is not propped up by the floor.
- **Physical plausibility:**
  - The stage is 24.6 m above the conditioned channel surface, a water surface of 35.0–38.0 m along the
    reach. That is a little above the 33.66 m observed peak stage, if the gauge datum and the DEM agree
    (not verified here).
  - The depth distribution is now close to the temporal engine's at the peak.
  - Continuity is exact: 23,472.37 m³/s out, 0 retained.
- **Visual:** the depth and state maps are coherent at 30m, 60m and 90m. There is one conveying path from
  the north inflow to a single exiting cell at the south outlet, and the floodplain extends up the
  tributary valleys.
- **Resolution consistency (unvalidated grids):** the old rule flooded 39.8% (30m), 62.3% (60m) and 72.7%
  (90m) of the ROI. The new one floods 48.5%, 47.4% and 51.8%, with a water surface of 34–39 m on all
  three. §21's 30m and 60m fast-mode cell counts are superseded: 30m 17,043 of 35,136 cells (~0.65 s),
  60m 4,137 of 8,736. Both remain unscored.

**Calibration attempted afterwards: no gain beyond noise, nothing adopted.** Following §16.3's method, the
remaining knobs were swept on the 90m grid, scored gap-only.
- **Global Manning's n multiplier** (the standard hydraulic calibration parameter):
  - With one reach, every rating-curve knob only moves the single stage. The DEM is integer meters, so
    near the optimum the swept family yields just four distinct extents, one per meter of water
    surface: ×0.80–0.875 → 0.883, ×0.88–0.995 → 0.8974, ×1.00–1.12 → 0.8959 (default), ×1.125–1.245 →
    0.887.
  - The default already sits on the plateau. The best point is +0.0015, about one cell.
  - Scaling only the floodplain classes (`n ≥ 0.15`, ×0.5–2.0) lands on the same two extents.
- **A tilted water surface:**
  - The residual errors have a spatial pattern. Misses cluster upstream near the inflow (20 of 31,
    terrain ~39 m against a ~37 m model surface). False alarms cluster near the outlet (24 of 62). That
    suggests the real surface falls more steeply than the 1 m-quantized bed.
  - Using one friction slope for both Manning and the tilt lowers the level more than it tilts the
    surface, and CSI falls monotonically (1e-4 → 0.895, 3e-4 → 0.831, 1e-3 → 0.612).
  - A decoupled 2-parameter grid (n multiplier 0.6–1.5 × tilt 1.5e-4–8e-4) is a flat plateau between 0.89
    and 0.90. Its maximum, **0.9010** (tilt 8e-4, n ×1.1), is +0.005 over the default, about five cells.
    It sits isolated at the grid's edge and needs a surface eight times steeper than the bed.
- **Conclusion:** within this rule family the fast mode is at its ceiling on this event. Every gain found
  is within the noise §16.3 used as its threshold (a naive top-3 spread of 0.0054), so the untuned
  default stays. Further improvement would need better input data, not tuning. A finer vertical
  resolution in the DEM would help, since 1 m steps set both the extent's granularity and the slope
  estimate.

**What remains.**
- **Accuracy:** the residual 31 FN and 62 FP sit close to the temporal engine's 42 and 46. The fast mode
  still has no time and no wave-front arrival; that is the temporal engine's distinct contribution, and
  §17's framing (screening mode alongside the validated temporal model) stands.
- **Speed vs. accuracy:** §17's trade-off has largely closed. On this event the fast mode now reaches
  essentially the same extent accuracy roughly 6,000× faster.
- **Scope of the claim:** one event, one ROI, one grid. Depth is still not validated against
  observations: there are none (§20). The UI keeps drawing the fast mode as extent only.
- **Regression:** pinned in `tests/test_fast_engine.py` (cross-section naive 800 / 1,223 / 31, gap-only
  800 / 62 / 31, and §19's 731 / 2,109 / 100 under `single_cell`). New hand-computed tests cover the
  rating-curve stage on a V-valley, reach splitting, and the floodplain width and roughness responses.

---

*Keep this file updated alongside `docs/project-plan.md` whenever a new roadmap step introduces another
point of comparison to TCC1 — the goal is that by the time the thesis is written, every "we said X, we
did Y" question already has its answer and rationale sitting here instead of needing to be
reconstructed from git history.*
