"""Re-score the outflow_fraction sweep excluding stage-invariant SGB cells
(roadmap step 10/11 follow-up, continuing check_riverbank_coverage.py).

check_riverbank_coverage.py found something more specific than an "Estrela
bank" geometric split: restricted to the Estrela side, the SGB reference
polygon's flooded cells are the *exact same* 48 cells (bit-identical mask,
Z=11-13m matching the channel bed) at COTA_1900cm (19.00m, near-baseflow),
COTA_2600cm (26.00m, mid), and COTA_3367cm (33.67m, this project's peak) -
the reference's flood extent never grows there at all, unlike the Lajeado
side (106 -> 430 -> 783 cells across the same three stages). The riverbank
split was a strong correlate of this, but the real mechanism is per-cell
stage-invariance, testable directly without any geometric bank proxy: for
every cell in the grid, is its flooded/dry status IDENTICAL across all three
queried stages? A cell that never changes status across a 14.67m stage range
(19.00m to 33.67m) carries no stage-discriminating information either way -
if frozen flooded, it's just the permanent channel; if frozen dry despite
sitting right next to a model-simulated flood, the reference simply never
registered it as flooded at any tested stage, which is indistinguishable
from a coverage gap and an unfair basis for penalizing the model.

This does NOT re-run the engine. It reloads validate_may2024.py's
--save-masks .npz outputs already on disk in data/sweep_outputs/ (the
outflow_fraction sweep, docs/tcc-deviations.md section 16) and rescopes
CSI/Hit Rate/False Alarm Rate to the valid (non-frozen) cells only, for
every swept value, reporting the naive (whole-domain) and corrected numbers
side by side.

Report only - no fix, no live default touched.

Run from the backend/ directory with the venv active:
    python -m examples.rescore_stage_invariant [--sweep-dir PATH] [--out-png PATH]
"""

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import rasterio
import requests
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch

from config import settings
from ingestion.flood_extent import reproject_geometry, rasterize_flood_extent
from validation.metrics import confusion_counts, csi, false_alarm_rate, hit_rate
from examples.shift_search_noise_floor import _shift_mask

# The same three stage layers check_riverbank_coverage.py queried: lowest
# available (near-baseflow), a mid stage, and this project's own peak
# (COTA_3367cm, id=18 - already FLOOD_EXTENT_LAYER_ID/FLOOD_EXTENT_RAW_PATH's
# stage elsewhere in this codebase). Kept as a local constant, not promoted
# to config/settings.py, since this three-stage query is specific to this
# one-off diagnostic, not the live pipeline.
_STAGE_LAYERS = [(3, "COTA_1900cm", 19.00), (10, "COTA_2600cm", 26.00), (18, "COTA_3367cm", 33.67)]

def _discover_sweep_values(sweep_dir: Path) -> list[float]:
    """Every outflow_fraction with a saved --save-masks .npz in sweep_dir,
    sorted ascending - not hardcoded, so this picks up the full sweep (the
    densified 0.05-0.2 range this task targets, plus the earlier coarser
    0.3-0.8 points already on disk) for free, no new runs needed."""
    values = []
    for path in sweep_dir.glob("of_*.npz"):
        try:
            values.append(float(path.stem.removeprefix("of_")))
        except ValueError:
            continue
    return sorted(values)

_EXCLUDED_COLOR = "#c9c9c9"
_TN_COLOR = "#f0efec"
_TP_COLOR = "#2a78d6"
_FP_COLOR = "#1baf7a"
_FN_COLOR = "#eb6834"


def _fetch_stage_mask(layer_id: int, transform, shape, crs) -> np.ndarray:
    response = requests.get(
        f"{settings.SGB_LAJEADO_MAPSERVER_URL}/{layer_id}/query",
        params={"where": "1=1", "outFields": "*", "f": "geojson"},
        timeout=60,
    )
    response.raise_for_status()
    features = response.json()["features"]
    if len(features) != 1:
        raise ValueError(f"expected exactly 1 feature from layer {layer_id}, got {len(features)}")
    reprojected = reproject_geometry(features[0]["geometry"], settings.FLOOD_EXTENT_SOURCE_CRS, crs)
    return rasterize_flood_extent(reprojected, transform, shape)


