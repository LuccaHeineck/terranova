---
name: terranova-context
description: Load Terranova flood-simulator project context (TCC background, architecture, and current build plan) before continuing development work. Use at the start of a session on this project, or whenever a task touches the CA simulation engine, DEM/geodata pipeline, validation metrics, or the TCC methodology.
---

# Terranova project context

Terranova is a flood simulation project for the Vale do Taquari (RS, Brazil), based on macroscopic cellular automata, developed as the user's TCC (undergraduate thesis) in Engenharia de Software at Univates. It is being built incrementally: a pure-Python/NumPy simulation core first, on small artificial grids, then real geodata (rasterio), then a FastAPI + WebSocket backend, then a React + Leaflet frontend, then Docker Compose — each step validated before the next.

When this skill is invoked, do the following before continuing any work:

1. Read `docs/project-plan.md` — the current build step, the target directory structure, and the full incremental roadmap (steps 1–8). This is the source of truth for "what are we doing right now" and "what comes next."
2. Read `docs/tcc-summary.md` — the condensed academic context: the research problem, the CA transition rule (WSE, Manning-weighted Moore-neighborhood flow, mass conservation), the already-completed informal proof of concept and its results, data sources, planned architecture, and validation metrics (CSI, RMSE). This exists so the full 69-page `TCC1LuccaHeineck.pdf` doesn't need to be re-read every session — only fall back to the PDF itself if something here is ambiguous or insufficient.
3. Read `docs/ARCHITECTURE.md` — the folder structure (including empty, README-documented placeholder folders scaffolded ahead of need), what belongs in each part, dependency directions between components, and where new code should go.
4. Read `plan.md` at the repo root for the user's high-level stack/repo conventions (monorepo, Docker Compose, code and comments in English).

Then proceed with the task, keeping implementation consistent with the transition rule and roadmap described in those docs.

## Keeping this current

Whenever a roadmap step in `docs/project-plan.md` is completed, update its "Current status" section to reflect the new current step before ending the session. If the TCC's documented methodology changes (e.g. the user shares an updated TCC draft), update `docs/tcc-summary.md` to match.
