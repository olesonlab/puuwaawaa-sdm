"""
Figures and summary tables for the Puʻuwaʻawaʻa SDM sensitivity analysis.
Reads CSVs written by pww_sensitivity.py.

Usage: python pww_sensitivity_figures.py results_dir
"""
import sys, os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

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
SC = {  # scenario: (label, color, marker, linestyle)
    "S1": ("Balanced", "#0072B2", "o", "-"),
    "S2": ("Conservation priority", "#E69F00", "s", "-"),
    "S5": ("Community priority", "#56B4E9", "^", "--"),
    "S6": ("Rancher-conservation", "#D55E00", "D", "-."),
    "S7": ("Hunter-recreationist", "#CC79A7", "v", ":"),
}
DESIGNS = [("conservation_only", "Conservation\nbenefit"),
           ("community_only", "Community\nscores"),
           ("fire_cost_only", "Fire effect\n& cost"),
           ("joint_pm1", "All inputs\n(±1)"),
           ("joint_pm2", "All inputs\n(±2)")]
FINDINGS = [
    ("asym_holds", "Tradeoff asymmetry\n(T&E lost to S5 > T&E gained by S2)"),
    ("S6_beats_S5", "Rancher-conservation more efficient\nthan Community priority"),
    ("hunter_weaker_than_rancher", "Hunter alignment weaker\nthan rancher alignment"),
    ("S6_alt1_modal", "Alt 1 is the modal action\nunder Rancher-conservation"),
    ("budget_beats_weights", "Budget changes portfolios more\nthan weights do"),
    ("budget_asym_holds", "Conservation spends ≥95% of budget;\nCommunity leaves ≥10% unspent at $60M"),
    ("S2_S3_S4_identical", "S2, S3, S4 identical at $20M"),
    ("alts_8_11_never", "Alts 8–11 never selected"),
]


def panel(ax, letter):
    ax.text(-0.14, 1.04, letter, transform=ax.transAxes, fontsize=12, fontweight="bold", va="bottom")


mc = pd.read_csv(f"{R}/sa_montecarlo.csv")
base = pd.read_csv(f"{R}/sa_baseline_metrics.csv").iloc[0]
oat = pd.read_csv(f"{R}/sa_oat.csv")
ws = pd.read_csv(f"{R}/sa_weight_sweep.csv")
designs = [d for d in DESIGNS if d[0] in set(mc.run)]

# ---------------- Table S2: robustness summary ----------------
rows = []
for key, lab in FINDINGS:
    r = {"finding": lab.replace("\n", " "), "baseline": bool(base[key]),
         "OAT_pct_holds": 100 * oat[key].astype(bool).mean()}
    for d, dl in designs:
        r[dl.replace("\n", " ")] = 100 * mc[mc.run == d][key].astype(bool).mean()
    rows.append(r)
for key, lab in (("asym_ratio", "Asymmetry ratio"), ("eff_S6_rancher", "S6 rancher pts per T&E pt lost"),
                 ("eff_S5_rancher", "S5 rancher pts per T&E pt lost"),
                 ("eff_S7_hunter", "S7 hunter pts per T&E pt lost"),
                 ("S6_alt1_count", "Alt 1 paddocks under S6 at $20M")):
    r = {"finding": lab + " [median (5th–95th)]", "baseline": round(float(base[key]), 2),
         "OAT_pct_holds": f"{oat[key].replace(np.inf, np.nan).min():.2f}–{oat[key].replace(np.inf, np.nan).max():.2f}"}
    for d, dl in designs:
        v = mc[mc.run == d][key].replace(np.inf, np.nan).dropna()
        r[dl.replace("\n", " ")] = f"{v.median():.2f} ({v.quantile(.05):.2f}–{v.quantile(.95):.2f})"
    rows.append(r)
tab = pd.DataFrame(rows)
tab.to_csv(f"{R}/TableS2_robustness_summary.csv", index=False)

