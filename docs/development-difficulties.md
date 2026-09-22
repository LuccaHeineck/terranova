# Development Difficulties

This tracks real hardships hit while building Terranova — bugs, dead ends, environment issues, and
things that took genuine debugging effort — as distinct from `docs/tcc-deviations.md`, which tracks
*comparisons to the TCC1 proposal*. Some items below are also deviations and are cross-referenced
there; most are pure implementation friction that TCC1 never had an opinion on either way. This
exists so the TCC II write-up has an honest "here's what was actually hard" record instead of one
reconstructed from memory at the end, and so future sessions on this project don't re-learn the same
lessons. Organized in build order, matching `docs/project-plan.md`'s roadmap steps.

---

## Step 1 — checkerboard/speckle artifact

Releasing a cell's full `outflow_fraction` in a single synchronous (Jacobi-style) pass caused
neighboring cells to overshoot past each other step to step — the same family of instability as
violating a CFL condition in explicit diffusion schemes — producing a visible speckled texture
instead of a smooth flood front. Diagnosing this took real investigation, not a quick fix: a
flat-water-everywhere control test (the artifact appeared even with zero initial asymmetry, ruling
out a seeding bug) and a fraction sweep (artifact magnitude scaled linearly with `outflow_fraction`,
pointing at a step-size stability issue rather than a logic bug) were both needed before the real
cause was clear. Fixed by internally decomposing the requested `outflow_fraction` into several
smaller synchronous sub-updates (`_MAX_STABLE_SUBSTEP_FRACTION` in `engine.py`) that compound to the
same total release, without changing `step()`'s external signature or per-call physical meaning.

## Step 1 → 2 — bare-slope bug caught late

Step 1's transition rule used bare slope (`drop / distance`) instead of the TCC's actual documented
`sqrt(slope)`. This wasn't a deliberate simplification — it was a plain transcription error — and
wasn't caught until step 2's Manning-weighting work forced a close re-read of the TCC's equation.

## Step 3 — `pysheds`/`richdem` unusable on this environment

Sink-filling the real DEM was planned around an existing hydrology library rather than hand-rolled
code. Both `pysheds` and `richdem` were tried first; `pysheds`'s `numba` JIT compilation step failed
to compile on this project's Python 3.14 — a toolchain/version-compatibility bug unrelated to the
DEM data itself, and not something worth downgrading the whole project's Python version to work
around. Resolved by implementing a priority-flood algorithm (Barnes et al. 2014) directly with
stdlib `heapq` in about 30 lines — simple enough that the library dependency turned out not to be
worth chasing.

## Step 3 — reprojection corner artifacts

Reprojecting the raw lat/lon DEM tile into a metric CRS (required for the engine's square-cell
distance assumptions) rotates the ROI box slightly, since true north and the new grid's north don't
align — this leaves thin nodata slivers at the corners that the engine would otherwise treat as
bottomless pits. Not anticipated going in; found by inspecting the reprojected raster and fixed with
a dedicated greedy border-trim step.

## Step 6 — flood overlay invisible against the basemap, twice

First occurrence: the initial blue-tinted depth color ramp was visually indistinguishable from OSM's
own blue river tiles — only caught by actually looking at a running demo in a browser, not by any
test. Fixed by switching to a high-contrast orange-red ramp. Second occurrence, same underlying
problem in a different form: OSM's busy colored roads/labels still visually competed with the flood
overlay in general, so the basemap itself was later swapped to Esri's low-saturation dark gray canvas
— a genuine "data overlay needs to visually dominate its basemap" lesson that took two separate
passes to fully resolve.

## Step 7 — Docker environment gaps only visible once the stack actually ran

Two real environment gaps were invisible in bare-metal testing and only surfaced when
`docker compose up --build` was actually run for the first time: a missing system library
(`libexpat1`, which rasterio's manylinux wheel dynamically links against but the `python:3.12-slim`
base image doesn't ship), and a bind-mount gap (the backend container had no access at all to the
repo-root `data/` folder, so the FastAPI lifespan crashed on startup trying to load real DEM/land-cover
files). Neither was something code review or unit tests could have caught — they only exist in the
containerized environment.

## Step 7 — root-owned files side effect

Because the backend container runs as root (no `USER` directive) and bind-mounts the host `data/`
folder read-write, its writes leave `data/processed/*.tif` root-owned on the host afterward. This
self-heals the next time the backend runs bare-metal as the normal user (it unconditionally
overwrites the same files), so it wasn't treated as a bug worth fixing properly — but it's a real
"permission denied" trap waiting for a future bare-metal run right after a Docker one, worth knowing
about rather than rediscovering.

