# validation

Empty for now — activates at roadmap step 8.

Will hold the CSI (Critical Success Index — spatial/extent accuracy) and RMSE (depth accuracy) metrics
that compare simulation output against real 2023/2024 flood event data (High-Water Marks and SWOT
satellite altimetry, read from `data/`).

Depends on `simulation/` (to get output arrays) and `data/` (ground-truth). Independent of `api/` — it's
a metrics library that could be invoked from `api/`, `scripts/`, or a notebook, not a service itself.
