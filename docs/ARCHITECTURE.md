# Architecture

This is the main guide to how Terranova is organized: what each folder is for, how data and requests
flow through the system, and where new code should go. Read this alongside `docs/project-plan.md` (which
step we're on) and `docs/tcc-summary.md` (the academic model being implemented).

The project is built **incrementally** — see `docs/project-plan.md`'s roadmap. Most of the folders below
are scaffolded now (each with its own short README) so the target shape is visible from day one, but most
of them are still empty: they only get real code when their roadmap step is reached. Don't write code
into a folder ahead of its step just because the folder exists.

## 1. Project overview

Terranova simulates flood propagation over Vale do Taquari (RS, Brazil) using a macroscopic cellular
automaton (CA): a grid of cells, each with a static elevation `Z` and a water depth `H` that evolves over
discrete time steps by exchanging volume with its 8 neighbors (the Moore neighborhood), weighted by slope
and (eventually) surface roughness. It's a Python/NumPy backend with a planned FastAPI + WebSocket API and
a React/Leaflet frontend, built one validated increment at a time rather than as a single upfront design.

## 2. High-level architecture

```
frontend  →  api  →  { simulation, ingestion, config, validation }
```

The frontend never talks to the simulation directly — it only ever calls the API over HTTP/WebSocket.
The API is a thin orchestration layer: it loads settings from `config`, gets real-world arrays from
`ingestion`, runs them through `simulation`, and (later) scores results with `validation`. `simulation`
itself is a dependency-free library that doesn't know any of this exists.

## 3. Folder structure

```
terranova/
├── backend/
│   ├── simulation/     # core CA engine — the domain/business logic (HAS CODE)
│   ├── examples/        # PoC/demo entrypoints, e.g. poc_grid.py (HAS CODE)
│   ├── ingestion/        # DEM + land-cover data processing (empty — step 3/4)
│   ├── api/              # FastAPI + WebSocket (empty — step 5)
│   ├── validation/       # CSI/RMSE metrics (empty — step 8)
│   ├── config/           # settings/paths/parameters (empty — starts step 3)
│   ├── scripts/          # future ops CLI tooling (empty — step 3+)
│   ├── tests/            # pytest suite (empty — starts step 2)
│   └── requirements.txt
├── data/                  # raw/processed geodata + validation ground-truth (empty — step 3)
│   ├── raw/
│   └── processed/
├── frontend/              # empty stub — filled starting step 6
├── docs/
│   ├── project-plan.md    # roadmap + current status
│   ├── tcc-summary.md     # condensed academic context
│   └── ARCHITECTURE.md    # this file
├── plan.md                # original stack decision
├── CLAUDE.md
├── TCC1LuccaHeineck.pdf
└── .gitignore
```

## 4. Explanation of every major folder

### `backend/simulation/` — the domain layer

What belongs here: the CA transition rule itself — pure functions over NumPy arrays (`Z`, `H`, later `N`
for roughness). Currently just `engine.py`, exposing `step(Z, H, outflow_fraction=0.5)`.

What does NOT belong here: file I/O, geodata parsing, HTTP/WebSocket code, configuration loading,
plotting. `simulation/` must stay dependency-free — no imports from `ingestion/`, `api/`, or `config/` —
so it stays trivially testable on plain arrays in isolation, independent of everything else.

Why it exists: this is the one piece of the TCC that everything else (API, frontend, real data) wraps
around. It's also why there's no separate `domain/` folder — `simulation/` already **is** the
domain/business-logic layer for this project; a `domain/` folder on top would just rename the same thing.

How it interacts with other folders: called by `examples/` (demos) and, later, `api/` (the real service).
Never calls anything else.

### `backend/examples/` — demos and PoCs

What belongs here: small, self-contained scripts that exercise `simulation/` end-to-end and print/plot
sanity checks, for a human to look at and verify behavior looks right — currently `poc_grid.py` (synthetic
terrain, seeded water pool, run N steps, assert mass conservation, plot the result).

What does NOT belong here: anything another part of the codebase imports. Nothing imports `examples/` —
it's a leaf, run directly (`python -m examples.poc_grid`), not a library.

Why it's separate from `scripts/`: a demo that shows the engine working is a different kind of thing from
an operational tool that helps run the project (like a future DEM-download CLI). Keeping them apart means
"how do I see the engine work" and "how do I do X to the project" never end up in the same junk drawer.

### `backend/ingestion/` — data processing (empty until step 3)

What belongs here: code that turns raw geodata into the arrays `simulation/` consumes — reading DEM
tiles with `rasterio`, sink filling, clipping to the region of interest (step 3), and applying the
MapBiomas land-cover → Manning's-n lookup table to build the roughness matrix `N` (step 4).

What does NOT belong here: the actual data files (that's `data/`), and no CA logic (that's
`simulation/`) — this folder only transforms inputs, it never runs the simulation.

How it interacts with other folders: reads from `data/raw/`, writes to `data/processed/`, uses `config/`
for file paths. Called by `api/` (and later `scripts/` for offline preprocessing runs).

### `backend/api/` — orchestration + network boundary (empty until step 5)

What belongs here: the FastAPI app — REST endpoints to configure/start a run, a WebSocket channel
streaming simulation frames every N iterations.

What does NOT belong here: any CA math (delegates to `simulation/`), any raster parsing (delegates to
`ingestion/`).

How it interacts with other folders: depends on `config/`, `ingestion/`, `simulation/`, `validation/` —
it's the layer that wires all of them together and is the only one the frontend ever talks to.

### `backend/validation/` — metrics (empty until step 8)

What belongs here: CSI (spatial/extent accuracy) and RMSE (depth accuracy) calculations comparing
simulation output against real flood event data (HWM, SWOT).

What does NOT belong here: simulation logic or data loading — it consumes arrays that `simulation/` and
`ingestion/`/`data/` already produced.

How it interacts with other folders: depends on `simulation/` (output) and `data/` (ground truth).
Independent of `api/` — it's a metrics library, usable from `api/`, `scripts/`, or standalone.

### `backend/config/` — settings (empty until step 3)

What belongs here: things that are currently just hardcoded constants in `examples/poc_grid.py` (grid
size, `outflow_fraction`) plus things that don't exist yet — DEM/lookup-table file paths (step 3-4), API
host/port and WebSocket settings (step 5), Docker environment variables (step 7).

What does NOT belong here: any logic — this is pure settings, no imports from anywhere else in the app.

How it interacts with other folders: everything else may import `config/`; it never imports anything
back. It's a dependency leaf, same shape as `simulation/` but for settings instead of math.

### `backend/scripts/` — ops tooling (empty until step 3+)

What belongs here: one-off operational utilities that support running the project — e.g. a future CLI to
download/clip a DEM tile, or trigger a preprocessing batch job.

What does NOT belong here: anything demonstrating engine behavior (`examples/`) or anything imported by
other code (that'd belong in a real module, not a script).

How it interacts with other folders: calls into `ingestion/` and `config/` to do its work; nothing calls
into `scripts/`.

### `backend/tests/` — automated tests (empty until step 2)

What belongs here: a pytest suite mirroring the rest of the backend (`test_engine.py` for `simulation/`,
etc.), replacing the ad hoc `assert` statements currently inline in `examples/poc_grid.py`'s `main()`.

What does NOT belong here: manual/visual demos (`examples/`) — tests should be automated and assertion-
based, runnable without a human looking at a plot.

How it interacts with other folders: imports from `simulation/`, `ingestion/`, `validation/`, etc. to
test them. Nothing imports `tests/` — it's a leaf.

### `data/` — raw and processed geodata (empty until step 3)

What belongs here: the actual files — DEM tiles, MapBiomas rasters, HWM/SWOT validation datasets — split
into `raw/` (as downloaded) and `processed/` (what `ingestion/` produces).

What does NOT belong here: any code. This folder is pure storage; once real files land here it's expected
to be gitignored (large binaries don't belong in git history).

How it interacts with other folders: read/written by `backend/ingestion/`; read by `backend/validation/`
for ground truth.

### `frontend/` — the UI (empty stub, filled starting step 6)

What belongs here: the React + Vite + Leaflet app — map rendering, config panel, live log/metrics panel.

What does NOT belong here: any backend logic. The frontend only ever calls `backend/api/`'s HTTP/WebSocket
contract; it never imports Python code or reads `data/` directly.

### `docs/` — documentation

`project-plan.md` (roadmap + current status), `tcc-summary.md` (condensed academic reference), and this
file. No code.

## 5. Explanation of important files

- **`backend/simulation/engine.py`** — the whole CA engine today: `step(Z, H, outflow_fraction=0.5)`.
  Pads `Z`/`H` so the grid boundary is a closed wall, computes water-surface elevation `WSE = Z + H`,
  distributes each cell's outflow to downhill Moore neighbors weighted by `drop / distance` (diagonal
  neighbors get a longer distance, per the TCC's note on geometric distortion), capped at
  `outflow_fraction` of the cell's depth per step for numerical stability. Pure NumPy, no side effects.
- **`backend/examples/poc_grid.py`** — builds a synthetic bowl-plus-hill terrain, seeds a pool of water,
  runs `simulation.engine.step` in a loop for a fixed number of iterations, asserting mass conservation
  and non-negative depth after every step, then plots terrain vs. final depth. This is currently the
  *only* place a multi-step run loop exists — `simulation/` itself only exposes a single step. If `api/`
  later needs the same "run N steps and check conservation" behavior, extracting that loop into a shared
  `simulation` runner function is a reasonable future refactor — not done yet, since it's not needed until
  a second caller exists.
- **`backend/requirements.txt`** — `numpy` (core dependency) and `matplotlib` (PoC/demo plotting only,
  not needed once real code lives in `api/`/`validation/`).

## 6. Data flow

```
data/raw/  →  ingestion/  →  data/processed/  →  simulation/ (as Z, H, N)  →  results (in-memory arrays)
                  ↑
              config/ (file paths)
```

Data enters the system as files under `data/raw/`, gets transformed by `ingestion/` (sink filling,
roughness lookup) into `data/processed/`, and finally loaded as plain NumPy arrays — by the time anything
reaches `simulation/`, it's just arrays, with no memory of what file it came from.

## 7. Request/response flow (once `api/` exists, step 5+)

```
frontend  --HTTP POST /simulations-->  api/  --loads-->  config/, ingestion/ (or cached data/processed/)
frontend  <--WebSocket frames----------api/  --runs----->  simulation/ (step-by-step loop)
```

The frontend starts a run over REST, then receives a stream of frames over WebSocket as `api/` calls
`simulation.engine.step` repeatedly. No persistence layer is planned — results are computed on demand from
preprocessed static data, matching the "no DB" decision in `plan.md`.

## 8. Simulation flow

1. A caller (today: `examples/poc_grid.py`; later: `api/`) builds or loads `Z` (and later `H`, `N`).
2. It calls `simulation.engine.step(Z, H, outflow_fraction)` once per iteration.
3. Each call returns the new `H`; the caller is responsible for the loop, iteration count, and any
   per-step checks (mass conservation, logging, streaming a frame) — `simulation/` itself has no concept
   of "a run," only "a step."

## 9. Dependency relationships

```
config/        ← leaf, nothing depends on it going the other way
simulation/    ← leaf, pure, no internal dependencies
ingestion/     → depends on config/
validation/    → depends on simulation/ (output) and data/ (ground truth)
api/           → depends on config/, ingestion/, simulation/, validation/
examples/      → depends on simulation/ only
scripts/       → depends on ingestion/, config/
tests/         → depends on whatever it's testing (simulation/, ingestion/, validation/)
frontend/      → depends on api/'s network contract only, never imports backend code
```

Arrows always point from "orchestration" toward "core logic," never the reverse — `simulation/` in
particular must never import from `api/`, `ingestion/`, or `config/`.

## 10. How the pieces fit together

Think of it in three layers:
1. **Core math** (`simulation/`) — doesn't know about files, networks, or settings. Just arrays in,
   arrays out.
2. **Support** (`config/`, `ingestion/`, `data/`, `validation/`) — get real-world inputs into a shape
   `simulation/` can use, and score its outputs against reality. Independent of each other except
   `ingestion/` reading `config/` for paths.
3. **Orchestration** (`api/`, `examples/`, `scripts/`) — the different ways a human or the frontend
   actually invokes the above. Each is a separate, independent entrypoint into the same core.

## 11. Where should I put this?

- New numeric transition-rule logic (e.g. Manning roughness weighting) → `backend/simulation/`
- A new raster/data format loader, sink-filling, or lookup-table logic → `backend/ingestion/`
- A new REST route or WebSocket message type → `backend/api/`
- A new CSI/RMSE-style metric → `backend/validation/`
- A new setting, file path, or tunable parameter → `backend/config/`
- A one-off script exploring/demonstrating engine behavior → `backend/examples/`
- A reusable CLI tool for project operations (e.g. downloading a DEM tile) → `backend/scripts/`
- A new automated test → `backend/tests/`
- A new raw or processed data file → `data/raw/` or `data/processed/`
- Anything React/Leaflet/UI → `frontend/`
- A roadmap or academic-context update → `docs/`

If you're unsure whether something needs a new folder at all: it probably doesn't. Every folder in this
project was added because a specific roadmap step needs it — don't add a new one without the same
justification.

## 12. How to understand this project (recommended reading order)

1. `docs/tcc-summary.md` — the academic model being implemented, in condensed form.
2. `backend/simulation/engine.py` — the actual core algorithm, ~60 lines.
3. `backend/examples/poc_grid.py` — see the engine run end-to-end on a toy example.
4. This file (`docs/ARCHITECTURE.md`) — how everything is organized around that core.
5. `docs/project-plan.md` — what's done, what's next, and why the steps are ordered this way.
