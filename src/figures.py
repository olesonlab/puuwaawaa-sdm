"""
Main-text Figures 3-5 and SI Figures S1-S2 for the Puʻuwaʻawaʻa SDM paper
(Conservation Science and Practice, CSP2-26-0352, revision).

Reads the optimizer output (sdm_results_summary.csv, sdm_results_paddock_detail.csv)
and writes PDF (vector) and 600 dpi PNG files. Figure titles are left off because
the captions carry them. Scenario names and colors match the SI sensitivity figures.

    python src/figures.py --data-dir results --out-dir figures

Figure 1 (map and photographs) is assembled by figure1_composite.py and Figure 2
(objectives hierarchy) was drawn by hand, so neither is produced here.
"""
import argparse
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import numpy as np
import pandas as pd

_ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
_ap.add_argument("--data-dir", default="results", help="folder with the optimizer CSVs")
_ap.add_argument("--out-dir", default="figures", help="folder for the figure files")
_args = _ap.parse_args()
RESULTS, OUT = _args.data_dir, _args.out_dir
os.makedirs(OUT, exist_ok=True)

MM = 1 / 25.4
FULL_W = 170 * MM          # full page width

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial", "Liberation Sans", "DejaVu Sans"],
    "font.size": 8, "axes.labelsize": 8, "axes.titlesize": 8.5,
    "xtick.labelsize": 7.5, "ytick.labelsize": 7.5, "legend.fontsize": 7.5,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.edgecolor": "#52514e", "xtick.color": "#52514e", "ytick.color": "#52514e",
    "axes.linewidth": 0.7, "pdf.fonttype": 42, "savefig.bbox": "tight",
})

# One scenario identity for every figure in the paper (Okabe-Ito hues, with marker
# and line-style redundancy so identity never rests on color alone).
SCEN = {  # csv name: (label, color, marker, linestyle)
    "Balanced":              ("Balanced",              "#3a3a3a", "o", "-"),
    "Conservation priority": ("Conservation Priority", "#0072B2", "s", "-"),
    "T&E emphasis":          ("T&E Emphasis",          "#56B4E9", "D", (0, (4, 2))),
    "Habitat emphasis":      ("Habitat Emphasis",      "#009E73", "P", (0, (1, 1.5))),
    "Community priority":    ("Community Priority",    "#D55E00", "^", "--"),
    "Rancher-conservation":  ("Rancher-Conservation",  "#E69F00", "v", "-."),
    "Hunter-recreationist":  ("Hunter-Recreationist",  "#CC79A7", "X", ":"),
}
ORDER = list(SCEN)
BUDGETS = [5, 10, 20, 40, 60]

summ = pd.read_csv(f"{RESULTS}/sdm_results_summary.csv")
summ["budget_M"] = summ.budget / 1e6
det = pd.read_csv(f"{RESULTS}/sdm_results_paddock_detail.csv")
det["budget_M"] = det.budget / 1e6


def save(fig, name):
    fig.savefig(f"{OUT}/{name}.pdf")
    fig.savefig(f"{OUT}/{name}.png", dpi=600)
    plt.close(fig)
    print("wrote", name)


def panel(ax, letter):
    ax.text(-0.13, 1.03, letter, transform=ax.transAxes, fontsize=10, fontweight="bold")


# ---------------------------------------------------------------- Figure 3
def figure3():
    s20 = summ[summ.budget_M == 20].set_index("scenario")
    keys = ["te_score", "habitat_score", "rancher_score", "hunter_score", "recreationist_score"]
    names = ["T&E plants", "Native habitat", "Ranching", "Hunting", "Recreation"]
    delta = s20[keys] - s20.loc["Balanced", keys]
    show = ["Conservation priority", "Community priority", "Rancher-conservation"]
    fig, ax = plt.subplots(figsize=(FULL_W, 72 * MM))
    x = np.arange(len(keys)); w = 0.26
    for i, s in enumerate(show):
        lab, col = SCEN[s][0], SCEN[s][1]
        vals = delta.loc[s].values
        bars = ax.bar(x + (i - 1) * w, vals, w * 0.92, color=col, label=lab,
                      hatch="////" if s == "Rancher-conservation" else None,
                      edgecolor="white", linewidth=0.4)
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v + (0.18 if v >= 0 else -0.18),
                    f"{v:+.1f}".replace("-", "\u2212"), ha="center", va="bottom" if v >= 0 else "top",
                    fontsize=6.5, color="#262626")
    ax.axhline(0, color="#262626", linewidth=0.7)
    ax.set_xticks(x, names)
    ax.set_ylabel("Change from Balanced at $20 million\n(score points)")
    ax.set_ylim(-9.8, 6)
    ax.yaxis.grid(True, color="#e4e3df", linewidth=0.5); ax.set_axisbelow(True)
    ax.legend(frameon=False, loc="lower left", ncol=3, bbox_to_anchor=(0, 1.0))
    save(fig, "Figure_3_asymmetry")