def _dem_channel_col(Z: np.ndarray) -> np.ndarray:
    """Per-row DEM-implied channel column: argmin(Z[row]) - the exact same
    thalweg proxy check_riverbank_coverage.py uses, reused verbatim (not
    redefined) so the bank-scoped correction below is grounded in the same
    definition, not a fresh guess."""
    return np.array([int(np.argmin(Z[r])) for r in range(Z.shape[0])])


def _classify_is_estrela(Z: np.ndarray) -> np.ndarray:
    """True where a cell sits on Estrela's side of the DEM-implied channel,
    calibrated against the real ANA "ESTRELA" gauge cell
    (settings.VALIDATION_GAUGE_ROW/COL) exactly as check_riverbank_coverage.py
    does (after that script's own labeling fix): the gauge cell itself sits
    on Lajeado's bank, so Estrela is the side OPPOSITE the gauge cell, not the
    gauge's own side. An earlier version of this function (and this side's
    label throughout this script's output/docs writeup) had this inverted -
    corrected here, which changes which frozen-dry cells the bank-scoped
    mask below actually excludes, not just a cosmetic rename."""
    channel_col = _dem_channel_col(Z)
    col_idx = np.arange(Z.shape[1])[None, :]
    is_west = col_idx < channel_col[:, None]
    gauge_is_west = bool(is_west[settings.VALIDATION_GAUGE_ROW, settings.VALIDATION_GAUGE_COL])
    return ~is_west if gauge_is_west else is_west