# ---------------- Table S3: paddock-level stability at $20M ----------------
j = mc[mc.run == "joint_pm1"]
stab = []
for s in ["S2", "S6", "S5"]:
    b0 = np.array(base[f"choices_{s}_20"].split(","), dtype=int)
    draws = np.array([np.array(x.split(","), dtype=int) for x in j[f"choices_{s}_20"]])
    for i in range(22):
        vals, cnt = np.unique(draws[:, i], return_counts=True)
        stab.append({"scenario": SC[s][0], "paddock": i + 1, "baseline_alt": b0[i],
                     "pct_draws_same_alt": 100 * (draws[:, i] == b0[i]).mean(),
                     "most_common_alt": vals[cnt.argmax()],
                     "pct_draws_alt7": 100 * (draws[:, i] == 7).mean()})
pd.DataFrame(stab).to_csv(f"{R}/TableS3_paddock_stability_20M.csv", index=False)

# ---------------- Figure S4: Monte Carlo robustness ----------------
fig = plt.figure(figsize=(11, 5.2))
gs = fig.add_gridspec(1, 2, width_ratios=[1.0, 1.25], wspace=0.55)
ax = fig.add_subplot(gs[0])
series = [("eff_S6_rancher", "S6", "Rancher-conservation\n(rancher pts / T&E pt)"),
          ("eff_S5_rancher", "S5", "Community priority\n(rancher pts / T&E pt)"),
          ("eff_S7_hunter", "S7", "Hunter-recreationist\n(hunter pts / T&E pt)")]
ny = len(designs)
for k, (key, s, lab) in enumerate(series):
    for di, (d, dl) in enumerate(designs):
        v = mc[mc.run == d][key].replace(np.inf, np.nan).dropna()
        y = di + (k - 1) * 0.24
        q5, q25, q50, q75, q95 = v.quantile([.05, .25, .5, .75, .95])
        ax.plot([q5, q95], [y, y], color=SC[s][1], lw=1.2, solid_capstyle="round")
        ax.plot([q25, q75], [y, y], color=SC[s][1], lw=4, solid_capstyle="round")
        ax.plot(q50, y, marker=SC[s][2], ms=7, mfc="white", mec=SC[s][1], mew=1.6,
                label=lab if di == 0 else None, ls="none")
for k, (key, s, lab) in enumerate(series):
    ax.axvline(base[key], color=SC[s][1], lw=0.8, ls=SC[s][3], alpha=0.8)
ax.set_xscale("log")
ax.set_yticks(range(ny)); ax.set_yticklabels([dl for _, dl in designs])
ax.invert_yaxis()
ax.set_xlabel("Community points gained per T&E point lost at $20M (log scale)")
ax.set_xticks([0.2, 0.5, 1, 2, 5, 10, 20]); ax.set_xticklabels(["0.2", "0.5", "1", "2", "5", "10", "20"])
ax.grid(axis="x", color=GRID, lw=0.6); ax.set_axisbelow(True)
ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=1, frameon=False)
ax.set_title("Exchange ratios under perturbation", loc="left", color=INK)
panel(ax, "A")

ax = fig.add_subplot(gs[1])
M = np.array([[100 * mc[mc.run == d][key].astype(bool).mean() for d, _ in designs] for key, _ in FINDINGS])
im = ax.imshow(M, cmap="Blues", vmin=0, vmax=100, aspect="auto")
for i in range(M.shape[0]):
    for jj in range(M.shape[1]):
        ax.text(jj, i, f"{M[i, jj]:.0f}", ha="center", va="center", fontsize=9,
                color="white" if M[i, jj] > 60 else INK)
ax.set_xticks(range(len(designs))); ax.set_xticklabels([dl for _, dl in designs], fontsize=8)
ax.set_yticks(range(len(FINDINGS))); ax.set_yticklabels([lab for _, lab in FINDINGS], fontsize=8)
ax.tick_params(length=0)
for sp in ax.spines.values():
    sp.set_visible(False)
