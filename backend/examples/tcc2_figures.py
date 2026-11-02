"""Figures for the TCC II write-up (Portuguese labels, since the thesis is in pt-BR).

Writes numbered PNGs to `docs/tcc2/figures/`. Model results come from three places:
- the caches `examples/tcc2_scenarios.py` writes (temporal engine runs to the May 2024 peak);
- runs made here, because they take seconds (the synthetic PoC and the fast mode);
- measured numbers quoted from `docs/tcc-deviations.md` where re-measuring would mean
  re-running hours of sweeps or benchmarks (the outflow_fraction and outlet-margin sweeps,
  the step-11 performance tables). Each such figure names its section in a comment and
  in its caption text in `docs/tcc2-context.md`.

A figure whose cache is missing is skipped with a message, so the rest still render.

Run from the backend/ directory with the venv active (after examples.tcc2_scenarios):

    python -m examples.tcc2_figures [--only fig01 fig08 ...]
"""

import argparse
from datetime import datetime, timedelta

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import BoundaryNorm, LightSource, ListedColormap
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import FuncFormatter, NullFormatter

from config import settings
from examples.poc_grid import GRID_SIZE, SEED_VOLUME, seed_pool, synthetic_roughness, synthetic_terrain
from examples.tcc2_scenarios import CACHE_DIR, FLOODED_DEPTH_THRESHOLD_M
from ingestion.dem import build_elevation_matrix, get_georeference, lonlat_to_cell
from ingestion.flood_extent import build_observed_flood_mask, build_validation_reference
from ingestion.hydrograph import (
    build_hydrograph,
    find_boundary_inflow_mask,
    find_boundary_outlet,
    find_calibration_pairs,
    load_raw_stage_series,
)
from ingestion.landcover import MANNING_N_BY_CLASS, align_to_reference_grid, build_roughness_matrix
from simulation.engine import step
from simulation.fast_engine import CONVEYING, EXITING, INUNDATED, classify_steady_flood
from validation.metrics import confusion_counts, csi, false_alarm_rate, hit_rate

OUT_DIR = settings.REPO_ROOT / "docs" / "tcc2" / "figures"

# First reading of the ANA record (data/raw/estrela_stage_may2024.xml); elapsed
# times in the model are measured from it.
RECORD_START = datetime(2024, 4, 27, 0, 0)

# ANA gauge 86879300 "ESTRELA" (settings.py's VALIDATION_GAUGE_ROW comment).
GAUGE_LON, GAUGE_LAT = -51.965, -29.4717

# Confusion-map colors: the ones examples/plot_confusion_map.py and the frontend's
# Observed layer use, plus two greys for the Estrela coverage-gap exclusion.
TN_COLOR, TP_COLOR, FP_COLOR, FN_COLOR = "#f0efec", "#2a78d6", "#1baf7a", "#eb6834"
EXCL_DRY_COLOR, EXCL_WET_COLOR = "#d6d3cc", "#9c988f"
CODE_TN, CODE_TP, CODE_FP, CODE_FN, CODE_EXCL_DRY, CODE_EXCL_WET = range(6)
CONFUSION_CMAP = ListedColormap([TN_COLOR, TP_COLOR, FP_COLOR, FN_COLOR, EXCL_DRY_COLOR, EXCL_WET_COLOR])

# The frontend's six depth bands (rendering/depthToImage.ts's DEPTH_BANDS).
DEPTH_EDGES = [0.01, 0.5, 2, 5, 10, 20, 1e6]
DEPTH_COLORS = ["#c6dbef", "#9ecae1", "#6baed6", "#3182bd", "#08519c", "#08306b"]
DEPTH_LABELS = ["0,01–0,5", "0,5–2", "2–5", "5–10", "10–20", "≥ 20"]

AGREE_BOTH, AGREE_TEMPORAL, AGREE_FAST = "#2a78d6", "#7b3fa0", "#c2410c"

# Temporal runs' wall-clock to the peak, measured uncontended (NumPy, i7-13620H), quoted
# rather than taken from the caches: tcc2_scenarios.py also records per-step history,
# and its runs may share the machine, so its own timings are not benchmarks.
DOCUMENTED_WALL_CLOCK_S = {
    "temporal_90m_moore": 7.6 * 60,  # docs/tcc-deviations.md section 18
    "temporal_90m_baseline": 23.3 * 60,  # section 18
    "temporal_90m_vonneumann": 4.48 * 60,  # section 22 (side by side with Moore's 7.41 min)
    "temporal_60m_moore": 20.7 * 60,  # section 25 (projected from uncontended per-step medians)
    # section 26: the run's own steps at its own rate once throttling was off (27.5 ms per macro step,
    # with per-step mass checks like section 18's 90m run); its 281 min total includes ~35 throttled min.
    "temporal_30m_moore": 556_774 * 0.0275,
}

# Fast-mode run times, medians measured unthrottled and quoted rather than re-measured per render.
DOCUMENTED_FAST_SECONDS = {
    (90, "single_cell"): 0.074,  # docs/tcc-deviations.md section 19 (median of 20)
    (90, "cross_section"): 0.073,  # section 23
    (60, "cross_section"): 0.168,  # section 24
    (30, "cross_section"): 0.658,  # section 26 (throttling disabled)
}

# Portuguese MapBiomas Collection 10 legend names for the classes in MANNING_N_BY_CLASS.
CLASS_NAMES_PT = {
    3: "Formação Florestal", 6: "Floresta Alagável", 9: "Silvicultura", 11: "Campo Alagado",
    12: "Formação Campestre", 15: "Pastagem", 21: "Mosaico de Usos", 24: "Área Urbanizada",
    25: "Outras Áreas não Vegetadas", 30: "Mineração", 33: "Rio, Lago e Oceano", 39: "Soja",
    41: "Outras Lavouras Temporárias",
}
CLASS_COLORS = {
    3: "#1f8d49", 6: "#026975", 9: "#7a5900", 11: "#519799", 12: "#d6bc74", 15: "#edde8e",
    21: "#ffefc3", 24: "#d4271e", 25: "#db4d4f", 30: "#9c0027", 33: "#2532e4", 39: "#f5b3c8",
    41: "#f54ca9",
}

plt.rcParams.update({
    "figure.dpi": 100,
    "savefig.dpi": 300,  # the TCC standard: 300 dpi at the final 16 cm width
    "font.size": 8,  # the TCC standard at the final 16 cm width: 8 pt axes and legends, 9 pt titles
    "axes.titlesize": 9,
    "legend.title_fontsize": 8,
    "axes.spines.top": False,
    "axes.spines.right": False,
})


def br(x: float, digits: int = 3) -> str:
    """A number with a Brazilian decimal comma and dot thousands separator."""
    text = f"{x:,.{digits}f}"
    return text.replace(",", "_").replace(".", ",").replace("_", ".")


COMMA = FuncFormatter(lambda x, _: br(x, 3).rstrip("0").rstrip(","))


def save(fig, name: str, dpi: int | None = None) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{name}.png"
    fig.savefig(path, bbox_inches="tight", facecolor="white", dpi=dpi)  # dpi=None: savefig.dpi
    plt.close(fig)
    print(f"  wrote {path.relative_to(settings.REPO_ROOT)}")