## Step 9 — wrong ANA API operation returned the wrong data shape

The originally planned ANA `HidroSerieHistorica` operation turned out to return a monthly transposed
summary that silently dropped most of the requested date window — no error, just the wrong shape,
which is a much harder failure mode to notice than an exception. Only caught by inspecting the
service's live WSDL directly and switching to the `DadosHidrometeorologicos` operation instead.

## Step 9 — wrong inflow boundary edge

A heuristic — "the ROI boundary edge with the highest minimum elevation is upstream" — was applied
blindly across all four edges and picked `"east"`. In reality the Taquari channel only ever crosses
this ROI's north and south edges; the east edge's "highest minimum" was just a 2-cell dip on a
hillside about 15m above the real channel bed. This was only caught by a whole-branch review that
cross-checked the heuristic's output directly against the real DEM's channel-elevation cells —
neither the heuristic's own logic nor any test flagged it as wrong on its own. Corrected to `"north"`,
and the heuristic itself is now documented as valid only once restricted to edges that actually carry
the channel.

## Step 9 — absolute mass-conservation tolerance broke at real scale

The existing `seeded_pool` mode's fixed `1e-6` absolute conservation tolerance works fine for a
constant ~400-unit closed-system volume. Gauge-driven cumulative inflow reaches order 1e7 over
100,000+ steps, where ordinary float64 round-off alone can exceed a fixed absolute bound with nothing
actually wrong — a correctness check that was solid at one scale became a false alarm at another.
Required switching that mode's check to a relative tolerance instead.

## Step 9 — first-step inflow burst

On a still-dry grid, `compute_stable_dt`'s no-flow fallback (3,600 seconds, a value sized for
redistribution stability, not for external-inflow sizing) would otherwise inject a full hour's worth
of real river discharge — thousands of m³/s — into the ~9 boundary cells in a single step. Required
an explicit `dt` cap at the raw gauge feed's own sample spacing (900s) to keep the transient bounded;
this doesn't eliminate the transient (concentrating a whole river's discharge through 9 cells on a
30m grid is an inherent coarse-grid simplification), just keeps it physically motivated and documented
instead of an arbitrary, unbounded spike.

## Step 9 — WebSocket close-before-`accept()` edge case

An unknown or already-consumed `run_id` causes the server to close the socket with code 4004 *before*
calling `accept()` — which means the frontend can never receive it as an ordinary JSON error message;
it only ever surfaces through the socket's `onclose` handler. Easy to miss entirely and end up with a
silently frozen UI instead of a visible error banner.

## Step 9 — the closed-boundary design meeting a real event for the first time

The engine's walls-on-all-sides boundary (required since step 1 for exact mass-conservation checks)
was never a problem for a single seeded pool of water. A real ~14-day hydrograph is a different story:
its total inflow (~9.1e9 m³) into the closed 183×192 ROI implies a mean depth of ~288m against a 96m
maximum terrain elevation — the entire ROI eventually floods, because there is nowhere for the water
to leave. This was always an implication of the closed-boundary design, but nothing exposed it until
step 9's real driving data existed to actually run it through. It's not fixed yet, and directly blocks
step 11's CSI comparison from being meaningful until it is addressed (see `project-plan.md`).

## Step 9 — the performance wall (current, unresolved as of this writing)

The first attempt to actually observe a full gauge-driven run to completion revealed it would take on
the order of hours of wall-clock time (measured throughput: ~50 real engine steps per minute once the
grid is wet, against 100,000+ steps needed for the full event), and separately that the WebSocket
handler is CPU-bound with no `await`/yield points during a run — blocking other API requests on the
same worker, with an abandoned run continuing to compute after the client disconnects. Neither problem
was visible from unit tests or short synthetic runs; both only appeared once a real, long-running
end-to-end scenario was actually attempted. See `docs/project-plan.md`'s roadmap step 10 for the
analysis of the likely cause and the plan to resolve it.

## Step 10 — the "obvious" vectorization fix made things slower, not faster