def build_validity_masks(Z: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, np.ndarray]]:
    """Fetches the three stage masks and returns (valid_global, valid_bank_scoped,
    valid_estrela_gap_only, stage_masks).

    A cell is "frozen" if its flooded/dry status is IDENTICAL across all
    three queried stages (no stage-discriminating information either way):
    frozen-FLOODED means the permanent channel; frozen-DRY means the
    reference never once registered that cell as flooded, from
    near-baseflow (19.00m) all the way to this project's own peak (33.67m).

    `valid_global` excludes every frozen cell domain-wide, exactly as the
    task's literal per-cell test specifies. `valid_bank_scoped` excludes the
    154 frozen-flooded channel cells everywhere PLUS the frozen-dry cells on
    the Estrela side (where check_riverbank_coverage.py's own finding
    actually lives). `valid_estrela_gap_only` isolates just the second half
    of that (the confirmed Estrela coverage-gap dry cells), leaving the 154
    frozen-flooded channel cells scored normally - this separates the two
    corrections' individual contributions, since they are NOT the same kind
    of correction: the 154-cell exclusion is a domain-wide "remove trivial
    channel credit" choice (not bank-specific - verified below to sit mostly
    on Lajeado's side, not Estrela's), while the bank-scoped dry exclusion is
    the actual, independently-verified coverage-gap correction.
    """
    with rasterio.open(settings.DEM_VALIDATION_PROCESSED_PATH) as ref:
        transform, shape, crs = ref.transform, ref.shape, ref.crs

    stage_masks = {}
    for layer_id, name, stage_m in _STAGE_LAYERS:
        mask = _fetch_stage_mask(layer_id, transform, shape, crs)
        stage_masks[name] = mask
        print(f"  {name} ({stage_m:.2f}m): {int(mask.sum())} flooded cells")

    names = [name for _, name, _ in _STAGE_LAYERS]
    m0, m1, m2 = (stage_masks[n] for n in names)
    frozen = np.logical_and(m0 == m1, m1 == m2)
    valid_global = ~frozen

    frozen_flooded = np.logical_and(frozen, m2)
    frozen_dry = np.logical_and(frozen, ~m2)
    print(
        f"\nvalidity mask (global, literal per-cell test): {int(valid_global.sum())} valid cells "
        f"({100 * valid_global.mean():.1f}%), {int(frozen.sum())} frozen/excluded "
        f"({100 * frozen.mean():.1f}%) - of which {int(frozen_flooded.sum())} frozen-FLOODED "
        f"(permanent channel) and {int(frozen_dry.sum())} frozen-DRY (never registered as "
        "flooded at any tested stage)"
    )

    # Degeneracy check: SGB's own stage layers turn out to be perfectly
    # nested (every lower-stage flooded cell is also flooded at every higher
    # stage tested, zero violations) - verified directly, not assumed. Under
    # that monotonicity, "dry at the peak stage" and "frozen-dry across all
    # three" are the SAME set (a cell dry at the max stage tested must also
    # be dry at every lower one), so valid_global can never contain a cell
    # that's both valid and observed-dry - FP is mathematically zero at
    # every operating point, regardless of how the simulation actually
    # performs. This makes CSI restricted to valid_global degenerate into
    # Hit Rate (see the printed check below) - not a real correction for
    # over-prediction, an artifact of applying the exclusion domain-wide
    # rather than scoped to where the coverage-gap finding actually lives.
    nesting_violations = int(np.logical_and(m0, ~m1).sum()) + int(np.logical_and(m1, ~m2).sum())
    valid_and_dry_at_peak = int(np.logical_and(valid_global, ~m2).sum())
    print(
        f"nesting check: {nesting_violations} stage-monotonicity violations across the three layers "
        f"(0 = perfectly nested); valid-AND-dry-at-peak cells: {valid_and_dry_at_peak} "
        f"{'-> FP is mathematically forced to 0 under valid_global; CSI(valid_global) degenerates to Hit Rate' if valid_and_dry_at_peak == 0 else ''}"
    )

    is_estrela = _classify_is_estrela(Z)

    # Direct recomputation of each excluded set's bank split - not inferred
    # from variable names, computed fresh from the same corrected is_estrela
    # used everywhere else in this function, per the standard this project
    # holds itself to after the earlier Estrela/Lajeado labeling bug.
    frozen_dry_estrela = int(np.logical_and(frozen_dry, is_estrela).sum())
    frozen_dry_lajeado = int(np.logical_and(frozen_dry, ~is_estrela).sum())
    frozen_flooded_estrela = int(np.logical_and(frozen_flooded, is_estrela).sum())
    frozen_flooded_lajeado = int(np.logical_and(frozen_flooded, ~is_estrela).sum())
    print(
        f"\nbank split of frozen-DRY cells (recomputed directly, n={int(frozen_dry.sum())}): "
        f"Estrela={frozen_dry_estrela} ({100*frozen_dry_estrela/frozen_dry.sum():.1f}%), "
        f"Lajeado={frozen_dry_lajeado} ({100*frozen_dry_lajeado/frozen_dry.sum():.1f}%)"
    )
    print(
        f"bank split of frozen-FLOODED cells (recomputed directly, n={int(frozen_flooded.sum())}): "
        f"Estrela={frozen_flooded_estrela} ({100*frozen_flooded_estrela/frozen_flooded.sum():.1f}%), "
        f"Lajeado={frozen_flooded_lajeado} ({100*frozen_flooded_lajeado/frozen_flooded.sum():.1f}%) "
        "-> NOT bank-specific: this exclusion is a separate 'remove trivial channel credit' choice, "
        "not the coverage-gap correction (see below)"
    )

    excluded_bank_scoped = np.logical_or(frozen_flooded, np.logical_and(frozen_dry, is_estrela))
    valid_bank_scoped = ~excluded_bank_scoped
    valid_estrela_gap_only = ~np.logical_and(frozen_dry, is_estrela)
    print(
        f"\nvalidity mask (bank-scoped, BUNDLES both corrections): {int(valid_bank_scoped.sum())} valid cells "
        f"({100 * valid_bank_scoped.mean():.1f}%) - excludes the {int(frozen_flooded.sum())} "
        f"frozen-flooded channel cells everywhere (mostly Lajeado-side, see above), plus the "
        f"{frozen_dry_estrela} frozen-dry cells on the Estrela side"
    )
    print(
        f"validity mask (Estrela-gap-only, the confirmed coverage-gap correction ALONE): "
        f"{int(valid_estrela_gap_only.sum())} valid cells ({100 * valid_estrela_gap_only.mean():.1f}%) - "
        f"excludes ONLY the {frozen_dry_estrela} Estrela-side frozen-dry cells, leaves the 154 "
        "frozen-flooded channel cells scored normally"
    )

    return valid_global, valid_bank_scoped, valid_estrela_gap_only, stage_masks