def load_cache(name: str):
    path = CACHE_DIR / f"{name}.npz"
    if not path.exists():
        print(f"  cache {path.name} missing - run `python -m examples.tcc2_scenarios --scenario {name}`")
        return None
    return np.load(path)


def km_extent(shape: tuple[int, int], dx: float) -> tuple[float, float, float, float]:
    rows, cols = shape
    return (0, cols * dx / 1000, 0, rows * dx / 1000)


def map_axes(ax, title: str | None = None) -> None:
    ax.set_xlabel("km")
    ax.set_ylabel("km")
    ax.set_aspect("equal")
    if title:
        ax.set_title(title)


def hillshade(ax, Z: np.ndarray, dx: float, alpha: float = 1.0) -> None:
    shade = LightSource(azdeg=315, altdeg=45).hillshade(Z, vert_exag=3, dx=dx, dy=dx)
    ax.imshow(shade, cmap="gray", extent=km_extent(Z.shape, dx), alpha=alpha, vmin=0, vmax=1)


def confusion_codes(simulated: np.ndarray, observed: np.ndarray, excluded: np.ndarray | None) -> np.ndarray:
    codes = np.full(simulated.shape, CODE_TN)
    codes[simulated & observed] = CODE_TP
    codes[simulated & ~observed] = CODE_FP
    codes[~simulated & observed] = CODE_FN
    if excluded is not None:
        codes[excluded & ~simulated] = CODE_EXCL_DRY
        codes[excluded & simulated] = CODE_EXCL_WET
    return codes


def scores(simulated: np.ndarray, observed: np.ndarray, excluded: np.ndarray | None = None) -> dict:
    if excluded is not None:
        simulated, observed = simulated[~excluded], observed[~excluded]
    tp, fp, fn = confusion_counts(simulated, observed)
    return {"tp": tp, "fp": fp, "fn": fn, "csi": csi(simulated, observed),
            "hr": hit_rate(simulated, observed), "far": false_alarm_rate(simulated, observed)}


def confusion_handles(with_gap: bool = True) -> list:
    """The error-map legend every figure uses, with or without the two Estrela-gap entries."""
    handles = [Patch(color=TP_COLOR, label="Acerto (VP)"), Patch(color=FN_COLOR, label="Omissão (FN)"),
               Patch(color=FP_COLOR, label="Falso alarme (FP)"), Patch(facecolor=TN_COLOR, edgecolor="#999", label="Seco em ambos")]
    if with_gap:
        handles += [Patch(color=EXCL_DRY_COLOR, label="Lacuna de Estrela, seco"),
                    Patch(color=EXCL_WET_COLOR, label="Lacuna de Estrela, inundado no modelo")]
    return handles


def confusion_panel(ax, Z, dx, simulated, observed, excluded, title: str | None, legend: bool = True) -> dict:
    """A confusion map; the title only names the panel (scores go in the text), None leaves it untitled."""
    s = scores(simulated, observed, excluded)
    ax.imshow(confusion_codes(simulated, observed, excluded), cmap=CONFUSION_CMAP, vmin=-0.5, vmax=5.5,
              extent=km_extent(Z.shape, dx), interpolation="nearest")
    map_axes(ax, title)
    if legend:
        ax.legend(handles=confusion_handles(excluded is not None), loc="upper center", bbox_to_anchor=(0.5, -0.14),
                  ncol=2, frameon=False)
    return s


def comma_axes(*axes) -> None:
    """km axes with a decimal comma."""
    for ax in axes:
        ax.xaxis.set_major_formatter(COMMA)
        ax.yaxis.set_major_formatter(COMMA)


def depth_panel(ax, H, Z, dx, title: str):
    hillshade(ax, Z, dx)
    masked = np.ma.masked_less_equal(H, FLOODED_DEPTH_THRESHOLD_M)
    im = ax.imshow(masked, cmap=ListedColormap(DEPTH_COLORS), norm=BoundaryNorm(DEPTH_EDGES, 6),
                   extent=km_extent(Z.shape, dx), interpolation="nearest", alpha=0.9)
    map_axes(ax, title)
    return im


def load_grid(resolution: int):
    """Z, N, inflow mask, outlet overrides and gauge cell for a scored grid (90 or 60 m)."""
    grid = settings.SCORED_GRIDS[resolution]
    dx = float(resolution)
    Z = build_elevation_matrix(processed_path=grid["dem_path"], resolution=dx)
    N = build_roughness_matrix(reference_path=grid["dem_path"], processed_path=grid["landcover_path"])
    inflow_mask = find_boundary_inflow_mask(Z, settings.HYDROGRAPH_INFLOW_EDGE)
    boundary = find_boundary_outlet(Z, N, settings.HYDROGRAPH_OUTLET_EDGE)
    return grid, dx, Z, N, inflow_mask, boundary


def peak_discharge() -> float:
    elapsed, stage = load_raw_stage_series(settings.HYDROGRAPH_RAW_PATH)
    return build_hydrograph().discharge_at(float(elapsed[int(np.argmax(stage))]))


_fast_cache: dict = {}


def fast_run(resolution: int, conveyance: str = "cross_section") -> dict:
    """Runs the fast engine once (under a second) and returns its extent with the scoring masks; memoized.
    Not timed: figures quote DOCUMENTED_FAST_SECONDS, so a re-render never moves a point."""
    key = (resolution, conveyance)
    if key in _fast_cache:
        return _fast_cache[key]
    grid, dx, Z, N, inflow_mask, (be, br_) = load_grid(resolution)
    result = classify_steady_flood(Z, N, dx, peak_discharge(), inflow_mask, boundary_elevation=be, boundary_roughness=br_,
                                   depth_threshold_m=FLOODED_DEPTH_THRESHOLD_M, conveyance=conveyance)
    observed = build_observed_flood_mask(reference_path=grid["dem_path"], processed_path=grid["flood_extent_path"])
    _, excluded = build_validation_reference(Z, reference_path=grid["dem_path"], gauge_row=grid["gauge_cell"][0],
                                             gauge_col=grid["gauge_cell"][1])
    _fast_cache[key] = {"Z": Z, "dx": dx, "result": result, "observed": observed, "excluded": excluded}
    return _fast_cache[key]


# --- figures -----------------------------------------------------------------


