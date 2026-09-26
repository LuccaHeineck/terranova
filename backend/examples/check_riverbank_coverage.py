"""Check whether the SGB/CPRM flood-extent reference data covers Estrela's
riverbank as well as Lajeado's (roadmap step 10 follow-up).

The SGB flood-extent data used for CSI validation is served from a MapServer
whose base URL is literally named `LAJEADO` (settings.SGB_LAJEADO_MAPSERVER_URL).
A prior exploratory script (characterize_fp_region.py) found a large false-
positive (FP) region at outflow_fraction=0.085. This script tests a real
possibility that would reframe that finding: if the reference dataset only
ever mapped Lajeado's side of the Taquari, part of the FP region isn't the CA
model over-predicting - it's the ground truth having zero coverage there.

Lajeado and Estrela are twin cities split by the Taquari river itself in this
reach, so the river is used here as the de facto municipal boundary - no
official IBGE polygon needed (that API was confirmed flaky/unavailable during
this investigation). The channel/thalweg proxy reused below (DEM-implied
channel column = argmin(Z[row]) per row) is the same definition an earlier,
uncommitted diagnostic already used for a related registration-offset question
into this same May 2024 CSI validation - reused verbatim, not redefined, for
consistency with that prior (undocumented) work. Which side of that channel is
"Estrela" is calibrated with data already in this repo: settings.
VALIDATION_GAUGE_ROW/COL is the grid cell for real ANA gauge station 86879300,
named "ESTRELA" - but that gauge cell itself sits on Lajeado's bank (confirmed
after review), so Estrela is the side OPPOSITE the gauge cell, not the gauge's
own side. No external API or guess involved either way.

Three checks:
1. Query the SGB MapServer's own root/layer listing - is there any layer
   suggesting a separate Estrela dataset, or is everything nested under one
   `LAJEADO` group?
2. What fraction of the SGB reference polygon's flooded cells fall on each
   bank?
3. What fraction of the outflow_fraction=0.085 FP region falls on each bank,
   compared against the same run's True Positive cells as a baseline?

Report only - no fix, no live default touched.

Run from the backend/ directory with the venv active:
    python -m examples.check_riverbank_coverage --npz PATH [--out-png PATH]
"""

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import rasterio
import requests

from config import settings


def _check_mapserver_layers() -> dict:
    response = requests.get(settings.SGB_LAJEADO_MAPSERVER_URL, params={"f": "json"}, timeout=30)
    response.raise_for_status()
    layers = response.json().get("layers", [])

    for layer in layers:
        parent = layer.get("parentLayerId")
        print(f"  id={layer['id']:>2}  parent={('-' if parent is None else parent):>4}  name={layer['name']}")

    estrela_layers = [layer for layer in layers if "estrela" in layer["name"].lower()]
    target_layer = next((layer for layer in layers if layer["id"] == settings.FLOOD_EXTENT_LAYER_ID), None)
    print(f"\nlayers with 'Estrela' in the name: {len(estrela_layers)} of {len(layers)}")
    print(
        f"this project's source layer (id={settings.FLOOD_EXTENT_LAYER_ID}): "
        f"{target_layer['name'] if target_layer else 'NOT FOUND'}"
    )
    return {"has_estrela_layer": bool(estrela_layers), "num_layers": len(layers)}


def _dem_channel_col(Z: np.ndarray) -> np.ndarray:
    """Per-row DEM-implied channel column: argmin(Z[row]).

    Same definition as an earlier, uncommitted diagnostic
    (dem_vs_reference_channel_offset.py, from a prior session's registration-
    offset investigation into this same May 2024 CSI validation) - reused
    verbatim rather than redefined, so this bank classification is grounded in
    the same channel proxy already used for that related question. Valid here
    because the Taquari runs roughly north-to-south through this ROI (enters
    settings.HYDROGRAPH_INFLOW_EDGE="north", exits HYDROGRAPH_OUTLET_EDGE=
    "south"), so "lowest column in each row" is a reasonable per-row thalweg.
    """
    return np.array([int(np.argmin(Z[r])) for r in range(Z.shape[0])])