def _load_npz_for(sweep_dir: Path, outflow_fraction: float) -> dict:
    path = sweep_dir / f"of_{outflow_fraction}.npz"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found - run validate_may2024.py --outflow-fraction {outflow_fraction} --save-masks first")
    return dict(np.load(path))


def _score(simulated: np.ndarray, observed: np.ndarray) -> dict:
    tp, fp, fn = confusion_counts(simulated, observed)
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "csi": csi(simulated, observed),
        "hit_rate": hit_rate(simulated, observed),
        "false_alarm_rate": false_alarm_rate(simulated, observed),
    }


def rescore_sweep(
    sweep_dir: Path, valid_global: np.ndarray, valid_bank_scoped: np.ndarray, valid_estrela_gap_only: np.ndarray
) -> list[dict]:
    rows = []
    for outflow_fraction in _discover_sweep_values(sweep_dir):
        data = _load_npz_for(sweep_dir, outflow_fraction)
        simulated_mask = data["simulated_mask"]
        observed_mask = data["observed_mask"]

        naive = _score(simulated_mask, observed_mask)
        corrected_global = _score(simulated_mask[valid_global], observed_mask[valid_global])
        corrected_bank_scoped = _score(simulated_mask[valid_bank_scoped], observed_mask[valid_bank_scoped])
        corrected_estrela_gap_only = _score(simulated_mask[valid_estrela_gap_only], observed_mask[valid_estrela_gap_only])
        rows.append(
            {
                "outflow_fraction": outflow_fraction,
                "naive": naive,
                "corrected_global": corrected_global,
                "corrected_bank_scoped": corrected_bank_scoped,
                "corrected_estrela_gap_only": corrected_estrela_gap_only,
            }
        )
    return rows


def _print_table(rows: list[dict]) -> None:
    print(
        f"{'of':>6} | {'naive':>6} | {'global*':>7} | {'gap-only**':>10} | {'bundled***':>10}"
    )
    print("(* global = degenerate, see nesting check above, for completeness only)")
    print("(** gap-only = ONLY the confirmed Estrela-side frozen-dry exclusion - the clean coverage-gap correction)")
    print("(*** bundled = gap-only PLUS the separate, non-bank-specific 154 frozen-flooded channel exclusion)")
    print("-" * 64)
    for row in rows:
        n, g, e, b = row["naive"], row["corrected_global"], row["corrected_estrela_gap_only"], row["corrected_bank_scoped"]
        print(
            f"{row['outflow_fraction']:>6} | "
            f"{n['csi']:>6.3f} | {g['csi']:>7.3f} | {e['csi']:>10.3f} | {b['csi']:>10.3f}"
        )


