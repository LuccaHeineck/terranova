# tests

Empty for now — the first real tests are expected alongside roadmap step 2 (Manning roughness), replacing
the ad hoc `assert` statements currently inline in `examples/poc_grid.py`'s `main()` (mass conservation,
non-negative depth) with a proper pytest suite.

Structure mirrors the backend: tests for `simulation/` go here directly (e.g. `test_engine.py`), and as
`ingestion/`, `validation/`, etc. gain code, their tests land here too rather than next to the source.