def fig01_area_estudo() -> None:
    """Study area: the 30 m DEM the live app runs on, with inflow, outlet and gauge."""
    Z = build_elevation_matrix()
    crs, transform = get_georeference()
    dx = settings.TARGET_RESOLUTION_METERS
    inflow = find_boundary_inflow_mask(Z, settings.HYDROGRAPH_INFLOW_EDGE)
    be, _ = find_boundary_outlet(Z, np.ones_like(Z), settings.HYDROGRAPH_OUTLET_EDGE)
    outlet_cols = np.flatnonzero(np.isfinite(be[-1, 1:-1]))
    gauge = lonlat_to_cell(GAUGE_LON, GAUGE_LAT, crs, transform, Z.shape)
    rows, cols = Z.shape
    to_km = dx / 1000

    fig, ax = plt.subplots(figsize=(6.4, 6))
    ext = km_extent(Z.shape, dx)
    hillshade(ax, Z, dx)
    im = ax.imshow(Z, cmap="terrain", extent=ext, alpha=0.55, vmin=0, vmax=Z.max())
    fig.colorbar(im, ax=ax, label="Elevação do terreno Z (m), após preenchimento de depressões", shrink=0.8)
    in_cols = np.flatnonzero(inflow[0])
    ax.plot((in_cols + 0.5) * to_km, np.full(in_cols.size, rows * to_km - 0.05), "v", color="#0a58ca", ms=5,
            label=f"Entrada (vazão ANA, {in_cols.size} células, borda norte)")
    ax.plot((outlet_cols + 0.5) * to_km, np.full(outlet_cols.size, 0.05), "v", color="#b02a37", ms=5,
            label=f"Exutório ({outlet_cols.size} células, borda sul)")
    if gauge is not None:
        gr, gc = gauge
        ax.plot((gc + 0.5) * to_km, (rows - gr - 0.5) * to_km, "*", color="#ffd400", mec="black", ms=13,
                label="Estação ANA 86879300 (Porto Fluvial de Estrela)")
    ax.text(0.2 * cols * to_km, 0.5 * rows * to_km, "LAJEADO\n(margem oeste)", ha="center", fontsize=9, weight="bold", color="#222")
    ax.text(0.85 * cols * to_km, 0.25 * rows * to_km, "ESTRELA\n(margem leste)", ha="center", fontsize=9, weight="bold", color="#222")
    map_axes(ax)  # untitled: the caption names the area, DEM, projection and grid
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.1), fontsize=7.5, frameon=False)
    save(fig, "fig01_area_estudo")


def fig02_cobertura_rugosidade() -> None:
    """MapBiomas 2024 land cover and the Manning's n matrix derived from it (30 m)."""
    Z = build_elevation_matrix()
    classes = align_to_reference_grid(settings.LANDCOVER_RAW_PATH, settings.DEM_PROCESSED_PATH)
    N = build_roughness_matrix()
    dx = settings.TARGET_RESOLUTION_METERS
    present = [c for c in sorted(MANNING_N_BY_CLASS) if (classes == c).any()]
    index = np.zeros_like(classes, dtype=int)
    for i, c in enumerate(present):
        index[classes == c] = i

    # 16 cm wide at final size: maps side by side, class names below in two columns. Each class's n
    # and share of the area are in the roughness table in the text, so the legend carries names only.
    fig, (a, b) = plt.subplots(1, 2, figsize=(6.3, 4.3))
    a.imshow(index, cmap=ListedColormap([CLASS_COLORS[c] for c in present]), vmin=-0.5, vmax=len(present) - 0.5,
             extent=km_extent(Z.shape, dx), interpolation="nearest")
    map_axes(a, "(a) Cobertura e uso da terra")
    im = b.imshow(N, cmap="YlOrBr", extent=km_extent(Z.shape, dx), interpolation="nearest")
    fig.colorbar(im, ax=b, label="Coeficiente de Manning n", fraction=0.046, pad=0.04, format=COMMA)
    map_axes(b, "(b) Matriz de rugosidade n")
    comma_axes(a, b)
    fig.legend(handles=[Patch(color=CLASS_COLORS[c], label=CLASS_NAMES_PT[c]) for c in present], ncol=2,
               loc="lower center", bbox_to_anchor=(0.5, 0.0), frameon=False, handlelength=1.2, handletextpad=0.5,
               columnspacing=1.5)
    fig.subplots_adjust(left=0.08, right=0.92, top=0.95, bottom=0.33, wspace=0.3)
    save(fig, "fig02_cobertura_rugosidade")