def _plot_overlay(
    Z: np.ndarray,
    observed_mask: np.ndarray,
    simulated_mask: np.ndarray,
    valid_mask: np.ndarray,
    out_png: Path,
    title: str,
) -> None:
    classification = np.full(Z.shape, 0, dtype=int)  # 0=TN
    classification[np.logical_and(simulated_mask, observed_mask)] = 1  # TP
    classification[np.logical_and(simulated_mask, ~observed_mask)] = 2  # FP
    classification[np.logical_and(~simulated_mask, observed_mask)] = 3  # FN
    classification_masked = np.where(valid_mask, classification, 4)  # 4=excluded

    fig, axes = plt.subplots(1, 4, figsize=(20, 5))
    for ax in axes:
        ax.set_xticks([])
        ax.set_yticks([])

    im0 = axes[0].imshow(Z, cmap="terrain")
    axes[0].set_title("Terrain (Z)")
    fig.colorbar(im0, ax=axes[0], label="elevation (m)", fraction=0.046)

    # Categorical (not continuous "Blues") so excluded cells read as a
    # distinct neutral gray, never confusable with a flooded-blue shade -
    # a continuous 0/0.5/1 Blues mapping made the excluded region look like
    # part of the flood extent in an earlier draft of this plot.
    wet_dry_cmap = ListedColormap([_TN_COLOR, "#08306b", _EXCLUDED_COLOR])
    axes[1].imshow(np.select([~valid_mask, observed_mask], [2, 1], default=0), cmap=wet_dry_cmap, vmin=0, vmax=2)
    axes[1].set_title("Observed (SGB, valid cells only)")

    axes[2].imshow(np.select([~valid_mask, simulated_mask], [2, 1], default=0), cmap=wet_dry_cmap, vmin=0, vmax=2)
    axes[2].set_title("Simulated (valid cells only)")

    cmap = ListedColormap([_TN_COLOR, _TP_COLOR, _FP_COLOR, _FN_COLOR, _EXCLUDED_COLOR])
    axes[3].imshow(classification_masked, cmap=cmap, vmin=0, vmax=4)
    axes[3].set_title("Confusion (stage-invariant cells excluded)")
    tp, fp, fn = confusion_counts(simulated_mask[valid_mask], observed_mask[valid_mask])
    tn = int(valid_mask.sum()) - tp - fp - fn
    legend_elements = [
        Patch(facecolor=_TP_COLOR, label=f"TP ({tp})"),
        Patch(facecolor=_FN_COLOR, label=f"FN ({fn})"),
        Patch(facecolor=_FP_COLOR, label=f"FP ({fp})"),
        Patch(facecolor=_TN_COLOR, edgecolor="#999999", label=f"TN ({tn})"),
        Patch(facecolor=_EXCLUDED_COLOR, label=f"excluded ({int((~valid_mask).sum())})"),
    ]
    axes[3].legend(handles=legend_elements, loc="upper center", bbox_to_anchor=(0.5, -0.05), ncol=3, fontsize=8)

    fig.suptitle(title)
    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"saved corrected overlay to {out_png}")


