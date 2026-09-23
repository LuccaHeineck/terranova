# validation

Roadmap step 10. Holds the accuracy metrics that compare simulation output against real 2023/2024 flood
event data.

`metrics.py` implements CSI (Critical Success Index — spatial/extent accuracy), Hit Rate, and False Alarm
Rate: pure functions over boolean NumPy arrays (a simulated "flooded" mask vs. a real observed one), all
three derived from the same confusion-matrix counts (true/false positives/negatives). No file I/O, no CA
logic — dependency-free like `simulation/`.

RMSE against real depth ground truth (High-Water Marks / SWOT) is deferred — see
`docs/tcc-deviations.md` section 13 for why — not implemented here yet.

Depends only on `numpy`. Independent of `api/` — it's a metrics library, usable from `api/`, `scripts/`,
or a standalone script like `examples/validate_may2024.py` (the real end-to-end CSI run against the May
2024 flood event, using ground truth ingested by `ingestion/flood_extent.py`).