def fig03_poc_sintetico() -> None:
    """The synthetic proof of concept (step 1-2) with exact closed/open-system invariants."""
    Z = synthetic_terrain(GRID_SIZE, GRID_SIZE)
    N = synthetic_roughness(GRID_SIZE, GRID_SIZE)
    H = np.zeros_like(Z)
    seed_pool(H, SEED_VOLUME)
    snapshot_steps = (0, 5, 50, 100)
    snapshots, closed_err = {0: H.copy()}, []
    for t in range(1, 101):
        H = step(Z, H, N)
        closed_err.append(abs(H.sum() - SEED_VOLUME))
        if t in snapshot_steps:
            snapshots[t] = H.copy()
    H_open = np.zeros_like(Z)
    inflow = np.zeros_like(Z)
    inflow[0, GRID_SIZE // 2] = 2.0
    open_err = []
    for t in range(1, 101):
        H_open = step(Z, H_open, N, inflow=inflow)
        open_err.append(abs(H_open.sum() - 2.0 * t))

    # 16 cm wide at final size: four maps on top, the mass-conservation plot full width below.
    fig = plt.figure(figsize=(6.3, 4.2))
    grid = fig.add_gridspec(2, 4, height_ratios=[1, 1.1], hspace=0.55, wspace=0.12,
                            left=0.11, right=0.98, top=0.91, bottom=0.11)
    ax = fig.add_subplot(grid[0, 0])
    ax.imshow(Z, cmap="terrain")
    ax.set_title("Terreno sintético Z\n(bacia + colina)")
    ax = fig.add_subplot(grid[0, 1])
    ax.imshow(N, cmap="YlOrBr")
    ax.set_title("Rugosidade sintética n\n(canal diagonal liso)")
    vmax = snapshots[5].max()
    for i, t in enumerate((5, 50)):
        ax = fig.add_subplot(grid[0, 2 + i])
        ax.imshow(Z, cmap="gray", alpha=0.35)
        ax.imshow(np.ma.masked_less_equal(snapshots[t], 1e-6), cmap="Blues", vmin=0, vmax=vmax / 3)
        ax.set_title(f"Lâmina d'água\n(passo {t})")
    for ax in fig.axes:
        ax.set_xticks([])
        ax.set_yticks([])
    ax = fig.add_subplot(grid[1, :])
    ax.semilogy(range(1, 101), np.maximum(closed_err, 1e-17), label="Sistema fechado: |V(t) − 400| (piscina inicial)")
    ax.semilogy(range(1, 101), np.maximum(open_err, 1e-17), label="Sistema aberto: |V(t) − 2t| (entrada de 2 por passo)")
    ax.axhline(1e-6, color="#b02a37", ls="--", lw=1, label="Tolerância da verificação (10⁻⁶)")
    ax.set_ylim(1e-18, 1e-3)
    ax.set_xlabel("Passo de simulação")
    ax.set_ylabel("Erro de volume")
    ax.set_title("Conservação de massa: erro no nível do arredondamento\nde ponto flutuante (precisão dupla)")
    # Between the error curves (<= 1e-13) and the tolerance line (1e-6).
    ax.legend(frameon=False, loc="center", bbox_to_anchor=(0.5, 0.6))
    save(fig, "fig03_poc_sintetico")


def fig04_hidrograma() -> None:
    """The real May 2024 ANA record: stage, discharge, and the empirical rating curve."""
    elapsed, stage = load_raw_stage_series(settings.HYDROGRAPH_RAW_PATH)
    hydro = build_hydrograph()
    pairs = np.array(find_calibration_pairs(settings.HYDROGRAPH_RAW_PATH))
    dates = [RECORD_START + timedelta(seconds=float(s)) for s in elapsed]
    qdates = [RECORD_START + timedelta(seconds=float(s)) for s in hydro.elapsed_seconds]
    peak = int(np.argmax(stage))

    # 16 cm wide at final size: (a) full width on top, (b) smaller and centred below. The note that
    # discharge is held fixed below the lowest rating pair goes in the caption.
    fig = plt.figure(figsize=(6.3, 5.6))
    grid = fig.add_gridspec(2, 6, height_ratios=[1.15, 1], left=0.1, right=0.9, top=0.95, bottom=0.09, hspace=0.45)
    a, b = fig.add_subplot(grid[0, :]), fig.add_subplot(grid[1, 1:5])
    a.plot(dates, stage, color="#0a58ca", lw=1.4, label="Cota (m)")
    a.set_ylabel("Cota na régua (m)", color="#0a58ca")
    a2 = a.twinx()
    a2.spines["right"].set_visible(True)
    a2.plot(qdates, hydro.discharge_m3s / 1000, color="#c2410c", lw=1.2, ls="--", label="Vazão (mil m³/s)")
    a2.set_ylabel("Vazão (mil m³/s)", color="#c2410c")
    a.axvline(dates[peak], color="#444", lw=0.8, ls=":")
    a.annotate(f"Pico: {br(stage[peak], 2)} m\n{dates[peak]:%d/%m %H:%M}\n{br(hydro.peak_discharge_m3s, 0)} m³/s",
               (dates[peak], stage[peak]), xytext=(0.62, 0.62), textcoords="axes fraction", fontsize=8,
               arrowprops={"arrowstyle": "->", "color": "#444"})
    a.set_title("(a) Estação 86879300, Porto Fluvial de Estrela (ANA/SGB), abr–mai 2024")
    a.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%d/%m"))
    a.yaxis.set_major_formatter(COMMA)
    a2.yaxis.set_major_formatter(COMMA)
    b.plot(pairs[:, 0], pairs[:, 1] / 1000, ".", ms=3, color="#c2410c")
    b.set_xlabel("Cota (m)")
    b.set_ylabel("Vazão (mil m³/s)")
    b.xaxis.set_major_formatter(COMMA)
    b.yaxis.set_major_formatter(COMMA)
    b.set_title(f"(b) Curva-chave da estação ({len(pairs)} pares cota–vazão)")
    print(f"  peak stage {stage[peak]:.2f} m at {dates[peak]:%d/%m %H:%M}, {hydro.peak_discharge_m3s:.1f} m3/s; "
          f"{len(pairs)} rating pairs, lowest stage {pairs[0, 0]:.2f} m")
    save(fig, "fig04_hidrograma")


def fig05_passo_tempo_balanco() -> None:
    """Adaptive CFL dt and the water budget over the validated 90 m run."""
    d = load_cache("temporal_90m_moore")
    if d is None:
        return
    hours = d["elapsed_s"] / 3600
    dx = float(d["resolution"])
    to_hm3 = dx**2 / 1e6  # summed depth (m) x cell area -> 10^6 m3
    fig, (a, b, c) = plt.subplots(3, 1, figsize=(6.3, 6.8), sharex=True)  # 16 cm wide at final size
    a.semilogy(hours, d["dt_cfl_s"], lw=0.6, color="#888", label=r"Limite CFL: $\Delta t = \Delta x \,/\, v_{\max}$")
    a.semilogy(hours, d["dt_s"], lw=0.8, color="#0a58ca", label=r"$\Delta t$ usado (limitado a 900 s)")
    a.set_ylabel("Passo de tempo (s)")
    a.set_title("(a) Passo de tempo adaptativo")
    a.legend(frameon=False, loc="upper right")
    b.plot(hours, d["cum_inflow"] * to_hm3, label="Entrada acumulada (vazão ANA)", color="#0a58ca")
    b.plot(hours, d["cum_outflow"] * to_hm3, label="Saída acumulada (exutório)", color="#b02a37")
    b.plot(hours, d["volume"] * to_hm3, label="Volume armazenado na grade", color="#1baf7a")
    b.set_ylabel("Volume (hm³)")
    b.set_title("(b) Balanço hídrico: armazenado = entrada − saída em todos os passos")
    b.legend(frameon=False)
    thousands = FuncFormatter(lambda x, _: br(x, 0))
    b.yaxis.set_major_formatter(thousands)
    c.yaxis.set_major_formatter(thousands)
    c.plot(hours, d["flooded_cells"], color="#2a78d6")
    c.set_ylabel("Células inundadas (> 0,01 m)")
    c2 = c.twinx()
    c2.spines["right"].set_visible(True)
    c2.plot(hours, d["discharge_m3s"] / 1000, color="#c2410c", ls="--", lw=1)
    c2.set_ylabel("Vazão de entrada (mil m³/s)", color="#c2410c")
    c.set_xlabel("Tempo simulado (h desde 27/04/2024 00:00)")
    c.set_title("(c) Extensão inundada e vazão de entrada")
    fig.tight_layout()
    save(fig, "fig05_passo_tempo_balanco")


def fig06_sequencia_inundacao() -> None:
    d = load_cache("temporal_90m_moore")
    if d is None:
        return
    Z, dx = d["Z"], float(d["resolution"])
    frames = [(s, d["snapshots"][i]) for i, s in enumerate(d["snapshot_seconds"])] + [(float(d["peak_elapsed_s"]), d["H"])]
    # 16 cm wide at final size; untitled (the caption carries the title).
    fig, axes = plt.subplots(2, 3, figsize=(6.3, 5.0), sharex=True, sharey=True)
    for ax, (seconds, H) in zip(axes.flat, frames):
        when = RECORD_START + timedelta(seconds=seconds)
        wet = int((H > FLOODED_DEPTH_THRESHOLD_M).sum())
        depth_panel(ax, H, Z, dx, f"t = {br(seconds / 3600, 1)} h ({when:%d/%m %H:%M})\n{br(wet, 0)} células")
        ax.label_outer()
    comma_axes(*axes.flat)
    fig.legend(handles=[Patch(color=c, label=f"{label} m") for c, label in zip(DEPTH_COLORS, DEPTH_LABELS)],
               loc="lower center", bbox_to_anchor=(0.5, 0.0), ncol=6, frameon=False, title="Profundidade da água",
               handlelength=1.2, handletextpad=0.4, columnspacing=1.0)
    fig.subplots_adjust(left=0.08, right=0.99, top=0.93, bottom=0.2, wspace=0.08, hspace=0.32)
    save(fig, "fig06_sequencia_inundacao")


def fig07_tempo_chegada_profundidade_max() -> None:
    d = load_cache("temporal_90m_moore")
    if d is None:
        return
    Z, dx = d["Z"], float(d["resolution"])
    # 16 cm wide at final size: each panel's key sits below it (a colour bar for (a), depth bands for (b)).
    fig, (a, b) = plt.subplots(1, 2, figsize=(6.3, 4.3))
    hillshade(a, Z, dx)
    im = a.imshow(np.ma.masked_invalid(d["first_wet_s"] / 3600), cmap="magma_r", extent=km_extent(Z.shape, dx),
                  interpolation="nearest", alpha=0.9)
    map_axes(a, "(a) Tempo de chegada da água")
    depth_panel(b, d["max_depth"], Z, dx, "(b) Profundidade máxima até o pico")
    comma_axes(a, b)
    fig.subplots_adjust(left=0.08, right=0.99, top=0.94, bottom=0.3, wspace=0.28)
    cax = fig.add_axes([a.get_position().x0, 0.1, a.get_position().width, 0.03])
    fig.colorbar(im, cax=cax, orientation="horizontal",
                 label="Horas desde o início do registro\naté a lâmina passar de 0,01 m")
    b.legend(handles=[Patch(color=c, label=f"{label} m") for c, label in zip(DEPTH_COLORS, DEPTH_LABELS)],
             loc="upper center", bbox_to_anchor=(0.5, -0.17), ncol=3, frameon=False, title="Profundidade da água",
             handlelength=1.2, handletextpad=0.4, columnspacing=1.0)
    save(fig, "fig07_tempo_chegada_profundidade_max")


def fig08_validacao_90m() -> None:
    d = load_cache("temporal_90m_moore")
    if d is None:
        return
    Z, dx, H = d["Z"], float(d["resolution"]), d["H"]
    observed, excluded = d["observed"], d["excluded"]
    simulated = H > FLOODED_DEPTH_THRESHOLD_M
    # 16 cm wide at final size: a 2x2 grid with one legend block below, one group per panel type.
    fig, axes = plt.subplots(2, 2, figsize=(6.3, 7.6))
    (a, b), (c, d_) = axes
    hillshade(a, Z, dx)
    a.imshow(np.ma.masked_where(~observed, observed), cmap=ListedColormap(["#2a78d6"]), extent=km_extent(Z.shape, dx), alpha=0.8)
    a.imshow(np.ma.masked_where(~excluded, excluded), cmap=ListedColormap(["#9c988f"]), extent=km_extent(Z.shape, dx), alpha=0.55)
    map_axes(a, "(a) Referência SGB/CPRM, cota 33,67 m")
    depth_panel(b, H, Z, dx, "(b) AC temporal no pico, t = 133,5 h")
    naive = confusion_panel(c, Z, dx, simulated, observed, None, "(c) Avaliação ingênua (domínio inteiro)", legend=False)
    gap = confusion_panel(d_, Z, dx, simulated, observed, excluded, "(d) Lacuna de Estrela excluída", legend=False)
    print(f"  observed {int(observed.sum())}, gap {int(excluded.sum())}, simulated {int(simulated.sum())}; "
          f"naive {naive['tp']}/{naive['fp']}/{naive['fn']} CSI {naive['csi']:.4f}; gap {gap['tp']}/{gap['fp']}/{gap['fn']} CSI {gap['csi']:.4f}")
    comma_axes(*axes.flat)
    groups = (
        ("(a) Referência", [Patch(color="#2a78d6", label="Inundado na referência"),
                            Patch(color="#9c988f", label=f"Lacuna de cobertura em Estrela ({br(int(excluded.sum()), 0)} células)")], 2),
        ("(b) Profundidade da água", [Patch(color=c_, label=f"{label} m") for c_, label in zip(DEPTH_COLORS, DEPTH_LABELS)], 6),
        ("(c, d) Mapa de erro", confusion_handles(), 3),
    )
    for (title, handles, ncol), y in zip(groups, (0.215, 0.158, 0.101)):
        fig.legend(handles=handles, title=title, ncol=ncol, loc="upper center", bbox_to_anchor=(0.5, y), frameon=False,
                   handlelength=1.2, handletextpad=0.4, columnspacing=1.0, borderaxespad=0)
    fig.subplots_adjust(left=0.09, right=0.99, top=0.97, bottom=0.27, wspace=0.25, hspace=0.3)
    save(fig, "fig08_validacao_90m")


# outflow_fraction sweep at 90 m, May 2024 peak - docs/tcc-deviations.md section 16.3 (13 full runs).
SWEEP_FRACTIONS = [0.05, 0.07, 0.085, 0.1, 0.115, 0.13, 0.15, 0.2, 0.3, 0.5, 0.6, 0.7, 0.8]
SWEEP_NAIVE_CSI = [0.363, 0.390, 0.395, 0.390, 0.383, 0.374, 0.358, 0.323, 0.221, 0.133, 0.113, 0.110, 0.101]


def fig09_calibracao_outflow() -> None:
    """outflow_fraction sweep under all three scorings - numbers from docs/tcc-deviations.md section 16.3."""
    f, naive = SWEEP_FRACTIONS, SWEEP_NAIVE_CSI
    gap = [0.848, 0.891, 0.900, 0.870, 0.836, 0.800, 0.754, 0.662, 0.406, 0.179, 0.139, 0.128, 0.116]
    bundled = [0.819, 0.868, 0.878, 0.841, 0.800, 0.755, 0.699, 0.588, 0.314, 0.059, 0.018, 0.010, 0.006]
    fig, ax = plt.subplots(figsize=(6.3, 3.7))  # 16 cm wide at final size
    ax.axvspan(0.07, 0.1, color="#ffd400", alpha=0.25, label="Patamar (0,07 a 0,10)")
    ax.plot(f, gap, "o-", color="#2a78d6", ms=4, label="CSI com a lacuna de Estrela excluída")
    ax.plot(f, bundled, "s--", color="#7b3fa0", ms=3.5, label="CSI agregado (lacuna + canal permanente)")
    ax.plot(f, naive, "^-", color="#888", ms=3.5, label="CSI ingênuo (domínio inteiro)")
    ax.annotate("Valor adotado\n(CSI 0,900)", (0.085, 0.900), xytext=(0.2, 0.97), arrowprops={"arrowstyle": "->"}, fontsize=8)
    ax.annotate("Valor inicial\n(CSI 0,179)", (0.5, 0.179), xytext=(0.55, 0.38), arrowprops={"arrowstyle": "->"}, fontsize=8)
    ax.set_xscale("log")
    ax.set_xticks([0.05, 0.07, 0.1, 0.15, 0.2, 0.3, 0.5, 0.8])  # the plateau edges and the initial 0.5 labelled
    ax.xaxis.set_major_formatter(COMMA)
    ax.xaxis.set_minor_formatter(FuncFormatter(lambda *_: ""))
    ax.yaxis.set_major_formatter(COMMA)
    ax.set_xlabel("Fração de liberação por passo (escala logarítmica)")
    ax.set_ylabel("CSI")
    ax.set_ylim(-0.02, 1.1)
    ax.legend(fontsize=8, frameon=False, loc="lower left")
    fig.subplots_adjust(left=0.1, right=0.98)  # so the tight crop stays ~16 cm wide
    save(fig, "fig09_calibracao_outflow")


def fig09_calibracao_ingenuo() -> None:
    """The same sweep, naive CSI only (no Estrela-gap scorings). Untitled; the caption carries the title."""
    f, naive = SWEEP_FRACTIONS, SWEEP_NAIVE_CSI
    fig, ax = plt.subplots(figsize=(7.5, 4.3))
    ax.axvspan(0.07, 0.1, color="#ffd400", alpha=0.25, label="Patamar (0,07 a 0,10)")
    ax.plot(f, naive, "o-", color="#2a78d6", label="CSI ingênuo (domínio inteiro)")
    ax.annotate("Valor adotado\n(CSI 0,395)", (0.085, 0.395), xytext=(0.16, 0.41), arrowprops={"arrowstyle": "->"}, fontsize=8)
    ax.annotate("Primeira simulação\n(CSI 0,133)", (0.5, 0.133), xytext=(0.36, 0.25), arrowprops={"arrowstyle": "->"}, fontsize=8)
    ax.set_xscale("log")
    ax.set_xticks([0.05, 0.07, 0.1, 0.15, 0.2, 0.3, 0.5, 0.8])  # the plateau edges and the first run's 0.5 labelled
    ax.xaxis.set_major_formatter(COMMA)
    ax.xaxis.set_minor_formatter(FuncFormatter(lambda *_: ""))
    ax.set_ylim(0, 0.45)
    ax.yaxis.set_major_formatter(COMMA)
    ax.set_xlabel("Fração de liberação por passo (escala logarítmica)")
    ax.set_ylabel("CSI")
    ax.legend(fontsize=7, frameon=False, loc="lower left")
    save(fig, "fig09_calibracao_ingenuo")


def fig10_primeiro_resultado() -> None:
    """The first result on the real event: the step-10 baseline (outflow_fraction=0.5) at the peak,
    scored naively over the whole grid like fig08(c). Untitled; the caption carries the title."""
    d = load_cache("temporal_90m_baseline")
    if d is None:
        return
    simulated, observed = d["H"] > FLOODED_DEPTH_THRESHOLD_M, d["observed"]
    # Axes sized in inches to match one panel of fig08's 17 x 5.4 in row, so the two print at the same scale.
    width, height = 2.86, 2.73
    fig = plt.figure(figsize=(width + 1, height + 1.6))
    ax = fig.add_axes([0.6 / (width + 1), 1.2 / (height + 1.6), width / (width + 1), height / (height + 1.6)])
    s = confusion_panel(ax, d["Z"], float(d["resolution"]), simulated, observed, None, None)
    print(f"  VP {s['tp']}, FP {s['fp']}, FN {s['fn']}; simulated {int(simulated.sum())}, observed {int(observed.sum())}; "
          f"CSI {s['csi']:.3f}, hit rate {s['hr']:.3f}, false alarm rate {s['far']:.3f}")
    save(fig, "fig10_primeiro_resultado")


def fig11_margem_exutorio() -> None:
    """Outlet-margin sweep - numbers from docs/tcc-deviations.md section 15 (7 full runs)."""
    drop = [0.01, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0]
    csi_values = [0.13327, 0.13327, 0.13315, 0.13327, 0.13315, 0.13327, 0.13411]
    fig, ax = plt.subplots(figsize=(7, 3.8))
    ax.axhspan(0.1333, 0.1333 + 0.1459, color="#eb6834", alpha=0.15,
               label="Ganho de CSI só por deslocar a máscara 1–3 células (+0,146)")
    ax.plot(drop, csi_values, "o-", color="#2a78d6", label="CSI ingênuo por margem do exutório")
    ax.set_xscale("log")
    ax.set_ylim(0.1, 0.3)
    ax.set_yticks([0.1, 0.15, 0.2, 0.25, 0.3])
    ax.set_xticks(drop)
    ax.xaxis.set_major_formatter(COMMA)
    ax.yaxis.set_major_formatter(COMMA)
    ax.set_xlabel("Margem de descida do exutório drop_m (m, escala log)")
    ax.set_ylabel("CSI")
    ax.set_title("Sensibilidade à margem do exutório: amplitude 0,00096 (resultado negativo)\n90 m, outflow_fraction = 0,5")
    ax.legend(frameon=False, loc="upper left")
    save(fig, "fig11_margem_exutorio")


def fig12_modo_rapido() -> None:
    single, cross = fast_run(90, "single_cell"), fast_run(90, "cross_section")
    Z, dx = cross["Z"], cross["dx"]
    r = cross["result"]
    # 16 cm wide at final size: (a) centred on top with its state legend beside it, (b) and (c) below
    # sharing the error-map legend.
    fig = plt.figure(figsize=(6.3, 7.0))
    grid = fig.add_gridspec(2, 4, left=0.09, right=0.99, top=0.96, bottom=0.13, wspace=0.6, hspace=0.3)
    a, b, c = fig.add_subplot(grid[0, 1:3]), fig.add_subplot(grid[1, 0:2]), fig.add_subplot(grid[1, 2:4])
    hillshade(a, Z, dx)
    states = np.full(Z.shape, np.nan)
    states[r.state == INUNDATED] = 0
    states[r.state == CONVEYING] = 1
    states[r.state == EXITING] = 2
    a.imshow(np.ma.masked_invalid(states), cmap=ListedColormap(["#9ecae1", "#08306b", "#b02a37"]), vmin=-0.5, vmax=2.5,
             extent=km_extent(Z.shape, dx), interpolation="nearest", alpha=0.9)
    map_axes(a, "(a) Estados do modo rápido (seção transversal)")
    a.legend(handles=[Patch(color="#08306b", label=f"Transportando\n({br(int((r.state == CONVEYING).sum()), 0)} células)"),
                      Patch(color="#b02a37", label=f"Saindo pelo exutório\n({br(int((r.state == EXITING).sum()), 0)} célula)"),
                      Patch(color="#9ecae1", label=f"Inundada lateralmente\n({br(int((r.state == INUNDATED).sum()), 0)} células)")],
             loc="center left", bbox_to_anchor=(1.04, 0.5), frameon=False, handlelength=1.2, handletextpad=0.5, labelspacing=0.9)
    single_s = confusion_panel(b, Z, dx, single["result"].flooded, single["observed"], single["excluded"],
                               "(b) Primeira regra: canal de uma célula", legend=False)
    cross_s = confusion_panel(c, Z, dx, r.flooded, cross["observed"], cross["excluded"], "(c) Curva-chave HAND por seção",
                              legend=False)
    print(f"  states {int((r.state == CONVEYING).sum())}/{int((r.state == EXITING).sum())}/{int((r.state == INUNDATED).sum())}; "
          f"single {single_s['tp']}/{single_s['fp']}/{single_s['fn']} CSI {single_s['csi']:.4f}; "
          f"cross {cross_s['tp']}/{cross_s['fp']}/{cross_s['fn']} CSI {cross_s['csi']:.4f}")
    comma_axes(a, b, c)
    fig.legend(handles=confusion_handles(), ncol=3, loc="lower center", bbox_to_anchor=(0.5, 0.0), frameon=False,
               handlelength=1.2, handletextpad=0.4, columnspacing=1.0)
    save(fig, "fig12_modo_rapido")


def fig13_temporal_vs_rapido() -> None:
    d = load_cache("temporal_90m_moore")
    if d is None:
        return
    fast = fast_run(90)
    Z, dx = d["Z"], float(d["resolution"])
    temporal = d["H"] > FLOODED_DEPTH_THRESHOLD_M
    quick = fast["result"].flooded
    both, t_only, f_only = temporal & quick, temporal & ~quick, ~temporal & quick
    codes = np.full(Z.shape, np.nan)
    codes[both], codes[t_only], codes[f_only] = 0, 1, 2
    print(f"  agreement CSI {csi(quick, temporal):.3f}")
    fig, ax = plt.subplots(figsize=(6.3, 6))
    hillshade(ax, Z, dx)
    ax.imshow(np.ma.masked_invalid(codes), cmap=ListedColormap([AGREE_BOTH, AGREE_TEMPORAL, AGREE_FAST]), vmin=-0.5, vmax=2.5,
              extent=km_extent(Z.shape, dx), interpolation="nearest", alpha=0.85)
    map_axes(ax)  # untitled: the caption carries the title, the agreement CSI and the run times
    ax.legend(handles=[Patch(color=AGREE_BOTH, label=f"Inundado nos dois ({br(int(both.sum()), 0)})"),
                       Patch(color=AGREE_TEMPORAL, label=f"Só no AC temporal ({br(int(t_only.sum()), 0)})"),
                       Patch(color=AGREE_FAST, label=f"Só no modo rápido ({br(int(f_only.sum()), 0)})")],
              loc="upper center", bbox_to_anchor=(0.5, -0.1), fontsize=8, frameon=False, ncol=1)
    save(fig, "fig13_temporal_vs_rapido")


def fig14_moore_vs_vonneumann() -> None:
    moore, vn = load_cache("temporal_90m_moore"), load_cache("temporal_90m_vonneumann")
    if moore is None or vn is None:
        return
    Z, dx = moore["Z"], float(moore["resolution"])
    m_wet, v_wet = moore["H"] > FLOODED_DEPTH_THRESHOLD_M, vn["H"] > FLOODED_DEPTH_THRESHOLD_M
    # Sized for a 16 cm wide A4 portrait figure at final size; the CSI and counts live in the text's table.
    fig, (a, b) = plt.subplots(1, 2, figsize=(6.3, 4.0))
    confusion_panel(a, Z, dx, v_wet, vn["observed"], vn["excluded"], "(a) Vizinhança de von Neumann", legend=False)
    a.legend(handles=confusion_handles(), loc="upper center", bbox_to_anchor=(0.5, -0.15), ncol=1, fontsize=8, frameon=False,
             handlelength=1.2, handletextpad=0.5)
    hillshade(b, Z, dx)
    codes = np.full(Z.shape, np.nan)
    codes[m_wet & v_wet], codes[v_wet & ~m_wet], codes[m_wet & ~v_wet] = 0, 1, 2
    b.imshow(np.ma.masked_invalid(codes), cmap=ListedColormap([AGREE_BOTH, "#eb6834", "#1baf7a"]), vmin=-0.5, vmax=2.5,
             extent=km_extent(Z.shape, dx), interpolation="nearest", alpha=0.85)
    map_axes(b, "(b) Diferença entre as vizinhanças")
    counts = {"both": int((m_wet & v_wet).sum()), "vn": int((v_wet & ~m_wet).sum()), "moore": int((m_wet & ~v_wet).sum())}
    print(f"  both {counts['both']}, von Neumann only {counts['vn']}, Moore only {counts['moore']}")
    b.legend(handles=[Patch(color=AGREE_BOTH, label=f"Inundado nas duas ({br(counts['both'], 0)})"),
                      Patch(color="#eb6834", label=f"Só von Neumann ({br(counts['vn'], 0)})"),
                      Patch(color="#1baf7a", label=f"Só Moore ({br(counts['moore'], 0)})")],
             loc="upper center", bbox_to_anchor=(0.5, -0.15), ncol=1, fontsize=8, frameon=False, handlelength=1.2, handletextpad=0.5)
    comma_axes(a, b)
    fig.subplots_adjust(left=0.08, right=0.99, top=0.95, bottom=0.36, wspace=0.28)
    save(fig, "fig14_moore_vs_vonneumann")


def fig15_resolucao_60_30m() -> None:
    """The temporal CA on the 60 m and 30 m grids side by side, scored with the Estrela gap excluded.
    16 cm wide at final size; the panel titles name the grid only, the caption carries the rest."""
    t60, t30 = load_cache("temporal_60m_moore"), load_cache("temporal_30m_moore")
    if t60 is None or t30 is None:
        return
    fig, axes = plt.subplots(1, 2, figsize=(6.3, 3.75))
    for ax, d, title in ((axes[0], t60, "(a) 60 m"), (axes[1], t30, "(b) 30 m")):
        s = confusion_panel(ax, d["Z"], float(d["resolution"]), d["H"] > FLOODED_DEPTH_THRESHOLD_M, d["observed"], d["excluded"],
                            title, legend=False)
        print(f"  {title}: VP {s['tp']}, FP {s['fp']}, FN {s['fn']}; CSI {s['csi']:.3f}")
    comma_axes(*axes)
    # Column-major fill: (VP, FN) | (FP, dry in both) | the two gap entries.
    fig.legend(handles=confusion_handles(), loc="lower center", bbox_to_anchor=(0.5, 0.0), ncol=3, frameon=False,
               handlelength=1.2, handletextpad=0.5, columnspacing=1.2)
    fig.subplots_adjust(left=0.09, right=0.99, top=0.94, bottom=0.24, wspace=0.28)
    save(fig, "fig15_resolucao_60_30m")


def fig16_desempenho() -> None:
    """Step-11 performance - numbers from docs/tcc-deviations.md section 25 (i7-13620H, RTX 4050 Laptop).
    16 cm wide at final size (A4 portrait); the speedup bars are a table in the text, not a panel."""
    syn = np.array([1024, 4096, 16384, 65536, 262144, 1048576, 4194304])
    real = np.array([3904, 8736, 35136])
    numpy_ms = ([1.46, 2.84, 8.49, 56.7, 418, 1717, 7153], [2.83, 5.03, 20.1])
    cupy_ms = ([16.7, 17.0, 16.3, 15.4, 16.1, 78.7, 390], [15.6, 16.4, 17.0])
    fused_ms = ([1.23, 1.75, 2.71, 5.82, 19.7, 72.3, 282], [1.52, 1.83, 4.02])
    loops_ms = ([38.9, 157, 650, 2744], [155, 354, 1460])
    fig, (a, b) = plt.subplots(1, 2, figsize=(6.0, 3.2))
    for (s, r), label, color in ((loops_ms, "Laços em Python", "#888"), (numpy_ms, "NumPy (CPU)", "#2a78d6"),
                                 (cupy_ms, "CuPy (GPU)", "#7b3fa0"), (fused_ms, "CuPy fundido (GPU)", "#1baf7a")):
        a.loglog(syn[:len(s)], s, "o-", color=color, label=label, ms=3, lw=1.2)
        a.loglog(real, r, "*", color=color, ms=8, mec="black", mew=0.4)
    # 90 m and 60 m sit close on the log axis, so their labels lean away from each other.
    for cells, name, ha in zip(real, ("90 m", "60 m", "30 m"), ("right", "center", "left")):
        a.axvline(cells, color="#ccc", lw=0.6, zorder=0)
        a.text(cells, 1.02, name, transform=a.get_xaxis_transform(), ha=ha, fontsize=8)
    a.set_xlabel("Células da grade")
    a.set_ylabel("Tempo por passo (ms)")
    a.set_title("(a) Tempo por passo × tamanho da grade", pad=14)
    handles = a.get_legend_handles_labels()[0] + [
        Line2D([], [], marker="*", ls="", color="#bbb", ms=8, mec="black", mew=0.4, label="= grades reais")]
    a.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=2, fontsize=8, frameon=False,
             handlelength=1.6, columnspacing=1.0)
    steps = [10, 100, 1000, 10000]
    for wall, name, color in (([0.03, 0.32, 3.20, 32.2], "90 m", "#2a78d6"), ([0.06, 0.56, 5.62, 56.4], "60 m", "#7b3fa0"),
                              ([0.22, 2.18, 21.8, 218], "30 m", "#c2410c")):
        b.loglog(steps, wall, "o-", color=color, label=name, ms=3, lw=1.2)
    b.set_xlabel("Passos simulados")
    b.set_ylabel("Tempo de execução (s)")
    b.set_title("(b) Tempo × número de passos", pad=14)
    b.legend(fontsize=8, frameon=False, loc="upper left")
    for ax in (a, b):
        ax.tick_params(labelsize=9)
        ax.xaxis.label.set_size(9)
        ax.yaxis.label.set_size(9)
        ax.title.set_size(10)
        for axis in (ax.xaxis, ax.yaxis):
            if axis is not a.xaxis:  # cell counts stay as powers of ten: "1.000.000" crowds its neighbours
                axis.set_major_formatter(COMMA)
            axis.set_minor_formatter(NullFormatter())
    fig.subplots_adjust(left=0.1, right=0.98, top=0.88, bottom=0.17, wspace=0.38)
    save(fig, "fig16_desempenho", dpi=300)