Profiling (see `docs/project-plan.md`'s step 10) showed `_single_update`'s 8-direction Python loop
dominates the engine's runtime, so the natural first fix was to replace it with a single stacked
`(8, rows, cols)` NumPy pass instead of looping over 8 small per-direction arrays — fewer, larger
calls instead of many small ones. It was implemented, verified numerically identical against a new
golden-output regression test and the full existing suite, then measured with the profiling script —
and it made a real gauge-driven run **~2.6x slower** (233 steps in 60s vs. the 607/60s baseline), not
faster. `np.stack`'s own cost of copying 8 slices into a new contiguous array turned out to outweigh
the savings from doing fewer, larger arithmetic calls, at this grid's actual size (~185×194 cells) —
an assumption ("fewer, bigger NumPy calls are always faster") that held in the abstract but not at
this specific array size once actually measured. Reverted in the same session, confirmed via `git
diff` that `engine.py` was back to its original state. The lesson: even a change reasoned about
carefully and verified for *correctness* still needs to be measured for *performance* before being
kept — the instinct that a fix "should" help isn't evidence that it does.

## Step 10 — the channel-edge heuristic doesn't generalize across resolutions either

While testing a coarser grid resolution (60m instead of 30m) as a performance fix, the same
elevation-margin heuristic that once wrongly picked `"east"` as the inflow edge (see the step-9 entry
above) was re-run at the new resolution as a sanity check — and it produced a *new* false positive:
west and east, which correctly show zero channel cells at 30m, both picked up a handful of
"channel-like" cells (within the fixed 2.0m margin of their own minimum) at 60m, purely as a resampling
artifact of the coarser DEM shifting those edges' local minima slightly closer together. North and
south — the real channel-crossing edges — stayed correct (their minimum elevations, 12.0m and 11.0m,
were exactly unchanged from the 30m grid), so the actual `HYDROGRAPH_INFLOW_EDGE = "north"` config
value stayed right by inspection, but a workflow that *re-derived* the edge from this heuristic
automatically at a new resolution, without a human checking the result against known geography, would
have risked repeating the exact class of bug step 9 already found and fixed once. The heuristic is
useful as a first pass but isn't self-verifying — it needs a human sanity check (or a real
channel-tracing algorithm) every time the resolution or ROI changes, not just once.

## Step 10 — restricting to a partial time window wasn't the free win it looked like

A second performance idea, orthogonal to grid coarsening: since the real flood's peak (33.66m) occurs
at day 5.56 of the full 14-day event, and CSI validation can't use the full 14-day run anyway (it
floods the entire ROI to physically implausible depths — see the step-9 entry above), why not just
simulate through the peak instead of the full event? At first glance this looks like a free ~2.5x cut
in total simulated time (5.56 of 14 days) with zero cost to spatial resolution.

Tested directly at 30m (real run, not an extrapolated sample, since the whole point was to get a real
number): after 9 minutes of wall-clock time it had only reached **0.11 of the 5.56 target days (~2%)**,
and the observed throughput was *declining* as it ran (9.97 → 9.07 → 8.81 → ... → 8.47 steps/sec and
still dropping), trending toward roughly **7-8 hours** just to reach the peak — worse than the naive
"40% of the full ~9h estimate" (~3.6h) would have suggested, not better. The early rising-limb period,
right as boundary inflow first starts pushing water into a mostly-dry grid, turns out to be one of the
*more* expensive parts of the event, not a cheap warm-up — `compute_stable_dt`'s own already-documented
"dt shrinks as the grid wets" behavior applies non-uniformly across the event, and this stretch is on
the expensive end of that curve. Stopped the run once the trend was clear rather than waiting hours for
a number we already had strong evidence for.

**Lesson**: "fewer real-time-days simulated" does not translate proportionally to "fewer wall-clock
hours needed" - throughput varies substantially across the event's timeline, and assuming a uniform
rate (even from a real, measured baseline sample) can be badly wrong in either direction. The time-
window lever still has some validity (it's needed for CSI regardless of speed, per the step-9 entry),
but it doesn't stack for free with grid coarsening the way a first-pass estimate suggested - actually
combining the two needs its own real measurement, not multiplication of two separate percentages.

## Process-level: resisting the temptation to follow TCC1's own timeline literally

Also recorded in `docs/tcc-deviations.md` section 0 as a TCC1-vs-built comparison point, but worth
repeating here as a genuine early friction point rather than just a footnote: TCC1's own Quadro 7
timeline starts with Docker/repo/WebSocket infrastructure and folds algorithm validation into the
middle of the schedule. Deliberately inverting that — validating the transition rule on small
synthetic grids first, with nothing else built yet — meant going against the proposal's literal
calendar from the very first session of actual coding, trusting that front-loading the
highest-academic-risk piece was worth the discomfort of not matching the written plan.

---

*Keep this file updated whenever a new roadmap step surfaces a real hardship worth remembering — a
bug that took real effort to track down, an environment/toolchain issue, a design assumption that
broke under real data, or anything else a future session (or the TCC II write-up) would benefit from
not having to rediscover. For points that also compare directly to what TCC1 proposed, add a
cross-referenced entry to `docs/tcc-deviations.md` too; not every difficulty here is a deviation, and
not every deviation there was actually difficult.*