def _noise_floor_masked(
    simulated_mask: np.ndarray, observed_mask: np.ndarray, valid_mask: np.ndarray, max_shift: int = 3
) -> dict:
    """Same shift-search idea as shift_search_noise_floor.py, but the
    simulated mask is shifted while the valid mask stays fixed (unshifted) -
    stage-invariance is a property of the reference geography, not of a
    candidate registration offset, so it shouldn't move with the shift being
    tested."""
    best = {"dy": 0, "dx": 0, "csi": float("-inf")}
    baseline = None
    for dy in range(-max_shift, max_shift + 1):
        for dx in range(-max_shift, max_shift + 1):
            shifted = _shift_mask(simulated_mask, dy, dx)
            try:
                score = csi(shifted[valid_mask], observed_mask[valid_mask])
            except ValueError:
                continue
            if dy == 0 and dx == 0:
                baseline = score
            if score > best["csi"]:
                best = {"dy": dy, "dx": dx, "csi": score}
    return {"baseline_csi": baseline, "best_dy": best["dy"], "best_dx": best["dx"], "best_csi": best["csi"]}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sweep-dir", type=Path, default=Path("../data/sweep_outputs"))
    parser.add_argument("--out-png", type=Path, default=Path("../data/sweep_outputs/stage_invariant_corrected_overlay.png"))
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    print("=== 1. Building the stage-invariance validity masks ===")
    # Z from an already-saved npz (any one - Z is identical across the sweep,
    # same 90m validation grid throughout) rather than re-deriving it, since
    # the bank classification needs the exact grid the sweep itself used.
    any_npz = _load_npz_for(args.sweep_dir, _discover_sweep_values(args.sweep_dir)[0])
    valid_global, valid_bank_scoped, valid_estrela_gap_only, stage_masks = build_validity_masks(any_npz["Z"])

    with rasterio.open(settings.FLOOD_EXTENT_VALIDATION_PROCESSED_PATH) as ref:
        on_disk_observed = ref.read(1).astype(bool)
    if np.array_equal(on_disk_observed, stage_masks["COTA_3367cm"]):
        print("sanity check: freshly-fetched COTA_3367cm mask matches the on-disk processed reference exactly.")
    else:
        print("WARNING: freshly-fetched COTA_3367cm mask differs from the on-disk processed reference.")

    print("\n=== 2. Rescoring the outflow_fraction sweep (naive vs. three correction variants) ===")
    rows = rescore_sweep(args.sweep_dir, valid_global, valid_bank_scoped, valid_estrela_gap_only)
    _print_table(rows)

    # Ranked by the gap-only correction, not the bundled one - it's the clean,
    # well-justified coverage-gap correction; bundling in the separate,
    # non-bank-specific 154-cell exclusion is a different choice that can (and
    # does, at this operating point) make the score look worse, not better.
    best_row = max(rows, key=lambda r: r["corrected_estrela_gap_only"]["csi"])
    best_of = best_row["outflow_fraction"]
    naive_best = best_row["naive"]
    gap_only_best = best_row["corrected_estrela_gap_only"]
    bundled_best = best_row["corrected_bank_scoped"]
    print(
        f"\n=== 3. Best value under the Estrela-gap-only correction: outflow_fraction={best_of} ===\n"
        f"naive CSI {naive_best['csi']:.4f} (TP={naive_best['tp']} FP={naive_best['fp']} FN={naive_best['fn']})\n"
        f"Estrela-gap-only-corrected CSI {gap_only_best['csi']:.4f} "
        f"(TP={gap_only_best['tp']} FP={gap_only_best['fp']} FN={gap_only_best['fn']}, "
        f"delta vs naive {gap_only_best['csi'] - naive_best['csi']:+.4f}) <- the clean, citable coverage-gap correction\n"
        f"bundled (gap-only + 154-channel exclusion) CSI {bundled_best['csi']:.4f} "
        f"(TP={bundled_best['tp']} FP={bundled_best['fp']} FN={bundled_best['fn']}, "
        f"delta vs gap-only {bundled_best['csi'] - gap_only_best['csi']:+.4f}) <- WORSE than gap-only alone, "
        "since the 154-cell exclusion removes real TP credit without touching the coverage-gap FP problem"
    )
    naive_ranking = sorted(rows, key=lambda r: r["naive"]["csi"], reverse=True)[:3]
    gap_ranking = sorted(rows, key=lambda r: r["corrected_estrela_gap_only"]["csi"], reverse=True)[:3]
    print(
        f"naive-CSI top 3: {[(r['outflow_fraction'], round(r['naive']['csi'], 4)) for r in naive_ranking]}"
    )
    print(
        f"Estrela-gap-only-corrected top 3: {[(r['outflow_fraction'], round(r['corrected_estrela_gap_only']['csi'], 4)) for r in gap_ranking]}"
    )

    print("\n=== 4. Visual overlay + noise-floor check for the Estrela-gap-only best value ===")
    data = _load_npz_for(args.sweep_dir, best_of)
    _plot_overlay(
        data["Z"],
        data["observed_mask"],
        data["simulated_mask"],
        valid_estrela_gap_only,
        args.out_png,
        title=f"outflow_fraction={best_of} - Estrela coverage-gap cells excluded (corrected CSI={gap_only_best['csi']:.4f})",
    )
    noise = _noise_floor_masked(data["simulated_mask"], data["observed_mask"], valid_estrela_gap_only)
    print(
        f"masked noise-floor (Estrela-gap-only): baseline (0,0) CSI {noise['baseline_csi']:.4f}, "
        f"best shifted CSI {noise['best_csi']:.4f} at (dy={noise['best_dy']}, dx={noise['best_dx']}) "
        f"(delta={noise['best_csi'] - noise['baseline_csi']:+.4f})"
    )

    default_row = next((r for r in rows if r["outflow_fraction"] == 0.5), None)
    if default_row is not None:
        n, g, e, b = (
            default_row["naive"], default_row["corrected_global"],
            default_row["corrected_estrela_gap_only"], default_row["corrected_bank_scoped"],
        )
        print(
            f"\n=== 5. Magnitude of the correction at the documented default outflow_fraction=0.5 (step 10) ===\n"
            f"naive CSI {n['csi']:.4f} vs. global-corrected CSI {g['csi']:.4f} (degenerate, see above) "
            f"vs. Estrela-gap-only CSI {e['csi']:.4f} vs. bundled CSI {b['csi']:.4f} "
            f"(delta gap-only vs naive: {e['csi'] - n['csi']:+.4f})"
        )


if __name__ == "__main__":
    main()
