"""Terrain + simulated depth + confusion-map visualization for a
validate_may2024.py run (roadmap step 10/11 exploratory tooling).

Loads a validate_may2024.py --save-masks .npz (simulated_mask, observed_mask,
Z, and H if present) and renders a 2-3 panel figure: real terrain, simulated
depth (if H was saved), and a categorical TP/FP/FN/TN confusion classification
- the mandatory visual companion to a bare CSI number, since a single scalar
can't show *where* a simulation over- or under-predicts.

No such visualization existed anywhere in the repo before this script
(confirmed by search) - built from scratch, following poc_real_dem.py's
`imshow(Z, cmap="terrain")` terrain-panel precedent and
validation.metrics.confusion_counts's per-cell TP/FP/FN logic.

Run from the backend/ directory with the venv active:
    python -m examples.plot_confusion_map --npz PATH --out PATH.png
"""

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch

from validation.metrics import confusion_counts, csi, false_alarm_rate, hit_rate

# TN as a neutral background, three colorblind-safe categorical hues for the
# classes that actually matter diagnostically. FN (miss / under-prediction)
# gets the most visually prominent hue since this project's own under-
# prediction investigation is specifically about that failure mode.
_TN_COLOR = "#f0efec"
_TP_COLOR = "#2a78d6"
_FP_COLOR = "#1baf7a"
_FN_COLOR = "#eb6834"

_CODE_TN, _CODE_TP, _CODE_FP, _CODE_FN = 0, 1, 2, 3


def _classify(simulated_mask: np.ndarray, observed_mask: np.ndarray) -> np.ndarray:
    """Per-cell TN=0/TP=1/FP=2/FN=3 classification."""
    classification = np.full(simulated_mask.shape, _CODE_TN, dtype=int)
    classification[np.logical_and(simulated_mask, observed_mask)] = _CODE_TP
    classification[np.logical_and(simulated_mask, ~observed_mask)] = _CODE_FP
    classification[np.logical_and(~simulated_mask, observed_mask)] = _CODE_FN
    return classification


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--npz", type=Path, required=True, help="Path to a validate_may2024.py --save-masks .npz file.")
    parser.add_argument("--out", type=Path, required=True, help="Output PNG path.")
    parser.add_argument("--title", type=str, default=None, help="Optional figure suptitle (e.g. the swept parameter's value).")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    data = np.load(args.npz)
    simulated_mask = data["simulated_mask"]
    observed_mask = data["observed_mask"]
    Z = data["Z"] if "Z" in data else None
    H = data["H"] if "H" in data else None

    tp, fp, fn = confusion_counts(simulated_mask, observed_mask)
    tn = simulated_mask.size - tp - fp - fn
    csi_value = csi(simulated_mask, observed_mask)
    hit_rate_value = hit_rate(simulated_mask, observed_mask)
    false_alarm_rate_value = false_alarm_rate(simulated_mask, observed_mask)

    print(f"TP={tp} FP={fp} FN={fn} TN={tn}")
    print(f"CSI={csi_value:.4f} HitRate={hit_rate_value:.4f} FalseAlarmRate={false_alarm_rate_value:.4f}")

    panels = []
    if Z is not None:
        panels.append(("terrain", Z))
    if H is not None:
        panels.append(("depth", H))
    panels.append(("confusion", None))

    fig, axes = plt.subplots(1, len(panels), figsize=(5 * len(panels), 5))
    if len(panels) == 1:
        axes = [axes]

    for ax, (kind, array) in zip(axes, panels):
        ax.set_xticks([])
        ax.set_yticks([])
        if kind == "terrain":
            im = ax.imshow(array, cmap="terrain")
            ax.set_title("Terrain (Z)")
            fig.colorbar(im, ax=ax, label="elevation (m)", fraction=0.046)
        elif kind == "depth":
            im = ax.imshow(array, cmap="Blues")
            ax.set_title("Simulated depth (H)")
            fig.colorbar(im, ax=ax, label="depth (m)", fraction=0.046)
        else:
            classification = _classify(simulated_mask, observed_mask)
            cmap = ListedColormap([_TN_COLOR, _TP_COLOR, _FP_COLOR, _FN_COLOR])
            ax.imshow(classification, cmap=cmap, vmin=0, vmax=3)
            ax.set_title(f"Confusion (CSI={csi_value:.3f})")
            legend_elements = [
                Patch(facecolor=_TP_COLOR, label=f"TP hit ({tp})"),
                Patch(facecolor=_FN_COLOR, label=f"FN miss / under-prediction ({fn})"),
                Patch(facecolor=_FP_COLOR, label=f"FP false alarm ({fp})"),
                Patch(facecolor=_TN_COLOR, edgecolor="#999999", label=f"TN ({tn})"),
            ]
            ax.legend(handles=legend_elements, loc="upper center", bbox_to_anchor=(0.5, -0.05), ncol=2, fontsize=8)

    if args.title:
        fig.suptitle(args.title)
    fig.tight_layout()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"saved plot to {args.out}")


if __name__ == "__main__":
    main()
