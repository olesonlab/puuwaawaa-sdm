"""
Figure generation for:
  Oleson et al. "Structured Decision Making reveals asymmetric tradeoffs
  between conservation and community objectives at Puʻuwaʻawaʻa Forest Reserve, Hawaiʻi"

Requires sdm_results_summary.csv and sdm_results_paddock_detail.csv produced
by pww_sdm_optimizer.py.

Usage:
    python figures.py --results_dir ./results --output_dir ./figures
"""

import argparse
import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.colors import LinearSegmentedColormap

# ── Colour palette ────────────────────────────────────────────────
SCENARIO_COLORS = {
    "Balanced":              "#6baed6",
    "Conservation priority": "#08519c",
    "T&E emphasis":          "#2171b5",
    "Habitat emphasis":      "#4292c6",
    "Community priority":    "#d73027",
    "Rancher-conservation":  "#f46d43",
    "Hunter-recreationist":  "#74c476",
}

SCENARIO_ORDER = list(SCENARIO_COLORS.keys())

ALT_COLORS = {
    1:  "#4dac26",
    2:  "#b8e186",
    3:  "#d01c8b",
    4:  "#7b3294",
    5:  "#c2a5cf",
    6:  "#a6dba0",
    7:  "#008837",
    8:  "#e66101",
    9:  "#fdb863",
    10: "#5e3c99",
    11: "#d3d3d3",
}


# ── Figure 3: Asymmetric tradeoffs bar chart at $20M ─────────────
def fig_asymmetric_tradeoffs(summary_df, budget=20_000_000, output_dir="."):
    balanced = summary_df[
        (summary_df["scenario"] == "Balanced") &
        (summary_df["budget"] == budget)
    ].iloc[0]

    sub_objectives = ["te_score", "habitat_score", "rancher_score",
                      "hunter_score", "recreationist_score"]
    labels = ["T&E", "Habitat", "Rancher", "Hunter", "Recreationist"]

    fig, axes = plt.subplots(1, len(SCENARIO_ORDER), figsize=(14, 4), sharey=False)
    fig.suptitle(f"Score changes from Balanced baseline at $20M",
                 fontsize=11, fontweight="bold")

    for ax, scenario in zip(axes, SCENARIO_ORDER):
        row = summary_df[
            (summary_df["scenario"] == scenario) &
            (summary_df["budget"] == budget)
        ]
        if row.empty or scenario == "Balanced":
            ax.set_title(scenario, fontsize=8)
            ax.axhline(0, color="black", linewidth=0.8)
            ax.set_xticks(range(len(labels)))
            ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=7)
            continue

        deltas = [row.iloc[0][col] - balanced[col] for col in sub_objectives]
        colors = ["#08519c" if d >= 0 else "#d73027" for d in deltas]
        ax.bar(range(len(deltas)), deltas, color=colors, edgecolor="white")
        ax.axhline(0, color="black", linewidth=0.8)
        ax.set_title(scenario, fontsize=8)
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=7)
        ax.set_ylabel("Score change" if ax == axes[0] else "", fontsize=8)

    plt.tight_layout()
    path = os.path.join(output_dir, "fig3_asymmetric_tradeoffs.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved: {path}")


# ── Figure 4: Sub-objective scores across budgets ────────────────
def fig_scores_across_budgets(summary_df, output_dir="."):
    sub_objectives = ["te_score", "habitat_score", "rancher_score",
                      "hunter_score", "recreationist_score"]
    titles = ["T&E score", "Habitat score", "Rancher score",
              "Hunter score", "Recreationist score"]

    fig, axes = plt.subplots(1, 5, figsize=(15, 4), sharey=False)
    fig.suptitle("Sub-objective scores across budgets under seven weighting scenarios",
                 fontsize=10, fontweight="bold")

    for ax, col, title in zip(axes, sub_objectives, titles):
        for scenario, color in SCENARIO_COLORS.items():
            sub = summary_df[summary_df["scenario"] == scenario].sort_values("budget")
            ax.plot(sub["budget"] / 1e6, sub[col],
                    color=color, marker="o", markersize=4, linewidth=1.5,
                    label=scenario)
        ax.set_title(title, fontsize=9)
        ax.set_xlabel("Budget ($M)", fontsize=8)
        ax.set_ylabel("Total score" if ax == axes[0] else "", fontsize=8)
        ax.tick_params(labelsize=7)

    handles = [mpatches.Patch(color=c, label=s)
               for s, c in SCENARIO_COLORS.items()]
    fig.legend(handles=handles, loc="lower center", ncol=4,
               fontsize=7, bbox_to_anchor=(0.5, -0.15))
    plt.tight_layout()
    path = os.path.join(output_dir, "fig4_scores_across_budgets.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved: {path}")