ax.set_title("% of draws in which each finding holds", loc="left", color=INK)
cb = fig.colorbar(im, ax=ax, fraction=0.04, pad=0.02); cb.set_label("% of draws", fontsize=8)
cb.ax.tick_params(labelsize=8)
panel(ax, "B")
fig.savefig(f"{R}/FigS4_montecarlo_robustness.png"); fig.savefig(f"{R}/FigS4_montecarlo_robustness.pdf"); plt.close(fig)

# ---------------- Figure S5: scores across budgets with uncertainty ----------------
budgets = [5, 10, 20, 40, 60]
fig, axes = plt.subplots(1, 2, figsize=(10, 4.2), sharex=True)
for ax, var, ylab, letter in ((axes[0], "te", "Total T&E score", "A"),
                              (axes[1], "rancher", "Total rancher score", "B")):
    for s, (lab, col, mk, ls) in SC.items():
        q = np.array([j[f"{var}_{s}_{b}"].quantile([.05, .5, .95]).values for b in budgets])
        ax.fill_between(budgets, q[:, 0], q[:, 2], color=col, alpha=0.13, lw=0)
        ax.plot(budgets, [base[f"{var}_{s}_{b}"] for b in budgets], color=col, ls=ls, lw=2,
                marker=mk, ms=6, mfc="white", mec=col, mew=1.4, label=lab)
    ax.set_xlabel("Budget ($ million)"); ax.set_ylabel(ylab)
    ax.set_xticks(budgets)
    ax.grid(axis="y", color=GRID, lw=0.6); ax.set_axisbelow(True)
    panel(ax, letter)
axes[0].legend(frameon=False, loc="upper left")
fig.tight_layout()
fig.savefig(f"{R}/FigS5_budget_scores_uncertainty.png"); fig.savefig(f"{R}/FigS5_budget_scores_uncertainty.pdf"); plt.close(fig)

# ---------------- Figure S6: weight sweep ----------------
fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.3), gridspec_kw={"width_ratios": [1, 1.05]})
ax = axes[0]
line = ws[ws["grid"].isna()] if "grid" in ws else ws
blues = ["#9ec5f4", "#5c9ee8", "#0072B2", "#1b5aa6", "#0d3a73"]
mks = ["o", "s", "^", "D", "v"]
for k, b in enumerate(sorted(line.budget.unique())):
    dd = line[line.budget == b].sort_values("eco_weight")
    ax.plot(dd.eco_weight, dd.te, color=blues[k], lw=2, marker=mks[k], ms=4, markevery=2,
            label=f"${b/1e6:.0f}M")
for s, x in (("S5", 0.2), ("S1", 0.5), ("S2", 0.8)):
    ax.axvline(x, color=INK2, lw=0.7, ls=":")
    ax.text(x, 21.2, s, ha="center", fontsize=8, color=INK2, bbox=dict(fc="white", ec="none", pad=1))
ax.set_ylim(0, 22)
ax.set_xlabel("Weight on ecological objective"); ax.set_ylabel("Total T&E score")
ax.legend(title="Budget", frameon=False, loc="center right", fontsize=8, title_fontsize=8)
ax.grid(axis="y", color=GRID, lw=0.6); ax.set_axisbelow(True)
panel(ax, "A")

ax = axes[1]
g = ws[ws["grid"] == True]
piv = g.pivot(index="eco_weight", columns="rancher_share", values="n_alt1").sort_index(ascending=False)
im = ax.imshow(piv.values, cmap="Purples", vmin=0, vmax=21, aspect="auto")
for i in range(piv.shape[0]):
    for jj in range(piv.shape[1]):
        v = piv.values[i, jj]
        ax.text(jj, i, f"{v:.0f}", ha="center", va="center", fontsize=7,
                color="white" if v > 11 else INK)