# ---------------------------------------------------------------- Figure 4
def figure4():
    fig, axes = plt.subplots(1, 2, figsize=(FULL_W, 70 * MM))
    for ax, key, ylab, letter in [(axes[0], "te_score", "Total T&E plant score", "A"),
                                  (axes[1], "rancher_score", "Total rancher score", "B")]:
        for s in ORDER:
            lab, col, mk, ls = SCEN[s]
            d = summ[summ.scenario == s].sort_values("budget_M")
            ax.plot(d.budget_M, d[key], color=col, marker=mk, linestyle=ls, linewidth=1.4,
                    markersize=4.5, markeredgecolor="white", markeredgewidth=0.5, label=lab,
                    zorder=3 if s != "T&E emphasis" else 4)
        ax.set_xscale("log")
        ax.set_xticks(BUDGETS, [f"${b}M" for b in BUDGETS])
        ax.minorticks_off()
        ax.set_xlabel("Budget (log scale)")
        ax.set_ylabel(ylab)
        ax.yaxis.grid(True, color="#e4e3df", linewidth=0.5); ax.set_axisbelow(True)
        panel(ax, letter)
    h, l = axes[0].get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", ncol=4, frameon=False, bbox_to_anchor=(0.5, -0.12))
    fig.tight_layout(w_pad=3)
    save(fig, "Figure_4_budget_curves")


# ---------------------------------------------------------------- Figure 5
ALT_STYLE = {  # alternative: (legend label, color, text color)
    1: ("1  Fence + fuelbreaks", "#9ecae1", "#1a1a1a"),
    3: ("3  Fence + intensify grazing", "#D55E00", "white"),
    4: ("4  Fence + fuelbreak + remove cattle", "#4292c6", "white"),
    5: ("5  Alt 4 + remove ungulates", "#2171b5", "white"),
    6: ("6  Alt 5 + weed control around T&E", "#08519c", "white"),
    7: ("7  Full restoration", "#08306b", "white"),
    10: ("10  Fence + plant natives", "#d9d0e9", "#1a1a1a"),
    11: ("11  No change", "#e6e6e6", "#1a1a1a"),
}


def figure5():
    d20 = det[det.budget_M == 20]
    grid = np.array([d20[d20.scenario == s].sort_values("paddock").alternative.values for s in ORDER])
    fig, ax = plt.subplots(figsize=(FULL_W, 62 * MM))
    for r in range(grid.shape[0]):
        for c in range(grid.shape[1]):
            a = int(grid[r, c]); lab, col, tc = ALT_STYLE[a]
            ax.add_patch(plt.Rectangle((c, r), 1, 1, facecolor=col, edgecolor="white", linewidth=0.8))
            ax.text(c + 0.5, r + 0.5, str(a), ha="center", va="center", fontsize=6.5, color=tc,
                    fontweight="bold")
    ax.set_xlim(0, grid.shape[1]); ax.set_ylim(grid.shape[0], 0)
    ax.set_xticks(np.arange(grid.shape[1]) + 0.5, [str(i + 1) for i in range(grid.shape[1])])
    ax.set_yticks(np.arange(grid.shape[0]) + 0.5, [SCEN[s][0] for s in ORDER])
    ax.set_xlabel("Paddock (Paddock 9 pre-assigned to full restoration)")
    ax.tick_params(length=0)
    for sp in ax.spines.values():
        sp.set_visible(False)
    used = sorted(set(grid.ravel()))
    handles = [Patch(facecolor=ALT_STYLE[a][1], edgecolor="#bdbdbd", linewidth=0.4,
                     label=ALT_STYLE[a][0]) for a in used]
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=3,
              frameon=False, handlelength=1.2, columnspacing=1.5)
    save(fig, "Figure_5_portfolios_heatmap")