# ── Figure 5: Portfolio heatmap at $20M ──────────────────────────
def fig_portfolio_heatmap(detail_df, budget=20_000_000, output_dir="."):
    sub = detail_df[detail_df["budget"] == budget].copy()
    pivot = sub.pivot_table(
        index="paddock", columns="scenario",
        values="alternative", aggfunc="first"
    )[SCENARIO_ORDER]

    fig, ax = plt.subplots(figsize=(10, 8))
    n_paddocks, n_scenarios = pivot.shape
    cmap = plt.cm.get_cmap("tab20", 11)

    im = ax.imshow(pivot.values, aspect="auto", cmap=cmap,
                   vmin=0.5, vmax=11.5, interpolation="nearest")

    ax.set_xticks(range(n_scenarios))
    ax.set_xticklabels(SCENARIO_ORDER, rotation=45, ha="right", fontsize=8)
    ax.set_yticks(range(n_paddocks))
    ax.set_yticklabels([f"Paddock {i}" for i in pivot.index], fontsize=7)
    ax.set_title(f"Management portfolios at $20M — selected alternative per paddock",
                 fontsize=10, fontweight="bold")

    cbar = plt.colorbar(im, ax=ax, ticks=range(1, 12))
    cbar.set_label("Alternative", fontsize=8)
    plt.tight_layout()
    path = os.path.join(output_dir, "fig5_portfolio_heatmap.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved: {path}")


# ── Figure 6: Conservation–rancher scatter at $20M ───────────────
def fig_conservation_rancher_scatter(summary_df, budget=20_000_000, output_dir="."):
    sub = summary_df[summary_df["budget"] == budget]
    fig, ax = plt.subplots(figsize=(6, 5))

    for _, row in sub.iterrows():
        color = SCENARIO_COLORS.get(row["scenario"], "gray")
        ax.scatter(row["rancher_score"], row["te_score"],
                   color=color, s=80, zorder=3)
        ax.annotate(row["scenario"], (row["rancher_score"], row["te_score"]),
                    textcoords="offset points", xytext=(5, 2), fontsize=7)

    ax.set_xlabel("Total rancher score", fontsize=10)
    ax.set_ylabel("Total T&E score", fontsize=10)
    ax.set_title("Conservation–rancher tradeoff at $20M", fontsize=10, fontweight="bold")
    ax.grid(alpha=0.3)
    plt.tight_layout()
    path = os.path.join(output_dir, "fig6_conservation_rancher_scatter.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved: {path}")


# ── Figure 7: Restoration progression under Conservation Priority ───
ndef fig_restoration_progression(detail_df, output_dir="."):
    scenario = "Conservation priority"
    sub = detail_df[detail_df["scenario"] == scenario].copy()
    budgets = sorted(sub["budget"].unique())

    alt_counts = []
    for b in budgets:
        bsub = sub[sub["budget"] == b]
        counts = bsub["alternative"].value_counts().to_dict()
        alt_counts.append(counts)

    alts = sorted(set(a for c in alt_counts for a in c.keys()))
    budget_labels = [f"${b/1e6:.0f}M" for b in budgets]

    bottom = np.zeros(len(budgets))
    fig, ax = plt.subplots(figsize=(8, 5))
    for alt in alts:
        vals = [c.get(alt, 0) for c in alt_counts]
        ax.bar(budget_labels, vals, bottom=bottom,
               color=ALT_COLORS.get(alt, "gray"), label=f"Alt {alt}")
        bottom += np.array(vals)

    ax.set_xlabel("Budget", fontsize=10)
    ax.set_ylabel("Number of paddocks", fontsize=10)
    ax.set_title(f"Restoration progression — {scenario}", fontsize=10, fontweight="bold")
    ax.legend(loc="upper left", fontsize=7, ncol=2)
    plt.tight_layout()
    path = os.path.join(output_dir, "fig7_restoration_progression.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved: {path}")


def _gini(x):
    x = np.sort(np.array(x, dtype=float))
    n = len(x)
    cumx = np.cumsum(x)
    return (n + 1 - 2 * np.sum(cumx) / cumx[-1]) / n


# ── Main ─────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Generate figures for Oleson et al. Paper 2")
    parser.add_argument("--results_dir", default="./results",
                        help="Directory containing sdm_results_*.csv files")
    parser.add_argument("--output_dir", default="./figures",
                        help="Directory to write figures to")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    print("Loading results...")
    summary = pd.read_csv(os.path.join(args.results_dir, "sdm_results_summary.csv"))
    detail = pd.read_csv(os.path.join(args.results_dir, "sdm_results_paddock_detail.csv"))

    print("Generating figures...")
    fig_asymmetric_tradeoffs(summary, output_dir=args.output_dir)
    fig_scores_across_budgets(summary, output_dir=args.output_dir)
    fig_portfolio_heatmap(detail, output_dir=args.output_dir)
    fig_conservation_rancher_scatter(summary, output_dir=args.output_dir)
    fig_restoration_progression(detail, output_dir=args.output_dir)
    print("Done.")


if __name__ == "__main__":
    main()