ax.set_xticks(range(piv.shape[1])); ax.set_xticklabels([f"{x:.1f}" for x in piv.columns], fontsize=8)
ax.set_yticks(range(piv.shape[0])); ax.set_yticklabels([f"{x:.1f}" for x in piv.index], fontsize=8)
ax.set_xlabel("Rancher share of social weight"); ax.set_ylabel("Weight on ecological objective")
ey = {round(v, 1): i for i, v in enumerate(piv.index)}
ex = {round(v, 1): i for i, v in enumerate(piv.columns)}
for s, (e, r) in {"S1": (0.5, 0.3), "S6": (0.5, 0.7), "S5": (0.2, 0.3), "S2": (0.8, 0.3)}.items():
    ax.add_patch(plt.Rectangle((ex[r] - 0.5, ey[e] - 0.5), 1, 1, fill=False, ec=INK, lw=1.4))
    ax.text(ex[r] + 0.52, ey[e] - 0.52, s, fontsize=7, color=INK, ha="left", va="bottom", fontweight="bold")
for sp in ax.spines.values():
    sp.set_visible(False)
ax.tick_params(length=0)
ax.set_title("Paddocks assigned Alt 1 (fence + fuelbreaks) at $20M", loc="left", fontsize=10, color=INK)
cb = fig.colorbar(im, ax=ax, fraction=0.04, pad=0.02); cb.ax.tick_params(labelsize=8)
panel(ax, "B")
fig.tight_layout()
fig.savefig(f"{R}/FigS6_weight_sweep.png"); fig.savefig(f"{R}/FigS6_weight_sweep.pdf"); plt.close(fig)

# ---------------- Figure S7: OAT tornado ----------------
oat[["group", "item", "dir"]] = oat.param.str.split("|", expand=True)
oat["label"] = oat.group + ": " + oat.item
fig, axes = plt.subplots(1, 2, figsize=(11, 5.2))
for ax, key, xl, letter in ((axes[0], "eff_S6_rancher", "Rancher-conservation exchange ratio", "A"),
                            (axes[1], "asym_ratio", "Asymmetry ratio", "B")):
    b0 = base[key]
    t = oat.pivot_table(index="label", columns="dir", values=key, aggfunc="first")
    t["lo"] = t.min(axis=1); t["hi"] = t.max(axis=1)
    t["range"] = (t.hi - t.lo).abs()
    t = t.sort_values("range", ascending=False).head(12).iloc[::-1]
    for i, (lab, r) in enumerate(t.iterrows()):
        for dcol, col, off in (("-1", "#56B4E9", -0.2), ("+1", "#0072B2", 0.2)):
            if dcol in r and pd.notna(r[dcol]):
                v = min(r[dcol], 12)
                ax.barh(i + off, v - b0, left=b0, height=0.36, color=col,
                        edgecolor="black", lw=0.4)
                if r[dcol] > 12:
                    ax.text(12.1, i + off, f"{r[dcol]:.0f}", va="center", fontsize=7, color=INK2)
    ax.axvline(b0, color=INK, lw=1)
    ax.axvline(1, color=INK2, lw=0.8, ls="--")
    ax.set_yticks(range(len(t))); ax.set_yticklabels(t.index, fontsize=8)
    ax.set_xlabel(xl); ax.grid(axis="x", color=GRID, lw=0.6); ax.set_axisbelow(True)
    panel(ax, letter)
from matplotlib.patches import Patch
fig.legend(handles=[Patch(fc="#56B4E9", ec="black", lw=0.4, label="Input lowered"),
                        Patch(fc="#0072B2", ec="black", lw=0.4, label="Input raised")],
               frameon=False, loc="upper center", bbox_to_anchor=(0.5, 0.02), ncol=2, fontsize=9)
fig.tight_layout(rect=(0, 0.05, 1, 1))
fig.savefig(f"{R}/FigS7_oat_tornado.png"); fig.savefig(f"{R}/FigS7_oat_tornado.pdf"); plt.close(fig)
print(tab.to_string())
