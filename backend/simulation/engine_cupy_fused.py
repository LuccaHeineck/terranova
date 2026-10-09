"""`simulation.engine.step` on the GPU with each substep fused into two CUDA kernels
(roadmap step 11, the follow-up docs/tcc-deviations.md section 18 recommended; results in
section 25).

Section 18 found plain CuPy flat at ~16 ms per macro step regardless of grid size: one
macro step is ~9 substeps of ~80 small elementwise kernels, so kernel launches, not
arithmetic, set the cost. Here a substep is two launches:
1. per cell, the total release and the normalizing weight sum;
2. per cell, a gather of what each neighbor released toward it, then the new depth.
Kernel 2 recomputes the neighbor's weight toward this cell instead of storing 8 weights
per cell - the same operands in the same order, so the same bits.

Bit-identical to the NumPy engine from the same input (tests/test_engine_cupy_fused.py):
the operation order follows `engine._single_update` exactly (see simulation/engine_loops.py
for the gather-order argument), and the kernels are compiled with `--fmad=false` because
NVRTC's default fused multiply-add contraction would round differently. CUDA's double
`sqrt` and `/` are IEEE correctly rounded, like NumPy's.

Benchmark-only, like engine_loops.py: nothing in `api/` uses it. CuPy is imported lazily
and stays an optional dependency (section 18), so importing this module is free.
"""

import math

import numpy as np

from simulation.engine import DEFAULT_OUTFLOW_FRACTION, _max_stable_substep_fraction, _neighborhood_offsets

_THREADS_PER_BLOCK = 256

_KERNEL_TEMPLATE = r"""
#define PADDED_INDEX(r, c) (((r) + 1) * (cols + 2) + ((c) + 1))

__device__ __forceinline__ double wse_at(const double* Zp, const double* H, int r, int c, int rows, int cols) {
    // Zp + pad(H, 0): padding cells add 0.0, as the vectorized engine's padded sum does.
    bool inside = r >= 0 && r < rows && c >= 0 && c < cols;
    return Zp[PADDED_INDEX(r, c)] + (inside ? H[r * cols + c] : 0.0);
}

__device__ __forceinline__ double weight(double center, double neighbor, double distance, double neighbor_n) {
    double drop = center - neighbor;
    if (drop < 0.0) drop = 0.0;  // np.maximum(x, 0.0); NaN stays NaN
    return sqrt(drop / distance) / neighbor_n;
}

extern "C" __global__ void release(
    const double* Zp, const double* Np, const double* H, double fraction, int rows, int cols,
    double* total_outflow, double* safe_total_weight
) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i >= rows * cols) return;
    int r = i / cols, c = i % cols;
    double center = wse_at(Zp, H, r, c, rows, cols);
    double total_weight = 0.0;
    {ACCUMULATE}
    bool has_outflow = total_weight > 0;
    total_outflow[i] = has_outflow ? fraction * H[i] : 0.0;
    safe_total_weight[i] = has_outflow ? total_weight : 1.0;
}

extern "C" __global__ void gather(
    const double* Zp, const double* Np, const double* H, int rows, int cols,
    const double* total_outflow, const double* safe_total_weight, double* H_out
) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i >= rows * cols) return;
    int r = i / cols, c = i % cols;
    double here = wse_at(Zp, H, r, c, rows, cols);
    double here_n = Np[PADDED_INDEX(r, c)];
    double received = 0.0;
    {GATHER}
    H_out[i] = H[i] - total_outflow[i] + received;
}
"""

_ACCUMULATE_TERM = """
    total_weight += weight(center, wse_at(Zp, H, r + ({dr}), c + ({dc}), rows, cols), {distance},
                           Np[PADDED_INDEX(r + ({dr}), c + ({dc}))]);"""

# Source (r - dr, c - dc) sent toward this cell along offset (dr, dc); its weight is computed
# from its own WSE as center, this cell as the neighbor, and this cell's roughness.
_GATHER_TERM = """
    {{
        int sr = r - ({dr}), sc = c - ({dc});
        if (sr >= 0 && sr < rows && sc >= 0 && sc < cols) {{
            int s = sr * cols + sc;
            double w = weight(wse_at(Zp, H, sr, sc, rows, cols), here, {distance}, here_n);
            received += total_outflow[s] * (w / safe_total_weight[s]);
        }}
    }}"""