# ---------------------------------------------------------------- Figure S1
def figure_s1():
    s20 = summ[summ.budget_M == 20].set_index("scenario")
    fig, ax = plt.subplots(figsize=(120 * MM, 95 * MM))
    offsets = {"Balanced": (-8, 8), "Conservation priority": (8, -2), "T&E emphasis": (8, -2),
               "Habitat emphasis": (8, -10), "Community priority": (-10, 8),
               "Rancher-conservation": (8, -9), "Hunter-recreationist": (-10, -12)}
    for s in ORDER:
        lab, col, mk, _ = SCEN[s]
        x, y = s20.loc[s, "rancher_score"], s20.loc[s, "te_score"]
        ax.scatter(x, y, s=48, color=col, marker=mk, edgecolor="#262626", linewidth=0.5, zorder=3)
    labels = {  # direct labels; the two identical conservation portfolios share one
        "Balanced": "Balanced", "Conservation priority": "Conservation Priority\n= T&E Emphasis",
        "Habitat emphasis": "Habitat Emphasis", "Community priority": "Community Priority",
        "Rancher-conservation": "Rancher-Conservation", "Hunter-recreationist": "Hunter-Recreationist"}
    for s, t in labels.items():
        x, y = s20.loc[s, "rancher_score"], s20.loc[s, "te_score"]
        dx, dy = offsets[s]
        ax.annotate(t, (x, y), xytext=(dx, dy), textcoords="offset points", fontsize=7,
                    ha="left" if dx > 0 else "right", va="center", color="#262626")
    bx, by = s20.loc["Balanced", ["rancher_score", "te_score"]]
    ax.axvline(bx, color="#bdbdbd", linewidth=0.6, linestyle=":")
    ax.axhline(by, color="#bdbdbd", linewidth=0.6, linestyle=":")
    ax.set_xlabel("Total rancher score at $20 million")
    ax.set_ylabel("Total T&E plant score at $20 million")
    ax.set_xlim(2, 19); ax.set_ylim(1, 12.5)
    save(fig, "Figure_S1_tradeoff_scatter")


# ---------------------------------------------------------------- Figure S2
def figure_s2():
    cp = det[det.scenario == "Conservation priority"]
    cats = [("Full restoration (Alt 7)", [7], "#08306b", "white"),
            ("Fencing with cattle or ungulate removal (Alts 4 to 6)", [4, 5, 6], "#4292c6", "white"),
            ("No change or other", None, "#e6e6e6", "#1a1a1a")]
    fig, ax = plt.subplots(figsize=(120 * MM, 75 * MM))
    bottom = np.zeros(len(BUDGETS))
    for lab, alts, col, tc in cats:
        vals = []
        for b in BUDGETS:
            a = cp[cp.budget_M == b].alternative
            vals.append(int(a.isin(alts).sum()) if alts else int((~a.isin([4, 5, 6, 7])).sum()))
        vals = np.array(vals)
        ax.bar(range(len(BUDGETS)), vals, 0.62, bottom=bottom, color=col, label=lab,
               edgecolor="white", linewidth=1)
        for i, v in enumerate(vals):
            if v:
                ax.text(i, bottom[i] + v / 2, str(v), ha="center", va="center", color=tc,
                        fontsize=7, fontweight="bold")
        bottom += vals
    ax.set_xticks(range(len(BUDGETS)), [f"${b}M" for b in BUDGETS])
    ax.set_xlabel("Budget")
    ax.set_ylabel("Paddocks under Conservation Priority")
    ax.set_ylim(0, 22.5)
    ax.set_yticks([0, 5, 10, 15, 20, 22])
    ax.legend(frameon=False, loc="upper left", bbox_to_anchor=(0, 1.2), ncol=1)
    save(fig, "Figure_S2_restoration_progression")


if __name__ == "__main__":
    figure3(); figure4(); figure5(); figure_s1(); figure_s2()