def fig17_velocidade_precisao() -> None:
    """Accuracy vs. wall-clock for every scored configuration: CSI from the caches and fast runs, times documented."""
    points = []
    for name, label in (("temporal_90m_baseline", "Temporal 90 m, 0,5 (original)"), ("temporal_90m_moore", "Temporal 90 m, 0,085 (validado)"),
                        ("temporal_90m_vonneumann", "Temporal 90 m, von Neumann"), ("temporal_60m_moore", "Temporal 60 m, 0,085"),
                        ("temporal_30m_moore", "Temporal 30 m, 0,085")):
        d = load_cache(name)
        if d is not None:
            s = scores(d["H"] > FLOODED_DEPTH_THRESHOLD_M, d["observed"], d["excluded"])
            points.append((DOCUMENTED_WALL_CLOCK_S[name], s["csi"], label, "#2a78d6"))
    for res, conv, label in ((90, "single_cell", "Rápido 90 m, canal de 1 célula"), (90, "cross_section", "Rápido 90 m, seção HAND"),
                             (60, "cross_section", "Rápido 60 m, seção HAND"), (30, "cross_section", "Rápido 30 m, seção HAND")):
        f = fast_run(res, conv)
        s = scores(f["result"].flooded, f["observed"], f["excluded"])
        points.append((DOCUMENTED_FAST_SECONDS[(res, conv)], s["csi"], label, "#c2410c"))
    # 16 cm wide at final size, untitled (the caption carries the title). Labels break after the
    # resolution so they stay narrow on the log axis; each sits above, below or beside its point.
    fig, ax = plt.subplots(figsize=(6.3, 4.3))
    above, below, left = (0, 6, "center", "bottom"), (0, -6, "center", "top"), (-7, 0, "right", "center")
    placement = {"Rápido 90 m, seção HAND": above, "Rápido 60 m, seção HAND": below,
                 "Temporal 90 m, 0,085 (validado)": above, "Temporal 30 m, 0,085": above, "Temporal 60 m, 0,085": below,
                 "Temporal 90 m, von Neumann": below, "Temporal 90 m, 0,5 (original)": left}
    for seconds, value, label, color in points:
        dx_pt, dy_pt, ha, va = placement.get(label, (7, 0, "left", "center"))
        ax.semilogx(seconds, value, "o", color=color, ms=6)
        ax.annotate(f"{label.replace(', ', chr(10), 1)}\nCSI {br(value)}", (seconds, value), xytext=(dx_pt, dy_pt),
                    textcoords="offset points", fontsize=8, ha=ha, va=va, linespacing=1.1)
    ax.set_xlim(0.01, 1e5)  # the 30 m temporal run sits at ~1.5e4 s
    ax.set_ylim(0.1, 1.08)  # room for the labels above the top points
    ax.set_yticks(np.arange(0.2, 1.01, 0.1))
    ax.yaxis.set_major_formatter(COMMA)
    ax.set_xlabel("Tempo até a extensão final (s, escala logarítmica)")
    ax.set_ylabel("CSI (lacuna de Estrela excluída)")
    ax.legend(handles=[Line2D([], [], marker="o", ls="", color="#2a78d6", label="AC temporal (até o pico)"),
                       Line2D([], [], marker="o", ls="", color="#c2410c", label="Modo rápido (regime permanente)")],
              fontsize=8, frameon=False, loc="lower left")
    fig.subplots_adjust(left=0.1, right=0.98)  # so the tight crop stays ~16 cm wide
    save(fig, "fig17_velocidade_precisao")


FIGURES = (
    fig01_area_estudo, fig02_cobertura_rugosidade, fig03_poc_sintetico, fig04_hidrograma, fig05_passo_tempo_balanco,
    fig06_sequencia_inundacao, fig07_tempo_chegada_profundidade_max, fig08_validacao_90m, fig09_calibracao_outflow,
    fig09_calibracao_ingenuo, fig10_primeiro_resultado, fig11_margem_exutorio, fig12_modo_rapido, fig13_temporal_vs_rapido,
    fig14_moore_vs_vonneumann, fig15_resolucao_60_30m, fig16_desempenho, fig17_velocidade_precisao,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", nargs="+", metavar="PREFIX",
                        help="figure names or prefixes, e.g. fig09 (both fig09 variants) or fig09_calibracao_ingenuo")
    args = parser.parse_args()
    prefixes = args.only or [""]
    unmatched = [p for p in prefixes if not any(f.__name__.startswith(p) for f in FIGURES)]
    if unmatched:
        parser.error(f"no figure matches {', '.join(unmatched)}")
    for figure in FIGURES:
        if any(figure.__name__.startswith(p) for p in prefixes):
            print(f"{figure.__name__}:")
            figure()


if __name__ == "__main__":
    main()