_kernels: dict[str, tuple] = {}


def _compiled(neighborhood: str):
    """(release, gather) RawKernels for `neighborhood`, compiled once per process."""
    if neighborhood not in _kernels:
        import cupy as cp

        offsets = _neighborhood_offsets(neighborhood)
        # repr() round-trips the exact double math.hypot gives the NumPy engine.
        terms = [(dr, dc, repr(math.hypot(dr, dc))) for dr, dc in offsets]
        source = _KERNEL_TEMPLATE.replace(
            "{ACCUMULATE}", "".join(_ACCUMULATE_TERM.format(dr=dr, dc=dc, distance=d) for dr, dc, d in terms)
        ).replace(
            "{GATHER}", "".join(_GATHER_TERM.format(dr=dr, dc=dc, distance=d) for dr, dc, d in terms)
        )
        module = cp.RawModule(code=source, options=("--fmad=false",))
        _kernels[neighborhood] = (module.get_function("release"), module.get_function("gather"))
    return _kernels[neighborhood]


def step(
    Z,
    H,
    N,
    outflow_fraction: float = DEFAULT_OUTFLOW_FRACTION,
    inflow=None,
    boundary_elevation=None,
    boundary_roughness=None,
    neighborhood: str = "moore",
):
    """`engine.step` for CuPy arrays, two kernel launches per substep. Same arguments, same
    validation, bit-identical result - see `engine.step` for what each argument means."""
    import cupy as cp

    _neighborhood_offsets(neighborhood)  # validates the name; the kernels bake the offsets in
    if not (0 < outflow_fraction <= 1):
        raise ValueError("outflow_fraction must be in (0, 1]")
    if cp.any(N <= 0):
        raise ValueError("N (Manning roughness) must be strictly positive everywhere")
    if inflow is not None:
        if inflow.shape != H.shape:
            raise ValueError("inflow must have the same shape as H")
        if cp.any(inflow < 0):
            raise ValueError("inflow must be non-negative everywhere")
    padded_shape = (H.shape[0] + 2, H.shape[1] + 2)
    if boundary_elevation is not None and boundary_elevation.shape != padded_shape:
        raise ValueError(f"boundary_elevation must have shape {padded_shape} (H's shape padded by 1)")
    if boundary_roughness is not None:
        if boundary_roughness.shape != padded_shape:
            raise ValueError(f"boundary_roughness must have shape {padded_shape} (H's shape padded by 1)")
        if cp.any(boundary_roughness <= 0):
            raise ValueError("boundary_roughness must be strictly positive everywhere")

    n_substeps = math.ceil(outflow_fraction / _max_stable_substep_fraction(neighborhood))
    substep_fraction = 1 - (1 - outflow_fraction) ** (1 / n_substeps)

    if boundary_elevation is None:
        boundary_elevation = cp.pad(Z, 1, mode="constant", constant_values=cp.inf)
    if boundary_roughness is None:
        boundary_roughness = cp.pad(N, 1, mode="constant", constant_values=1.0)
    Zp = cp.ascontiguousarray(boundary_elevation, dtype=cp.float64)
    Np = cp.ascontiguousarray(boundary_roughness, dtype=cp.float64)

    release, gather = _compiled(neighborhood)
    rows, cols = H.shape
    cells = rows * cols
    grid = ((cells + _THREADS_PER_BLOCK - 1) // _THREADS_PER_BLOCK,)
    block = (_THREADS_PER_BLOCK,)
    current = cp.ascontiguousarray(H, dtype=cp.float64).copy()
    scratch = cp.empty_like(current)
    total_outflow = cp.empty_like(current)
    safe_total_weight = cp.empty_like(current)
    rows32, cols32 = np.int32(rows), np.int32(cols)
    fraction = np.float64(substep_fraction)
    for _ in range(n_substeps):
        release(grid, block, (Zp, Np, current, fraction, rows32, cols32, total_outflow, safe_total_weight))
        gather(grid, block, (Zp, Np, current, rows32, cols32, total_outflow, safe_total_weight, scratch))
        current, scratch = scratch, current
    if inflow is not None:
        current = current + inflow
    return current