def _classify_banks(Z: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Returns (channel_col, is_west) - is_west[r, c] is True if column c sits
    west (lower column index) of the channel at row r."""
    channel_col = _dem_channel_col(Z)
    col_idx = np.arange(Z.shape[1])[None, :]
    is_west = col_idx < channel_col[:, None]
    return channel_col, is_west


def _bank_split(mask: np.ndarray, is_estrela: np.ndarray) -> dict:
    total = int(mask.sum())
    estrela = int(np.logical_and(mask, is_estrela).sum())
    lajeado = total - estrela
    return {
        "total": total,
        "estrela": estrela,
        "lajeado": lajeado,
        "estrela_pct": 100 * estrela / total if total else float("nan"),
        "lajeado_pct": 100 * lajeado / total if total else float("nan"),
    }


def _print_split(label: str, split: dict) -> None:
    print(f"{label}: {split['total']} cells total")
    print(f"  Estrela side: {split['estrela']} ({split['estrela_pct']:.1f}%)")
    print(f"  Lajeado side: {split['lajeado']} ({split['lajeado_pct']:.1f}%)")


def _plot_diagnostic(
    Z: np.ndarray,
    channel_col: np.ndarray,
    gauge_row: int,
    gauge_col: int,
    observed_mask: np.ndarray,
    fp_mask: np.ndarray,
    is_estrela: np.ndarray,
    out_png: Path,
) -> None:
    rows = np.arange(Z.shape[0])
    fig, ax = plt.subplots(figsize=(7, 9))
    ax.imshow(Z, cmap="terrain", alpha=0.6)
    ax.plot(channel_col, rows, "k-", linewidth=1.5, label="DEM-implied channel (argmin per row)")

    obs_r, obs_c = np.where(observed_mask)
    obs_estrela = is_estrela[obs_r, obs_c]
    ax.scatter(obs_c[obs_estrela], obs_r[obs_estrela], s=4, c="tab:blue", marker=".", alpha=0.6, label="SGB observed (Estrela side)")
    ax.scatter(obs_c[~obs_estrela], obs_r[~obs_estrela], s=4, c="tab:orange", marker=".", alpha=0.6, label="SGB observed (Lajeado side)")

    fp_r, fp_c = np.where(fp_mask)
    ax.scatter(fp_c, fp_r, s=14, facecolors="none", edgecolors="red", marker="o", label="FP cells (outflow_fraction=0.085)")

    ax.scatter([gauge_col], [gauge_row], s=100, c="lime", marker="*", edgecolors="black", linewidths=0.5, label="gauge cell (ANA 86879300, ESTRELA)")

    ax.set_xlabel("column index")
    ax.set_ylabel("row index (0 = north)")
    ax.set_title("River-channel bank split vs. SGB coverage and FP region")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.08), ncol=2, fontsize=8)
    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=150, bbox_inches="tight")
    plt.close(fig)


def _print_verdict(layer_findings: dict, sgb_split: dict, fp_split: dict, tp_split: dict) -> None:
    print(
        f"1. SGB MapServer layer tree: {'a' if layer_findings['has_estrela_layer'] else 'NO'} "
        f"layer suggesting a separate Estrela dataset, among {layer_findings['num_layers']} layers "
        "all nested under one LAJEADO MapServer."
    )

    print(
        f"2. SGB reference polygon coverage: {sgb_split['estrela_pct']:.1f}% of its flooded cells "
        f"fall on the Estrela side, {sgb_split['lajeado_pct']:.1f}% on the Lajeado side "
        f"({sgb_split['total']} total cells)."
    )
    # Symmetric: identify whichever side SGB under-represents, don't assume it's Estrela -
    # the hypothesis this script tests could turn out inverted from how it was originally framed.
    minority_side, minority_pct = min(
        [("Estrela", sgb_split["estrela_pct"]), ("Lajeado", sgb_split["lajeado_pct"])],
        key=lambda pair: pair[1],
    )
    if minority_pct < 5.0:
        coverage_verdict = f"effectively ZERO coverage of the {minority_side} side"
    elif minority_pct < 40.0:
        coverage_verdict = f"PARTIAL coverage, skewed heavily away from the {minority_side} side"
    else:
        coverage_verdict = "roughly balanced coverage of both sides"
    print(f"   -> {coverage_verdict}.")

    print(
        f"3. FP region (outflow_fraction=0.085): {fp_split['estrela_pct']:.1f}% Estrela / "
        f"{fp_split['lajeado_pct']:.1f}% Lajeado ({fp_split['total']} cells)."
    )
    print(
        f"   Same-run TP baseline: {tp_split['estrela_pct']:.1f}% Estrela / "
        f"{tp_split['lajeado_pct']:.1f}% Lajeado ({tp_split['total']} cells)."
    )
    minority_key = minority_side.lower()
    skew = fp_split[f"{minority_key}_pct"] - tp_split[f"{minority_key}_pct"]
    print(f"   FP cells are {skew:+.1f} percentage points more concentrated on the under-covered ({minority_side}) side than the TP baseline.")

    explains_fp = minority_pct < 5.0 and skew > 20.0
    print("\n4. VERDICT:")
    if explains_fp:
        print(
            f"   The SGB reference data has effectively zero coverage of the {minority_side} side, and the FP\n"
            "   region is disproportionately concentrated there relative to the TP baseline. This is a\n"
            "   real, likely-significant contributor to the FP finding: a reference-data coverage gap,\n"
            "   not (solely) CA-model over-prediction. CSI/FAR as currently computed may be unfairly\n"
            f"   penalizing correctly simulated flooding on the {minority_side} side."
        )
    else:
        print(
            "   The numbers do NOT cleanly support the coverage-gap hypothesis as the explanation -\n"
            f"   either SGB coverage of {minority_side} isn't near-zero, or the FP region isn't\n"
            f"   disproportionately concentrated on the {minority_side} side relative to the TP baseline.\n"
            "   Consider the IBGE municipal-boundary check as an independent, non-river-based cross-check\n"
            "   before ruling this out entirely."
        )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--npz",
        type=Path,
        default=Path("../data/sweep_outputs/of_0.085.npz"),
        help="Path to a validate_may2024.py --save-masks .npz file.",
    )
    parser.add_argument("--out-png", type=Path, default=None, help="Optional diagnostic plot output path.")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    print("=== 1. SGB MapServer layer listing ===")
    layer_findings = _check_mapserver_layers()

    print("\n=== 2. River-channel bank classification (90m validation grid) ===")
    data = np.load(args.npz)
    simulated_mask = data["simulated_mask"]
    observed_mask = data["observed_mask"]
    Z = data["Z"]

    with rasterio.open(settings.FLOOD_EXTENT_VALIDATION_PROCESSED_PATH) as ref:
        tif_observed_mask = ref.read(1).astype(bool)
    if not np.array_equal(tif_observed_mask, observed_mask):
        print(
            "WARNING: observed_mask in the .npz differs from the on-disk "
            f"{settings.FLOOD_EXTENT_VALIDATION_PROCESSED_PATH} - using the .npz copy."
        )
    else:
        print(f"observed_mask matches the on-disk {settings.FLOOD_EXTENT_VALIDATION_PROCESSED_PATH.name} exactly.")

    channel_col, is_west = _classify_banks(Z)
    gauge_row, gauge_col = settings.VALIDATION_GAUGE_ROW, settings.VALIDATION_GAUGE_COL
    gauge_is_west = bool(is_west[gauge_row, gauge_col])
    print(f"gauge cell (ANA station 86879300, 'ESTRELA'): row={gauge_row} col={gauge_col}")
    print(f"DEM-implied channel column at that row: {channel_col[gauge_row]}")
    print(f"gauge cell sits {'west' if gauge_is_west else 'east'} of the channel at its own row")
    # The gauge cell itself sits on Lajeado's bank, not Estrela's (corrected after review) -
    # Estrela is therefore the side OPPOSITE the gauge cell's own side.
    is_estrela = ~is_west if gauge_is_west else is_west
    print(
        f"-> calibrated: {'east' if gauge_is_west else 'west'}-of-channel = Estrela, "
        f"{'west' if gauge_is_west else 'east'}-of-channel = Lajeado (gauge cell's own side)"
    )

    print("\n=== 3. SGB reference polygon coverage per bank ===")
    sgb_split = _bank_split(observed_mask, is_estrela)
    _print_split("SGB observed flooded cells", sgb_split)

    print("\n=== 4. FP-region split per bank, vs TP baseline ===")
    fp_mask = np.logical_and(simulated_mask, ~observed_mask)
    tp_mask = np.logical_and(simulated_mask, observed_mask)
    fp_split = _bank_split(fp_mask, is_estrela)
    tp_split = _bank_split(tp_mask, is_estrela)
    _print_split("FP cells (outflow_fraction=0.085)", fp_split)
    _print_split("TP cells (same-run baseline)", tp_split)

    if args.out_png is not None:
        _plot_diagnostic(Z, channel_col, gauge_row, gauge_col, observed_mask, fp_mask, is_estrela, args.out_png)
        print(f"\nsaved diagnostic plot to {args.out_png}")

    print("\n=== 5. Verdict ===")
    _print_verdict(layer_findings, sgb_split, fp_split, tp_split)


if __name__ == "__main__":
    main()
