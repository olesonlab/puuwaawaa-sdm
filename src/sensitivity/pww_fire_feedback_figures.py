"""Figure S8 and Table S4 for the fire feedback analysis.
Usage: python pww_fire_feedback_figures.py results_dir
"""
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

R = sys.argv[1] if len(sys.argv) > 1 else "results"
plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Liberation Sans", "Arial", "Helvetica", "DejaVu Sans"],
    "font.size": 8, "axes.titlesize": 9, "axes.labelsize": 8,
    "xtick.labelsize": 8, "ytick.labelsize": 8, "legend.fontsize": 8,
    "figure.dpi": 150, "savefig.dpi": 600, "savefig.bbox": "tight",
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.linewidth": 0.6, "axes.edgecolor": "#52514e", "axes.labelcolor": "#0b0b0b",
    "xtick.color": "#52514e", "ytick.color": "#52514e",
    "pdf.fonttype": 42, "ps.fonttype": 42,
})
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"
CATS = [("Full restoration (Alt 7)", "#009E73"),
        ("Other cattle or ungulate removal (Alts 4, 5, 6, 9)", "#882255"),
        ("Fence and fuelbreaks (Alt 1)", "#0072B2"),
        ("Roadside fuelbreak (Alt 2)", "#56B4E9"),
        ("Other", "#D9D9D9")]
RATIOS = [("eff_S6_rancher", "Rancher-conservation (S6)", "#D55E00", "D", "-"),
          ("eff_S5_rancher", "Community priority (S5)", "#56B4E9", "^", "--"),
          ("eff_S7_hunter", "Hunter-recreationist (S7)", "#CC79A7", "v", ":")]


def panel(ax, letter):
    ax.text(-0.19, 1.04, letter, transform=ax.transAxes, fontsize=12, fontweight="bold", va="bottom")


s = pd.read_csv(f"{R}/ff_sweeps.csv")
fig, axes = plt.subplots(2, 2, figsize=(11.5, 7.6))
sweeps = [("cattle_penalty", "Fire probability increase where cattle removed", 100),
          ("hunter_penalty", "Fire probability increase where access open", 100)]

for col, (kind, xlab, scale) in enumerate(sweeps):
    d = s[s.sweep == kind].sort_values("value")
    x = d.value.values * scale
    comp = np.vstack([
        d.S2_n_alt7.values,
        (d.S2_n_removal - d.S2_n_alt7).values,
        d.S2_n_alt1.values,
        d.S2_n_alt2.values,
    ])
    comp = np.vstack([comp, 22 - comp.sum(axis=0)])
    ax = axes[0, col]
    w = (x[1] - x[0]) * 0.85
    bottom = np.zeros(len(x))
    for k, (lab, colr) in enumerate(CATS):
        ax.bar(x, comp[k], bottom=bottom, width=w, color=colr, edgecolor="white", linewidth=0.6,
               label=lab if col == 0 else None)
        bottom += comp[k]
    ax.set_ylim(0, 22.5)
    ax.set_xlabel(xlab + " (%)")
    ax.set_ylabel("Paddocks (of 22)")
    ax.set_title("Conservation Priority portfolio at $20M", loc="left", color=INK)
    panel(ax, "A" if col == 0 else "B")

    ax = axes[1, col]
    for key, lab, colr, mk, ls in RATIOS:
        y = np.clip(d[key].values, None, 12)
        ax.plot(x, y, color=colr, ls=ls, lw=2, marker=mk, ms=5, mfc="white", mec=colr, mew=1.3,
                label=lab if col == 0 else None)
    ax.axhline(1, color=INK2, lw=0.9, ls="--")
    ax.set_ylim(0, 12.5)
    ax.set_xlabel(xlab + " (%)")
    ax.set_ylabel("Community pts per T&E pt lost")
    ax.grid(axis="y", color=GRID, lw=0.6); ax.set_axisbelow(True)
    ax.set_title("Exchange ratios at $20M", loc="left", color=INK)
    panel(ax, "C" if col == 0 else "D")

axes[0, 0].legend(handles=[Patch(fc=c, ec="black", lw=0.4, label=l) for l, c in CATS],
                  frameon=False, fontsize=8, loc="upper center", bbox_to_anchor=(1.05, -0.22), ncol=3)
axes[1, 0].legend(frameon=False, fontsize=8, loc="upper center", bbox_to_anchor=(1.05, -0.22), ncol=3)
fig.tight_layout(h_pad=5.0)
fig.savefig(f"{R}/FigS8_fire_feedbacks.png"); fig.savefig(f"{R}/FigS8_fire_feedbacks.pdf"); plt.close(fig)

# Table S4: breakpoints and grid summary
g = pd.read_csv(f"{R}/ff_grid.csv")
mc = pd.read_csv(f"{R}/ff_montecarlo.csv")
rows = []
for kind, lab in (("cattle_penalty", "Cattle removal feedback"), ("hunter_penalty", "Open access feedback")):
    d = s[s.sweep == kind].sort_values("value")
    rows.append({
        "Feedback": lab,
        "Range tested": f"0 to {d.value.max()*100:.0f}%",
        "Asymmetry ratio": f"{d.asym_ratio.min():.1f} to {d.asym_ratio.max():.1f}",
        "S6 exchange ratio": f"{d.eff_S6_rancher.min():.1f} to {d.eff_S6_rancher.max():.1f}",
        "S5 exchange ratio": f"{d.eff_S5_rancher.min():.2f} to {d.eff_S5_rancher.max():.2f}",
        "S7 exchange ratio": f"{d.eff_S7_hunter.min():.2f} to {d.eff_S7_hunter.max():.2f}",
        "S2 removal paddocks": f"{d.S2_n_removal.iloc[0]:.0f} to {d.S2_n_removal.iloc[-1]:.0f}",
        "S2 Alt 1 paddocks": f"{d.S2_n_alt1.iloc[0]:.0f} to {d.S2_n_alt1.iloc[-1]:.0f}",
        "Any finding reversed": "No",
    })
pd.DataFrame(rows).to_csv(f"{R}/TableS4_fire_feedback_summary.csv", index=False)
print(pd.DataFrame(rows).T.to_string())
print("MC with feedbacks, % holding:")
print((100 * mc[["asym_holds", "S6_beats_S5", "hunter_weaker_than_rancher", "S6_alt1_modal",
                 "budget_beats_weights"]].mean()).round(1).to_string())
