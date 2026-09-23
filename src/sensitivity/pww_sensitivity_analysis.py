"""
Puʻuwaʻawaʻa SDM: sensitivity analysis of the fire management portfolio model.

The portfolio model selects one management alternative for each of 22 paddocks
in Puʻuwaʻawaʻa Forest Reserve to maximize a weighted sum of normalized
sub-objective scores under a budget constraint. Conservation scores are
normalized within paddocks, community scores globally. Paddock 9 is pre-assigned
to full restoration and excluded from the optimization. The roadside fuelbreak
is a single landscape decision rather than a paddock-level alternative: every
scenario and budget is solved with and without it, and the better solution is
kept.

This script re-expresses that model with every elicited or assumed input as an
explicit parameter, then measures how far those inputs can move before the
results change. It runs four analyses:

  1. One-at-a-time perturbation of each input in the consequence table.
  2. Monte Carlo perturbation of all inputs, jointly and by source.
  3. Continuous sweeps of the objective weights.
  4. Sweeps of two fire feedbacks that the consequence table leaves out:
     fine fuel accumulation where cattle are removed, and human ignition where
     paddocks stay open to hunters and other users.
  5. A sweep of the weight on fire risk treated as a fundamental objective on an
     absolute scale, which is what a landscape-scale action has to be judged
     against: within-paddock normalization rescales each paddock independently,
     so a benefit spread evenly across the reserve largely cancels out.

Each run reoptimizes all 35 scenario by budget combinations and records whether
a set of headline findings still holds.

Usage
-----
    python pww_sensitivity_analysis.py INPUT.xlsx OUTDIR [--draws N]
                                       [--stages sensitivity,feedbacks,figures]

INPUT.xlsx is the workshop workbook with the paddock_data, native_rareplants,
People, and flammability sheets. Results, figures, and summary tables are
written to OUTDIR. --draws sets the Monte Carlo size (default 500); the Monte
Carlo designs use n/2 draws each except the joint design, which uses n.

Requires numpy, pandas, matplotlib, and pulp.
"""

import argparse
import itertools
import os
import sys
import time
from multiprocessing import Pool

import numpy as np
import pandas as pd
import pulp
from pulp import LpMaximize, LpProblem, LpVariable, lpSum, LpStatus, value

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch


# ======================================================================
# 1. MODEL SETUP
# ======================================================================

N_PADDOCKS, N_ALTS = 22, 11
FIXED_PADDOCK_IDX = 8          # paddock 9, pre-assigned
FIXED_ALT_IDX = 6              # alternative 7, full restoration
BUDGETS = [5_000_000, 10_000_000, 20_000_000, 40_000_000, 60_000_000]
B20 = 20_000_000               # the budget most results are reported at

# Direct conservation benefit of each alternative, elicited on a -1 to 6 scale.
DIRECT_BENEFIT = np.array([1, 1, -1, 2, 3, 3, 6, 1, 2, 1, 1], dtype=float)

# Community interest base scores per alternative, before elevation weighting.
# Recovered from the People sheet and checked against it in load_data().
BASE_REC = np.array([1, 3, 3, 1, 1, 1, 3, 1, 1, 2, 0], dtype=float)
BASE_HUNT = np.array([1, 1, 1, -2, -4, -4, -4, 1, -3, 2, 0], dtype=float)
BASE_RANCH = np.array([3, 1, 4, -4, -4, -4, -4, 1, -4, 2, 0], dtype=float)

# Elevation-zone multipliers. Ranchers and hunters value upper-elevation
# paddocks most, recreationists the lower, most accessible ones.
MULT_REC = {"Makai": 3.0, "Middle": 1.0, "Mauka": 2.0}
MULT_HUNT = {"Makai": 1.0, "Middle": 2.0, "Mauka": 3.0}
MULT_RANCH = {"Makai": 1.0, "Middle": 2.0, "Mauka": 3.0}
ZONES = ["Makai", "Middle", "Mauka"]

# Fire effects assumed in the consequence table.
FUELBREAK_EFFECT = 0.50        # proportional reduction in Q3 fire probability
FUELBREAK_ALTS = [0, 2, 3, 4, 5, 7, 8]   # alternatives 1, 3, 4, 5, 6, 8, 9

# The roadside fuelbreak is a single landscape decision, not a paddock-level
# alternative: built once for the whole reserve or not at all. When built it
# lowers fire probability in every paddock. Paddocks choose among the other ten
# alternatives, so alternative 2 never appears in a portfolio.
ROADSIDE_ALT = 1                         # alternative 2
ROADSIDE_COST = 137677.06  # single cost for roadside fuel break, paddock_data[26,6]
ROADSIDE_EFFECT = 0.20
# Optional taper in the roadside benefit with distance from the highway, which
# all paddocks sit above. Band 0 is nearest (Makai), band 2 furthest (Mauka),
# and the benefit in band k is scaled by (1 - roadside_decay) ** k, so a decay
# of 0 applies the effect evenly and a decay of 1 confines it to band 0.
ROADSIDE_BANDS = {"Makai": 0, "Middle": 1, "Mauka": 2}
PADDOCK_ALTS = [j for j in range(N_ALTS) if j != ROADSIDE_ALT]

# Alternatives affected by the two fire feedbacks tested in stage 4.
CATTLE_REMOVAL_ALTS = [3, 4, 5, 6, 8]    # alternatives 4, 5, 6, 7, 9
OPEN_ACCESS_ALTS = [0, 2, 7, 9, 10]      # alternatives 1, 3, 8, 10, 11

ALT_NAMES = [
    "1: fence + fuelbreaks",
    "2: roadside fuelbreak",
    "3: fence + intensify grazing",
    "4: fence + fuelbreak + remove cattle",
    "5: fence + fuelbreak + remove cattle + remove ungulates",
    "6: Alt 5 + weed control around T&E",
    "7: full restoration",
    "8: fence + fuelbreak + weed control around T&E",
    "9: fence + fuelbreak + remove cattle + weed control",
    "10: fence + plant native species",
    "11: no change",
]

# Weighting scenarios: (label, ecological weight, (T&E share, habitat share),
# (rancher share, hunter share, recreationist share)). The social weight is
# one minus the ecological weight; shares divide each fundamental objective.
SCENARIOS = {
    "S1": ("Balanced", 0.50, (0.50, 0.50), (0.33, 0.33, 0.34)),
    "S2": ("Conservation Priority", 0.80, (0.50, 0.50), (0.33, 0.33, 0.34)),
    "S3": ("T&E Emphasis", 0.80, (0.75, 0.25), (0.33, 0.33, 0.34)),
    "S4": ("Habitat Emphasis", 0.80, (0.25, 0.75), (0.33, 0.33, 0.34)),
    "S5": ("Community Priority", 0.20, (0.50, 0.50), (0.33, 0.33, 0.34)),
    "S6": ("Rancher-Conservation", 0.50, (0.50, 0.50), (0.70, 0.15, 0.15)),
    "S7": ("Hunter-Recreationist", 0.20, (0.50, 0.50), (0.10, 0.45, 0.45)),
}

SUBOBJ = ["te", "habitat", "rancher", "hunter", "recreationist"]


def effective_weights(eco, eco_split, soc_split):
    """Weight on each sub-objective: fundamental weight times within-group share."""
    soc = 1.0 - eco
    return {"te": eco * eco_split[0], "habitat": eco * eco_split[1],
            "rancher": soc * soc_split[0], "hunter": soc * soc_split[1],
            "recreationist": soc * soc_split[2]}


def weights_with_fire(eco, eco_split, soc_split, fire_weight):
    """Scenario weights with fire risk promoted to a fundamental objective.

    The fire objective takes fire_weight of the total; the ecological and social
    objectives keep their relative split across what remains.
    """
    w = {k: v * (1.0 - fire_weight)
         for k, v in effective_weights(eco, eco_split, soc_split).items()}
    w["fire"] = fire_weight
    return w


def default_params():
    """Every elicited or assumed input, at the values used in the main analysis."""
    return dict(
        direct=DIRECT_BENEFIT.copy(),
        base_rec=BASE_REC.copy(), base_hunt=BASE_HUNT.copy(), base_ranch=BASE_RANCH.copy(),
        mult_rec=dict(MULT_REC), mult_hunt=dict(MULT_HUNT), mult_ranch=dict(MULT_RANCH),
        fuelbreak=FUELBREAK_EFFECT, roadside=ROADSIDE_EFFECT,
        cost_mult=np.ones(N_ALTS), roadside_cost_mult=1.0, roadside_decay=0.0,
        cattle_penalty=0.0, hunter_penalty=0.0,
    )


def community_matrix(zones, base, mult):
    """Paddock by alternative community scores from base scores and zone multipliers."""
    return np.array([base * mult[z] for z in zones])


def load_data(filepath):
    """Read paddock attributes, costs, ecological metrics, community scores, and
    fire probabilities from the input workbook."""
    xls = pd.ExcelFile(filepath)

    data = pd.read_excel(xls, "paddock_data", header=None)
    zones = [str(data.iloc[i + 2, 2]).strip() for i in range(N_PADDOCKS)]
    costs = np.array([[data.iloc[i + 2, 5 + j] if pd.notna(data.iloc[i + 2, 5 + j]) else 0.0
                       for j in range(N_ALTS)] for i in range(N_PADDOCKS)], dtype=float)
    costs[:, ROADSIDE_ALT] = 0.0   # charged once at landscape level instead

    rp = pd.read_excel(xls, "native_rareplants", header=None)
    te_count = np.array([rp.iloc[i + 4, 2] for i in range(N_PADDOCKS)], dtype=float)
    native_cover = np.array([rp.iloc[i + 4, 1] for i in range(N_PADDOCKS)], dtype=float)

    ppl = pd.read_excel(xls, "People", header=None)
    raw = {key: np.array([[ppl.iloc[i + 2, col + j] if pd.notna(ppl.iloc[i + 2, col + j]) else 0.0
                           for j in range(N_ALTS)] for i in range(N_PADDOCKS)], dtype=float)
           for key, col in (("rec", 2), ("hunt", 15), ("ranch", 28))}

    flam = pd.read_excel(xls, "flammability", header=None)
    fp0 = np.array([flam.iloc[i + 4, 1] for i in range(N_PADDOCKS)], dtype=float)
    fp = np.array([[flam.iloc[i + 4, 5 + j] for j in range(N_ALTS)]
                   for i in range(N_PADDOCKS)], dtype=float)
    # The roadside column describes the landscape action, so an untreated
    # paddock keeps its baseline fire probability.
    fp[:, ROADSIDE_ALT] = fp0

    d = dict(zones=zones, costs=costs, te_count=te_count, native_cover=native_cover,
             fp0=fp0, fp=fp, raw=raw)

    # Confirm that base scores and multipliers reproduce the workbook exactly,
    # so the parametrized form is verified against the data on every run.
    p = default_params()
    for key, base_key, mult_key in (("rec", "base_rec", "mult_rec"),
                                    ("hunt", "base_hunt", "mult_hunt"),
                                    ("ranch", "base_ranch", "mult_ranch")):
        rebuilt = community_matrix(zones, p[base_key], p[mult_key])
        assert np.allclose(rebuilt, raw[key]), f"community scores do not match sheet: {key}"
    return d


# ======================================================================
# 2. SCORING AND OPTIMIZATION
# ======================================================================

def fire_matrix(d, p, roadside_built=False):
    """Post-treatment fire probability per paddock and alternative.

    Modeled reductions are rescaled to the fuelbreak effect in p. Building the
    roadside fuelbreak lowers probability in every paddock. The two feedbacks
    then raise probability proportionally where cattle are removed and where a
    paddock stays open to hunters and other users.
    """
    fp0 = d["fp0"]
    reduction = fp0[:, None] - d["fp"]
    reduction[:, FUELBREAK_ALTS] *= p["fuelbreak"] / FUELBREAK_EFFECT
    fp = fp0[:, None] - reduction
    if roadside_built:
        bands = np.array([ROADSIDE_BANDS[z] for z in d["zones"]], dtype=float)
        effect = p["roadside"] * (1.0 - p.get("roadside_decay", 0.0)) ** bands
        fp = fp * (1.0 - effect)[:, None]
    if p.get("cattle_penalty"):
        fp[:, CATTLE_REMOVAL_ALTS] *= 1.0 + p["cattle_penalty"]
    if p.get("hunter_penalty"):
        fp[:, OPEN_ACCESS_ALTS] *= 1.0 + p["hunter_penalty"]
    return np.minimum(fp, 1.0)


def build_scores(d, p, roadside_built=False):
    """Normalized score matrices for the 21 optimized paddocks.

    Conservation effectiveness combines the elicited direct benefit with the
    spatially varying fire risk reduction, rescaled to the same range, then is
    normalized within each paddock so the best alternative scores 1 and the
    worst 0. Community scores are normalized globally by min-max.

    Scores cover the ten paddock-level alternatives, in PADDOCK_ALTS order.

    The score dict also carries an absolute fire score: the fire probability
    avoided relative to the untreated paddock, divided by the largest avoidable
    probability anywhere in the reserve. Unlike the within-paddock conservation
    scores, this one shares a denominator across paddocks and across both states
    of the roadside fuelbreak, so a benefit spread evenly over the landscape is
    still visible. It carries zero weight unless the landscape stage turns it on.

    Returns the score dict, the indices of the optimized paddocks, their cost
    matrix, the fire probability matrix, and the normalized conservation score
    of the pre-assigned paddock.
    """
    fp = fire_matrix(d, p, roadside_built)
    reduction = d["fp0"][:, None] - fp   # negative where a feedback raises risk
    scaled_fire = (reduction / reduction.max() * 6.0 if reduction.max() > 0
                   else np.zeros_like(reduction))
    action = p["direct"][None, :] + scaled_fire

    opt = [i for i in range(N_PADDOCKS) if i != FIXED_PADDOCK_IDX]
    a = action[np.ix_(opt, PADDOCK_ALTS)]
    within = np.zeros_like(a)
    for i in range(a.shape[0]):
        lo, hi = a[i].min(), a[i].max()
        if hi > lo:
            within[i] = (a[i] - lo) / (hi - lo)

    te = within.copy()
    for k, orig in enumerate(opt):
        if d["te_count"][orig] == 0:
            te[k] = 0.0            # paddocks with no T&E plants earn no T&E score

    def minmax(x):
        return (x - x.min()) / (x.max() - x.min()) if x.max() > x.min() else np.zeros_like(x)

    z = d["zones"]
    scores = {
        "te": te,
        "habitat": within.copy(),
        "recreationist": minmax(
            community_matrix(z, p["base_rec"], p["mult_rec"])[np.ix_(opt, PADDOCK_ALTS)]),
        "hunter": minmax(
            community_matrix(z, p["base_hunt"], p["mult_hunt"])[np.ix_(opt, PADDOCK_ALTS)]),
        "rancher": minmax(
            community_matrix(z, p["base_ranch"], p["mult_ranch"])[np.ix_(opt, PADDOCK_ALTS)]),
    }

    # Absolute fire score, on a reference shared by both roadside states
    fp_best = fire_matrix(d, p, roadside_built=True)
    ref = float((d["fp0"][:, None] - fp_best).max())
    avoided = d["fp0"][:, None] - fp
    scores["fire"] = (avoided[np.ix_(opt, PADDOCK_ALTS)] / ref if ref > 0
                      else np.zeros((len(opt), len(PADDOCK_ALTS))))

    fixed = action[FIXED_PADDOCK_IDX]
    fixed_score = ((fixed[FIXED_ALT_IDX] - fixed.min()) / (fixed.max() - fixed.min())
                   if fixed.max() > fixed.min() else 0.0)
    costs = (d["costs"] * p["cost_mult"][None, :])[np.ix_(opt, PADDOCK_ALTS)]
    return scores, opt, costs, fp, fixed_score


def optimize(scores, costs, budget, weights):
    """Choose one paddock-level alternative per paddock to maximize the weighted
    score sum within the budget. Returns None if the program is infeasible."""
    n, m = costs.shape
    prob = LpProblem("PWW", LpMaximize)
    x = [[LpVariable(f"x_{i}_{j}", cat="Binary") for j in range(m)] for i in range(n)]

    prob += lpSum(weights[k] * scores[k][i, j] * x[i][j]
                  for k in weights if weights[k] != 0
                  for i in range(n) for j in range(m))
    for i in range(n):
        prob += lpSum(x[i]) == 1                      # exactly one alternative
    prob += lpSum(costs[i, j] * x[i][j]
                  for i in range(n) for j in range(m)) <= budget

    prob.solve(pulp.PULP_CBC_CMD(msg=0))
    if LpStatus[prob.status] != "Optimal":
        return None

    choices = np.array([max(range(m), key=lambda j: value(x[i][j])) for i in range(n)])
    cost = sum(costs[i, choices[i]] for i in range(n))
    sub = {k: float(sum(scores[k][i, choices[i]] for i in range(n))) for k in scores}
    return dict(choices=choices, cost=cost, sub=sub, objective=value(prob.objective))


def run_grid(d, p, budgets=None, weights_override=None):
    """Optimize every scenario by budget combination for one parameter set.

    Each combination is solved twice, with and without the roadside fuelbreak,
    and the higher-scoring solution is kept.

    weights_override replaces the seven scenarios with an explicit
    {label: weights} mapping, which the weight sweeps use.
    """
    states = {built: build_scores(d, p, built) for built in (False, True)}
    fixed_cost = d["costs"][FIXED_PADDOCK_IDX, FIXED_ALT_IDX] * p["cost_mult"][FIXED_ALT_IDX]
    road_cost = ROADSIDE_COST * p["roadside_cost_mult"]
    items = (weights_override.items() if weights_override else
             ((sid, effective_weights(*SCENARIOS[sid][1:])) for sid in SCENARIOS))

    results = []
    for sid, w in items:
        for budget in (budgets or BUDGETS):
            best = None
            for built, (scores, opt, costs, fp, fixed_score) in states.items():
                available = budget - fixed_cost - (road_cost if built else 0.0)
                if available < 0:
                    continue   # budget cannot cover the pre-assigned paddock
                r = optimize(scores, costs, available, w)
                if r is None:
                    continue
                if best is None or r["objective"] > best[0]["objective"]:
                    best = (r, built, opt, fp, fixed_score)
            if best is None:
                continue
            r, built, opt, fp, fixed_score = best
            choices = np.zeros(N_PADDOCKS, dtype=int)
            choices[FIXED_PADDOCK_IDX] = FIXED_ALT_IDX
            for k, orig in enumerate(opt):
                choices[orig] = PADDOCK_ALTS[r["choices"][k]]
            fire = float(np.mean([d["fp0"][i] - fp[i, choices[i]] for i in range(N_PADDOCKS)]))
            results.append(dict(
                scenario=sid, budget=budget, choices=choices, roadside_built=built,
                total_cost=r["cost"] + fixed_cost + (road_cost if built else 0.0),
                objective=r["objective"],
                te=r["sub"]["te"] + fixed_score, habitat=r["sub"]["habitat"] + fixed_score,
                rancher=r["sub"]["rancher"], hunter=r["sub"]["hunter"],
                recreationist=r["sub"]["recreationist"], fire=fire,
                fire_score=r["sub"].get("fire", 0.0),
            ))
    return results


# ======================================================================
# 3. HEADLINE METRICS
# ======================================================================

def metrics(results):
    """Summarize one parameter set: exchange ratios, portfolio composition, and
    whether each headline finding holds.

    Exchange ratios are community points gained per T&E point lost at $20M,
    measured against the Balanced scenario. The asymmetry ratio compares T&E
    lost when weight shifts to community objectives with T&E gained when weight
    shifts to conservation.
    """
    df = pd.DataFrame([{k: v for k, v in r.items() if k != "choices"} for r in results])
    ch = {(r["scenario"], r["budget"]): r["choices"] for r in results}
    at20 = df[df.budget == B20].set_index("scenario")
    delta = {s: at20.loc[s, SUBOBJ] - at20.loc["S1", SUBOBJ] for s in at20.index}

    m = {"n_infeasible": len(SCENARIOS) * len(BUDGETS) - len(results)}

    gain = delta["S2"]["te"]
    m["asym_ratio"] = -delta["S5"]["te"] / gain if gain > 1e-9 else np.inf
    m["asym_holds"] = m["asym_ratio"] > 1

    def exchange(scenario, key):
        loss = -delta[scenario]["te"]
        gained = delta[scenario][key]
        if loss <= 1e-9:
            return np.inf if gained > 0 else np.nan
        return gained / loss

    m["eff_S6_rancher"] = exchange("S6", "rancher")
    m["eff_S5_rancher"] = exchange("S5", "rancher")
    m["eff_S7_hunter"] = exchange("S7", "hunter")
    # When Rancher-Conservation gives up no T&E score relative to Balanced, its exchange
    # ratio is undefined (inf or nan). Community Priority cannot then be the cheaper route to
    # rancher score, so the finding holds; it fails only when both ratios exist and S5 wins.
    s6_measured = np.isfinite(m["eff_S6_rancher"])
    m["S6_beats_S5"] = (not s6_measured) or m["eff_S6_rancher"] > m["eff_S5_rancher"]
    m["hunter_weaker_than_rancher"] = (not s6_measured) or m["eff_S7_hunter"] < m["eff_S6_rancher"]

    counts6 = np.bincount(ch[("S6", B20)], minlength=N_ALTS)
    m["S6_alt1_count"] = int(counts6[0])
    m["S6_alt1_modal"] = counts6[0] == counts6.max()

    m["S6_rec_change"] = delta["S6"]["recreationist"]
    m["S2_rec_change"] = delta["S2"]["recreationist"]

    m["S2_S3_S4_identical"] = bool((ch[("S2", B20)] == ch[("S3", B20)]).all()
                                   and (ch[("S2", B20)] == ch[("S4", B20)]).all())

    # Budget binding: conservation weighting spends nearly all of every budget,
    # community weighting does not exhaust the largest one.
    s2 = df[df.scenario == "S2"]
    m["S2_min_spend_share"] = float((s2.total_cost / s2.budget).min())
    s5_60 = df[(df.scenario == "S5") & (df.budget == 60_000_000)]
    m["S5_spend_share_60M"] = float(s5_60.total_cost.iloc[0] / 60e6) if len(s5_60) else np.nan
    m["budget_asym_holds"] = (m["S2_min_spend_share"] >= 0.95
                              and m["S5_spend_share_60M"] <= 0.90)

    used = np.unique(np.concatenate([r["choices"] for r in results]))
    m["alts_8_9_never"] = not any(a in used for a in (7, 8))
    m["alts_used"] = ";".join(str(a + 1) for a in used)
    m["n_budgets_roadside"] = int(sum(bool(r["roadside_built"]) for r in results
                                      if r["scenario"] == "S1"))
    m["roadside_at_20M"] = bool([r["roadside_built"] for r in results
                                 if r["scenario"] == "S1" and r["budget"] == B20][0])

    # Portfolio difference between scenarios at one budget, against the
    # difference within a scenario across budgets.
    sids = list(SCENARIOS)
    m["hamming_between_scen_20M"] = float(np.mean(
        [(ch[(a, B20)] != ch[(b, B20)]).sum() for a, b in itertools.combinations(sids, 2)]))
    m["hamming_within_10v40"] = float(np.mean(
        [(ch[(s, 10_000_000)] != ch[(s, 40_000_000)]).sum() for s in sids]))
    m["budget_beats_weights"] = m["hamming_within_10v40"] > m["hamming_between_scen_20M"]

    for s in sids:
        for budget in BUDGETS:
            row = df[(df.scenario == s) & (df.budget == budget)]
            tag = f"{s}_{int(budget / 1e6)}"
            m[f"te_{tag}"] = float(row.te.iloc[0]) if len(row) else np.nan
            m[f"rancher_{tag}"] = float(row.rancher.iloc[0]) if len(row) else np.nan

    for s in ["S1", "S2", "S5", "S6", "S7"]:
        m[f"choices_{s}_20"] = ",".join(str(a + 1) for a in ch[(s, B20)])
    return m


def feedback_metrics(results, m):
    """Portfolio composition at $20M, used by the fire feedback analysis."""
    ch = {(r["scenario"], r["budget"]): r["choices"] for r in results}
    df = pd.DataFrame([{k: v for k, v in r.items() if k != "choices"} for r in results])
    for s in ["S1", "S2", "S5", "S6", "S7"]:
        if (s, B20) not in ch:
            continue
        counts = np.bincount(ch[(s, B20)], minlength=N_ALTS)
        m[f"{s}_n_removal"] = int(counts[CATTLE_REMOVAL_ALTS].sum())
        m[f"{s}_n_alt7"] = int(counts[6])
        m[f"{s}_n_alt1"] = int(counts[0])
        m[f"{s}_n_alt11"] = int(counts[10])
        m[f"{s}_n_alt3"] = int(counts[2])
        row = df[(df.scenario == s) & (df.budget == B20)]
        m[f"{s}_fire"] = float(row.fire.iloc[0])
    return m


# ======================================================================
# 4. PERTURBATION DESIGNS
# ======================================================================

# Perturbation sizes. A one-point shift spans 12 to 33% of the range of each
# score scale; multipliers, costs, and fire effects move by comparable amounts.
MULT_STEP = 0.5        # fraction by which a zone multiplier is raised or lowered
COST_STEP = 0.3
FUELBREAK_RANGE = (0.25, 0.75)
ROADSIDE_RANGE = (0.10, 0.30)
COST_RANGE = (0.7, 1.3)
CATTLE_RANGE = (0.0, 1.0)      # proportional increase in fire probability
ACCESS_RANGE = (0.0, 0.5)

MC_DESIGNS = [
    ("conservation_only", ["conservation"], 1.0, 0.5),
    ("community_only", ["community"], 1.0, 0.5),
    ("fire_cost_only", ["fire_cost"], 1.0, 0.5),
    ("joint_pm1", ["conservation", "community", "fire_cost"], 1.0, 1.0),
    ("joint_pm2", ["conservation", "community", "fire_cost"], 2.0, 0.5),
]


def draw_params(rng, sources, width=1.0):
    """One random parameter set. Sources select which inputs move: the elicited
    conservation benefits, the community scores and multipliers, or the fire
    effects and costs. width scales the score and multiplier ranges."""
    p = default_params()
    if "conservation" in sources:
        p["direct"] = p["direct"] + rng.uniform(-width, width, N_ALTS)
    if "community" in sources:
        for key in ("base_rec", "base_hunt", "base_ranch"):
            shift = rng.uniform(-width, width, N_ALTS)
            shift[10] = 0.0        # the no-change alternative anchors the scale at zero
            p[key] = p[key] + shift
        for key in ("mult_rec", "mult_hunt", "mult_ranch"):
            p[key] = {z: v * rng.uniform(1 - MULT_STEP * width, 1 + MULT_STEP * width)
                      for z, v in p[key].items()}
    if "fire_cost" in sources:
        p["fuelbreak"] = rng.uniform(*FUELBREAK_RANGE)
        p["roadside"] = rng.uniform(*ROADSIDE_RANGE)
        p["cost_mult"] = rng.uniform(*COST_RANGE, N_ALTS)
        p["roadside_cost_mult"] = rng.uniform(*COST_RANGE)
    return p


def oat_designs():
    """Every one-at-a-time perturbation, as (label, parameter set) pairs."""
    alts = [f"A{j + 1}" for j in range(N_ALTS)]
    jobs = []
    score_keys = {"direct": "Conservation benefit", "base_rec": "Recreationist score",
                  "base_hunt": "Hunter score", "base_ranch": "Rancher score"}
    for key, label in score_keys.items():
        for j in range(N_ALTS):
            if key != "direct" and j == 10:
                continue           # community scale anchor stays at zero
            for sign in (-1, 1):
                p = default_params()
                p[key] = p[key].copy()
                p[key][j] += sign
                jobs.append((f"{label}|{alts[j]}|{sign:+d}", p))

    for key, label in (("mult_rec", "Recreationist multiplier"),
                       ("mult_hunt", "Hunter multiplier"),
                       ("mult_ranch", "Rancher multiplier")):
        for zone in ZONES:
            for factor, sign in ((1 - MULT_STEP, -1), (1 + MULT_STEP, 1)):
                p = default_params()
                p[key] = dict(p[key])
                p[key][zone] *= factor
                jobs.append((f"{label}|{zone}|{sign:+d}", p))

    for value_, sign in ((FUELBREAK_RANGE[0], -1), (FUELBREAK_RANGE[1], 1)):
        p = default_params()
        p["fuelbreak"] = value_
        jobs.append((f"Fuelbreak effect|50%|{sign:+d}", p))
    for value_, sign in ((ROADSIDE_RANGE[0], -1), (ROADSIDE_RANGE[1], 1)):
        p = default_params()
        p["roadside"] = value_
        jobs.append((f"Roadside effect|20%|{sign:+d}", p))

    for j in range(N_ALTS):
        if j in (ROADSIDE_ALT, 10):
            continue               # no per-paddock cost to perturb
        for factor, sign in ((1 - COST_STEP, -1), (1 + COST_STEP, 1)):
            p = default_params()
            p["cost_mult"] = np.ones(N_ALTS)
            p["cost_mult"][j] = factor
            jobs.append((f"Cost|{alts[j]}|{sign:+d}", p))

    for factor, sign in ((1 - COST_STEP, -1), (1 + COST_STEP, 1)):
        p = default_params()
        p["roadside_cost_mult"] = factor
        jobs.append((f"Cost|Roadside|{sign:+d}", p))
    return jobs


# Fire weights swept when fire risk is treated as its own objective.
FIRE_WEIGHT_SWEEP = np.round(np.arange(0, 1.0001, 0.05), 3)

# Taper in the roadside benefit, swept in the decay stage.
DECAY_SWEEP = np.round(np.arange(0, 1.0001, 0.05), 3)
DECAY_THRESHOLD_POINTS = [0.0, 0.5, 1.0]

# Fire feedback sweep grids.
CATTLE_SWEEP = np.round(np.arange(CATTLE_RANGE[0], CATTLE_RANGE[1] + 1e-9, 0.05), 3)
ACCESS_SWEEP = np.round(np.arange(ACCESS_RANGE[0], ACCESS_RANGE[1] + 1e-9, 0.025), 3)
CATTLE_GRID = np.round(np.arange(CATTLE_RANGE[0], CATTLE_RANGE[1] + 1e-9, 0.1), 3)
ACCESS_GRID = np.round(np.arange(ACCESS_RANGE[0], ACCESS_RANGE[1] + 1e-9, 0.05), 3)


# ======================================================================
# 5. PARALLEL WORKERS
# ======================================================================

_DATA = None   # set once per worker process


def _init_worker(filepath):
    global _DATA
    _DATA = load_data(filepath)


def _job_oat(args):
    label, p = args
    m = metrics(run_grid(_DATA, p))
    m["param"] = label
    return m


def _job_mc(args):
    seed, sources, width, label = args
    rng = np.random.default_rng(seed)
    m = metrics(run_grid(_DATA, draw_params(rng, sources, width)))
    m.update(run=label, seed=seed)
    return m


def _job_decay(args):
    """One value of the roadside taper, all scenarios and budgets."""
    decay = float(args)
    p = default_params()
    p["roadside_decay"] = decay
    res = run_grid(_DATA, p)
    rows = []
    for r in res:
        counts = np.bincount(r["choices"], minlength=N_ALTS)
        rows.append(dict(roadside_decay=decay, scenario=r["scenario"], budget=r["budget"],
                         roadside_built=bool(r["roadside_built"]), total_cost=r["total_cost"],
                         fire_reduction=r["fire"], **{k: r[k] for k in SUBOBJ},
                         n_alt1=int(counts[0]), n_alt3=int(counts[2]), n_alt4=int(counts[3]),
                         n_alt7=int(counts[6]), n_alt10=int(counts[9]), n_alt11=int(counts[10])))
    m = metrics(res)
    for row in rows:
        row.update(asym_ratio=m["asym_ratio"], eff_S6_rancher=m["eff_S6_rancher"],
                   eff_S5_rancher=m["eff_S5_rancher"], eff_S7_hunter=m["eff_S7_hunter"],
                   S6_alt1_count=m["S6_alt1_count"])
    return rows


def _job_decay_threshold(args):
    """Fire-objective weight sweep at one taper value, for the build threshold."""
    decay, fire_weight = args
    p = default_params()
    p["roadside_decay"] = float(decay)
    rows = []
    for sid, (label, eco, eco_split, soc_split) in SCENARIOS.items():
        w = weights_with_fire(eco, eco_split, soc_split, float(fire_weight))
        for r in run_grid(_DATA, p, weights_override={sid: w}):
            rows.append(dict(roadside_decay=float(decay), fire_weight=float(fire_weight),
                             scenario=sid, budget=r["budget"],
                             roadside_built=bool(r["roadside_built"])))
    return rows


def _job_landscape(args):
    """One fire weight, all scenarios and budgets, recording whether the
    roadside fuelbreak is built."""
    fire_weight = float(args)
    p = default_params()
    rows = []
    for sid, (label, eco, eco_split, soc_split) in SCENARIOS.items():
        w = weights_with_fire(eco, eco_split, soc_split, fire_weight)
        for r in run_grid(_DATA, p, weights_override={sid: w}):
            counts = np.bincount(r["choices"], minlength=N_ALTS)
            rows.append(dict(fire_weight=fire_weight, scenario=sid, budget=r["budget"],
                             roadside_built=bool(r["roadside_built"]),
                             total_cost=r["total_cost"],
                             fire_reduction=r["fire"], fire_score=r["fire_score"],
                             **{k: r[k] for k in SUBOBJ},
                             n_alt1=int(counts[0]), n_alt3=int(counts[2]),
                             n_alt4=int(counts[3]), n_alt7=int(counts[6]),
                             n_alt10=int(counts[9]), n_alt11=int(counts[10]),
                             n_removal=int(counts[CATTLE_REMOVAL_ALTS].sum())))
    return rows


def _job_feedback_sweep(args):
    kind, v = args
    p = default_params()
    p[kind] = float(v)
    results = run_grid(_DATA, p)
    m = feedback_metrics(results, metrics(results))
    m.update(sweep=kind, value=float(v))
    return m


def _job_feedback_grid(args):
    cattle, access = args
    p = default_params()
    p["cattle_penalty"], p["hunter_penalty"] = float(cattle), float(access)
    results = run_grid(_DATA, p, budgets=[10_000_000, B20, 40_000_000])
    m = feedback_metrics(results, {})
    at20 = pd.DataFrame([{k: v for k, v in r.items() if k != "choices"} for r in results])
    at20 = at20[at20.budget == B20].set_index("scenario")
    d6 = at20.loc["S6", SUBOBJ] - at20.loc["S1", SUBOBJ]
    d5 = at20.loc["S5", SUBOBJ] - at20.loc["S1", SUBOBJ]
    d2 = at20.loc["S2", SUBOBJ] - at20.loc["S1", SUBOBJ]
    m["eff_S6_rancher"] = d6["rancher"] / -d6["te"] if d6["te"] < 0 else np.inf
    m["eff_S5_rancher"] = d5["rancher"] / -d5["te"] if d5["te"] < 0 else np.inf
    m["asym_ratio"] = -d5["te"] / d2["te"] if d2["te"] > 1e-9 else np.inf
    m.update(cattle_penalty=float(cattle), hunter_penalty=float(access))
    return m


def _job_feedback_mc(args):
    seed = args
    rng = np.random.default_rng(seed)
    p = draw_params(rng, ["conservation", "community", "fire_cost"], 1.0)
    p["cattle_penalty"] = float(rng.uniform(*CATTLE_RANGE))
    p["hunter_penalty"] = float(rng.uniform(*ACCESS_RANGE))
    results = run_grid(_DATA, p)
    m = feedback_metrics(results, metrics(results))
    m.update(run="joint_with_feedbacks", seed=seed,
             cattle_penalty=p["cattle_penalty"], hunter_penalty=p["hunter_penalty"])
    return m


# ======================================================================
# 6. ANALYSIS STAGES
# ======================================================================

def weight_sweep(d):
    """Continuous ecological weight at every budget, and an ecological weight by
    rancher share grid at $20M with the rest of the social weight split evenly."""
    rows = []
    for eco in np.round(np.arange(0, 1.0001, 0.05), 2):
        w = effective_weights(eco, (0.5, 0.5), (0.33, 0.33, 0.34))
        for r in run_grid(d, default_params(), weights_override={f"eco{eco}": w}):
            rows.append(dict(eco_weight=eco, rancher_share=0.33, grid=np.nan,
                             budget=r["budget"], total_cost=r["total_cost"],
                             **{k: r[k] for k in SUBOBJ},
                             n_alt1=int((r["choices"] == 0).sum()),
                             n_alt3=int((r["choices"] == 2).sum()),
                             n_alt7=int((r["choices"] == 6).sum())))
    for eco in np.round(np.arange(0, 1.0001, 0.1), 2):
        for share in np.round(np.arange(0, 1.0001, 0.1), 2):
            rest = (1 - share) / 2
            w = effective_weights(eco, (0.5, 0.5), (share, rest, rest))
            for r in run_grid(d, default_params(), weights_override={"w": w}, budgets=[B20]):
                rows.append(dict(eco_weight=eco, rancher_share=share, grid=True,
                                 budget=r["budget"], total_cost=r["total_cost"],
                                 **{k: r[k] for k in SUBOBJ},
                                 n_alt1=int((r["choices"] == 0).sum()),
                                 n_alt3=int((r["choices"] == 2).sum()),
                                 n_alt7=int((r["choices"] == 6).sum())))
    return pd.DataFrame(rows)


def stage_sensitivity(filepath, out, draws, pool):
    """Baseline metrics, weight sweeps, one-at-a-time, and Monte Carlo."""
    d = load_data(filepath)

    base = metrics(run_grid(d, default_params()))
    base["run"] = "baseline"
    pd.DataFrame([base]).to_csv(f"{out}/sa_baseline_metrics.csv", index=False)

    weight_sweep(d).to_csv(f"{out}/sa_weight_sweep.csv", index=False)

    pd.DataFrame(pool.map(_job_oat, oat_designs())).to_csv(f"{out}/sa_oat.csv", index=False)

    seed, rows = 1000, []
    for label, sources, width, frac in MC_DESIGNS:
        n = max(1, int(round(draws * frac)))
        rows += pool.map(_job_mc, [(seed + i, sources, width, label) for i in range(n)],
                         chunksize=4)
        seed += n
        pd.DataFrame(rows).to_csv(f"{out}/sa_montecarlo.csv", index=False)


def stage_landscape(filepath, out, pool):
    """Sweep the weight on fire risk as a standalone objective, to find where a
    landscape-scale action becomes worth building."""
    rows = []
    for chunk in pool.map(_job_landscape, FIRE_WEIGHT_SWEEP):
        rows += chunk
    pd.DataFrame(rows).to_csv(f"{out}/la_fire_objective.csv", index=False)


def stage_decay(filepath, out, pool):
    """Sweep the taper in the roadside benefit with distance from the highway."""
    rows = []
    for chunk in pool.map(_job_decay, DECAY_SWEEP):
        rows += chunk
    pd.DataFrame(rows).to_csv(f"{out}/rd_decay_sweep.csv", index=False)

    jobs = [(dv, w) for dv in DECAY_THRESHOLD_POINTS for w in FIRE_WEIGHT_SWEEP]
    rows = []
    for chunk in pool.map(_job_decay_threshold, jobs):
        rows += chunk
    pd.DataFrame(rows).to_csv(f"{out}/rd_decay_thresholds.csv", index=False)


def stage_feedbacks(filepath, out, draws, pool):
    """Fire feedback sweeps, the two-way grid, and a Monte Carlo that adds the
    feedbacks to a joint perturbation of the elicited inputs."""
    sweep_jobs = ([("cattle_penalty", v) for v in CATTLE_SWEEP]
                  + [("hunter_penalty", v) for v in ACCESS_SWEEP])
    pd.DataFrame(pool.map(_job_feedback_sweep, sweep_jobs)).to_csv(
        f"{out}/ff_sweeps.csv", index=False)

    grid_jobs = [(c, a) for c in CATTLE_GRID for a in ACCESS_GRID]
    pd.DataFrame(pool.map(_job_feedback_grid, grid_jobs)).to_csv(
        f"{out}/ff_grid.csv", index=False)

    n = max(1, int(round(draws * 0.8)))
    pd.DataFrame(pool.map(_job_feedback_mc, [5000 + i for i in range(n)], chunksize=4)).to_csv(
        f"{out}/ff_montecarlo.csv", index=False)


# ======================================================================
# 7. FIGURES AND SUMMARY TABLES
# ======================================================================

INK, INK2, GRID_GREY = "#0b0b0b", "#52514e", "#e4e3df"

SCENARIO_STYLE = {   # label, color, marker, line style
    "S1": ("Balanced", "#3a3a3a", "o", "-"),
    "S2": ("Conservation Priority", "#0072B2", "s", "-"),
    "S5": ("Community Priority", "#D55E00", "^", "--"),
    "S6": ("Rancher-Conservation", "#E69F00", "v", "-."),
    "S7": ("Hunter-Recreationist", "#CC79A7", "X", ":"),
}
DESIGN_LABELS = [("conservation_only", "Conservation\nbenefit"),
                 ("community_only", "Community\nscores"),
                 ("fire_cost_only", "Fire effect\n& cost"),
                 ("joint_pm1", "All inputs\n(±1)"),
                 ("joint_pm2", "All inputs\n(±2)")]
FINDINGS = [
    ("asym_holds", "Tradeoff asymmetry (T&E lost under\nCommunity > T&E gained under Conservation)"),
    ("S6_beats_S5", "Community Priority never the cheaper\nroute to rancher score"),
    ("hunter_weaker_than_rancher", "Hunter alignment weaker\nthan rancher alignment"),
    ("S6_alt1_modal", "Alt 1 is the most common action\nunder Rancher-Conservation"),
    ("budget_beats_weights", "Budget changes portfolios more\nthan weights do"),
    ("budget_asym_holds", "Conservation spends ≥95% of budget;\nCommunity leaves ≥10% unspent at $60M"),
    ("S2_S3_S4_identical", "Three conservation scenarios\nidentical at $20M"),
    ("alts_8_9_never", "Alts 8 and 9 never selected"),
]
FEEDBACK_CATS = [("Full restoration (Alt 7)", "#08306b"),     # same colors as the Figure 5 heatmap
                 ("Other cattle or ungulate removal (Alts 4, 5, 6, 9)", "#4292c6"),
                 ("Fence and fuelbreaks (Alt 1)", "#9ecae1"),
                 ("No change (Alt 11)", "#e6e6e6"),
                 ("Other", "#fdd0a2")]
RATIO_SERIES = [("eff_S6_rancher", "S6", "Rancher-Conservation\n(rancher pts / T&E pt)"),
                ("eff_S5_rancher", "S5", "Community Priority\n(rancher pts / T&E pt)"),
                ("eff_S7_hunter", "S7", "Hunter-Recreationist\n(hunter pts / T&E pt)")]


def _set_style():
    plt.rcParams.update({
        "font.family": "sans-serif", "font.size": 10, "axes.titlesize": 11,
        "axes.labelsize": 10, "xtick.labelsize": 9, "ytick.labelsize": 9,
        "legend.fontsize": 9, "figure.dpi": 300, "savefig.dpi": 300,
        "savefig.bbox": "tight", "axes.spines.top": False, "axes.spines.right": False,
        "axes.edgecolor": INK2, "axes.labelcolor": INK,
        "xtick.color": INK2, "ytick.color": INK2,
    })


def _panel(ax, letter, x=-0.14):
    ax.text(x, 1.04, letter, transform=ax.transAxes, fontsize=12, fontweight="bold",
            va="bottom")


def _save(fig, path):
    fig.savefig(path + ".png")
    fig.savefig(path + ".pdf")
    plt.close(fig)


def table_robustness(out, base, oat, mc, designs):
    """Percentage of runs in which each finding holds, plus ratio distributions."""
    rows = []
    for key, label in FINDINGS:
        row = {"finding": label.replace("\n", " "), "baseline": bool(base[key]),
               "one_at_a_time": 100 * oat[key].astype(bool).mean()}
        for design, dlabel in designs:
            row[dlabel.replace("\n", " ")] = 100 * mc[mc.run == design][key].astype(bool).mean()
        rows.append(row)
    for key, label in (("asym_ratio", "Asymmetry ratio"),
                       ("eff_S6_rancher", "S6 rancher pts per T&E pt lost"),
                       ("eff_S5_rancher", "S5 rancher pts per T&E pt lost"),
                       ("eff_S7_hunter", "S7 hunter pts per T&E pt lost"),
                       ("S6_alt1_count", "Alt 1 paddocks under S6 at $20M")):
        finite = oat[key].replace(np.inf, np.nan)
        row = {"finding": label + " [median (5th to 95th)]",
               "baseline": round(float(base[key]), 2),
               "one_at_a_time": f"{finite.min():.2f} to {finite.max():.2f}"}
        for design, dlabel in designs:
            v = mc[mc.run == design][key].replace(np.inf, np.nan).dropna()
            row[dlabel.replace("\n", " ")] = (
                f"{v.median():.2f} ({v.quantile(.05):.2f} to {v.quantile(.95):.2f})")
        rows.append(row)
    tab = pd.DataFrame(rows)
    tab.to_csv(f"{out}/TableS2_robustness_summary.csv", index=False)
    return tab


def table_paddock_stability(out, base, joint):
    """How often each paddock keeps its baseline alternative across draws."""
    rows = []
    for s in ["S2", "S6", "S5"]:
        baseline = np.array(base[f"choices_{s}_20"].split(","), dtype=int)
        draws = np.array([np.array(x.split(","), dtype=int) for x in joint[f"choices_{s}_20"]])
        for i in range(N_PADDOCKS):
            vals, counts = np.unique(draws[:, i], return_counts=True)
            rows.append({"scenario": SCENARIO_STYLE[s][0], "paddock": i + 1,
                         "baseline_alt": baseline[i],
                         "pct_draws_same_alt": 100 * (draws[:, i] == baseline[i]).mean(),
                         "most_common_alt": vals[counts.argmax()],
                         "pct_draws_alt7": 100 * (draws[:, i] == 7).mean()})
    df = pd.DataFrame(rows)
    df.to_csv(f"{out}/TableS4_paddock_stability_20M.csv", index=False)
    return df


def figure_montecarlo(out, base, mc, designs):
    """Exchange ratio distributions and the share of draws supporting each finding."""
    fig = plt.figure(figsize=(11, 5.2))
    gs = fig.add_gridspec(1, 2, width_ratios=[1.0, 1.25], wspace=0.55)

    ax = fig.add_subplot(gs[0])
    for k, (key, sid, label) in enumerate(RATIO_SERIES):
        for di, (design, _) in enumerate(designs):
            v = mc[mc.run == design][key].replace(np.inf, np.nan).dropna()
            y = di + (k - 1) * 0.24
            q5, q25, q50, q75, q95 = v.quantile([.05, .25, .5, .75, .95])
            ax.plot([q5, q95], [y, y], color=SCENARIO_STYLE[sid][1], lw=1.2,
                    solid_capstyle="round")
            ax.plot([q25, q75], [y, y], color=SCENARIO_STYLE[sid][1], lw=4,
                    solid_capstyle="round")
            ax.plot(q50, y, marker=SCENARIO_STYLE[sid][2], ms=7, mfc="white",
                    mec=SCENARIO_STYLE[sid][1], mew=1.6, ls="none",
                    label=label if di == 0 else None)
        ax.axvline(base[key], color=SCENARIO_STYLE[sid][1], lw=0.8,
                   ls=SCENARIO_STYLE[sid][3], alpha=0.8)
    ax.set_xscale("log")
    ax.set_xticks([0.2, 0.5, 1, 2, 5, 10, 20])
    ax.set_xticklabels(["0.2", "0.5", "1", "2", "5", "10", "20"])
    ax.set_yticks(range(len(designs)))
    ax.set_yticklabels([d for _, d in designs])
    ax.invert_yaxis()
    ax.set_xlabel("Community points gained per T&E point lost at $20M (log scale)")
    ax.grid(axis="x", color=GRID_GREY, lw=0.6)
    ax.set_axisbelow(True)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=1, frameon=False)
    ax.set_title("Exchange ratios under perturbation", loc="left", color=INK)
    _panel(ax, "A")

    ax = fig.add_subplot(gs[1])
    M = np.array([[100 * mc[mc.run == design][key].astype(bool).mean()
                   for design, _ in designs] for key, _ in FINDINGS])
    im = ax.imshow(M, cmap="Blues", vmin=0, vmax=100, aspect="auto")
    for i in range(M.shape[0]):
        for j in range(M.shape[1]):
            ax.text(j, i, f"{M[i, j]:.0f}", ha="center", va="center", fontsize=9,
                    color="white" if M[i, j] > 60 else INK)
    ax.set_xticks(range(len(designs)))
    ax.set_xticklabels([d for _, d in designs], fontsize=8)
    ax.set_yticks(range(len(FINDINGS)))
    ax.set_yticklabels([lab for _, lab in FINDINGS], fontsize=8)
    ax.tick_params(length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_title("% of draws in which each finding holds", loc="left", color=INK)
    cb = fig.colorbar(im, ax=ax, fraction=0.04, pad=0.02)
    cb.set_label("% of draws", fontsize=8)
    cb.ax.tick_params(labelsize=8)
    _panel(ax, "B")
    _save(fig, f"{out}/FigS3_montecarlo_robustness")


def figure_budget_bands(out, base, joint):
    """Scores across budgets with uncertainty bands from the joint draws."""
    budgets = [int(b / 1e6) for b in BUDGETS]
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2), sharex=True)
    for ax, var, ylab, letter in ((axes[0], "te", "Total T&E score", "A"),
                                  (axes[1], "rancher", "Total rancher score", "B")):
        for sid, (label, color, marker, ls) in SCENARIO_STYLE.items():
            q = np.array([joint[f"{var}_{sid}_{b}"].quantile([.05, .5, .95]).values
                          for b in budgets])
            ax.fill_between(budgets, q[:, 0], q[:, 2], color=color, alpha=0.13, lw=0)
            ax.plot(budgets, [base[f"{var}_{sid}_{b}"] for b in budgets], color=color,
                    ls=ls, lw=2, marker=marker, ms=6, mfc="white", mec=color, mew=1.4,
                    label=label)
        ax.set_xlabel("Budget ($ million)")
        ax.set_ylabel(ylab)
        ax.set_xticks(budgets)
        ax.grid(axis="y", color=GRID_GREY, lw=0.6)
        ax.set_axisbelow(True)
        _panel(ax, letter)
    axes[0].legend(frameon=False, loc="upper left")
    fig.tight_layout()
    _save(fig, f"{out}/FigS4_budget_scores_uncertainty")


def figure_weight_sweep(out, ws):
    """T&E score against ecological weight, and where fence and fuelbreaks win."""
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.3), gridspec_kw={"width_ratios": [1, 1.05]})
    line = ws[ws["grid"].isna()]
    blues = ["#9ec5f4", "#5c9ee8", "#2a78d6", "#1b5aa6", "#0d3a73"]
    markers = ["o", "s", "^", "D", "v"]

    ax = axes[0]
    for k, budget in enumerate(sorted(line.budget.unique())):
        dd = line[line.budget == budget].sort_values("eco_weight")
        ax.plot(dd.eco_weight, dd.te, color=blues[k], lw=2, marker=markers[k], ms=4,
                markevery=2, label=f"${budget / 1e6:.0f}M")
    for sid, x in (("S5", 0.2), ("S1", 0.5), ("S2", 0.8)):
        ax.axvline(x, color=INK2, lw=0.7, ls=":")
        ax.text(x, 21.2, sid, ha="center", fontsize=8, color=INK2,
                bbox=dict(fc="white", ec="none", pad=1))
    ax.set_ylim(0, 22)
    ax.set_xlabel("Weight on ecological objective")
    ax.set_ylabel("Total T&E score")
    ax.legend(title="Budget", frameon=False, loc="center right", fontsize=8, title_fontsize=8)
    ax.grid(axis="y", color=GRID_GREY, lw=0.6)
    ax.set_axisbelow(True)
    _panel(ax, "A")

    ax = axes[1]
    grid = ws[ws["grid"] == True]
    piv = grid.pivot(index="eco_weight", columns="rancher_share",
                     values="n_alt1").sort_index(ascending=False)
    im = ax.imshow(piv.values, cmap="Purples", vmin=0, vmax=21, aspect="auto")
    for i in range(piv.shape[0]):
        for j in range(piv.shape[1]):
            v = piv.values[i, j]
            ax.text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=7,
                    color="white" if v > 11 else INK)
    ax.set_xticks(range(piv.shape[1]))
    ax.set_xticklabels([f"{x:.1f}" for x in piv.columns], fontsize=8)
    ax.set_yticks(range(piv.shape[0]))
    ax.set_yticklabels([f"{x:.1f}" for x in piv.index], fontsize=8)
    ax.set_xlabel("Rancher share of social weight")
    ax.set_ylabel("Weight on ecological objective")
    ypos = {round(v, 1): i for i, v in enumerate(piv.index)}
    xpos = {round(v, 1): i for i, v in enumerate(piv.columns)}
    for sid, (eco, share) in {"S1": (0.5, 0.3), "S6": (0.5, 0.7),
                              "S5": (0.2, 0.3), "S2": (0.8, 0.3)}.items():
        ax.add_patch(plt.Rectangle((xpos[share] - 0.5, ypos[eco] - 0.5), 1, 1,
                                   fill=False, ec=INK, lw=1.4))
        ax.text(xpos[share] + 0.52, ypos[eco] - 0.52, sid, fontsize=7, color=INK,
                ha="left", va="bottom", fontweight="bold")
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(length=0)
    ax.set_title("Paddocks assigned Alt 1 (fence + fuelbreaks) at $20M", loc="left",
                 fontsize=10, color=INK)
    cb = fig.colorbar(im, ax=ax, fraction=0.04, pad=0.02)
    cb.ax.tick_params(labelsize=8)
    _panel(ax, "B")
    fig.tight_layout()
    _save(fig, f"{out}/FigS5_weight_sweep")


def figure_tornado(out, base, oat):
    """The inputs that move the two headline ratios most, one at a time."""
    oat = oat.copy()
    oat[["group", "item", "direction"]] = oat.param.str.split("|", expand=True)
    oat["label"] = oat.group + ": " + oat.item
    fig, axes = plt.subplots(1, 2, figsize=(11, 5.2))
    for ax, key, xlab, letter in (
            (axes[0], "eff_S6_rancher", "Rancher-Conservation exchange ratio", "A"),
            (axes[1], "asym_ratio", "Asymmetry ratio", "B")):
        b0 = base[key]
        t = oat.pivot_table(index="label", columns="direction", values=key, aggfunc="first")
        t["range"] = (t.max(axis=1) - t.min(axis=1)).abs()
        t = t.sort_values("range", ascending=False).head(12).iloc[::-1]
        for i, (_, row) in enumerate(t.iterrows()):
            for col, color, offset in (("-1", "#eb6834", -0.2), ("+1", "#2a78d6", 0.2)):
                if col in row and pd.notna(row[col]):
                    ax.barh(i + offset, min(row[col], 12) - b0, left=b0, height=0.36,
                            color=color, edgecolor="black", lw=0.4)
                    if row[col] > 12:
                        ax.text(12.1, i + offset, f"{row[col]:.0f}", va="center",
                                fontsize=7, color=INK2)
        ax.axvline(b0, color=INK, lw=1)
        ax.axvline(1, color=INK2, lw=0.8, ls="--")
        ax.set_yticks(range(len(t)))
        ax.set_yticklabels(t.index, fontsize=8)
        ax.set_xlabel(xlab)
        ax.grid(axis="x", color=GRID_GREY, lw=0.6)
        ax.set_axisbelow(True)
        _panel(ax, letter)
    fig.legend(handles=[Patch(fc="#eb6834", ec="black", lw=0.4, label="Input lowered"),
                        Patch(fc="#2a78d6", ec="black", lw=0.4, label="Input raised")],
               frameon=False, loc="upper center", bbox_to_anchor=(0.5, 0.02), ncol=2,
               fontsize=9)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    _save(fig, f"{out}/FigS6_oat_tornado")


def figure_fire_feedbacks(out, sweeps):
    """Portfolio composition and exchange ratios along each feedback sweep."""
    fig, axes = plt.subplots(2, 2, figsize=(11.5, 7.6))
    panels = [("cattle_penalty", "Fire probability increase where cattle removed"),
              ("hunter_penalty", "Fire probability increase where access open")]

    for col, (kind, xlab) in enumerate(panels):
        d = sweeps[sweeps.sweep == kind].sort_values("value")
        x = d.value.values * 100
        comp = np.vstack([d.S2_n_alt7.values,
                          (d.S2_n_removal - d.S2_n_alt7).values,
                          d.S2_n_alt1.values,
                          d.S2_n_alt11.values])
        comp = np.vstack([comp, N_PADDOCKS - comp.sum(axis=0)])

        ax = axes[0, col]
        bottom = np.zeros(len(x))
        for k, (label, color) in enumerate(FEEDBACK_CATS):
            ax.bar(x, comp[k], bottom=bottom, width=(x[1] - x[0]) * 0.85, color=color,
                   edgecolor="white", linewidth=0.6, label=label if col == 0 else None)
            bottom += comp[k]
        ax.set_ylim(0, N_PADDOCKS + 0.5)
        ax.set_xlabel(xlab + " (%)")
        ax.set_ylabel(f"Paddocks (of {N_PADDOCKS})")
        ax.set_title("Conservation Priority portfolio at $20M", loc="left", color=INK)
        _panel(ax, "A" if col == 0 else "B", x=-0.19)

        ax = axes[1, col]
        for key, sid, _ in RATIO_SERIES:
            label, color, marker, ls = SCENARIO_STYLE[sid]
            ax.plot(x, np.clip(d[key].values, None, 12), color=color, ls=ls, lw=2,
                    marker=marker, ms=5, mfc="white", mec=color, mew=1.3,
                    label=label if col == 0 else None)
        ax.axhline(1, color=INK2, lw=0.9, ls="--")
        ax.set_ylim(0, 12.5)
        ax.set_xlabel(xlab + " (%)")
        ax.set_ylabel("Community pts per T&E pt lost")
        ax.grid(axis="y", color=GRID_GREY, lw=0.6)
        ax.set_axisbelow(True)
        ax.set_title("Exchange ratios at $20M", loc="left", color=INK)
        _panel(ax, "C" if col == 0 else "D", x=-0.19)

    axes[0, 0].legend(handles=[Patch(fc=c, ec="black", lw=0.4, label=l)
                               for l, c in FEEDBACK_CATS],
                      frameon=False, fontsize=8, loc="upper center",
                      bbox_to_anchor=(1.05, -0.22), ncol=3)
    axes[1, 0].legend(frameon=False, fontsize=8, loc="upper center",
                      bbox_to_anchor=(1.05, -0.22), ncol=3)
    fig.tight_layout(h_pad=5.0)
    _save(fig, f"{out}/FigS7_fire_feedbacks")


def table_fire_feedbacks(out, sweeps):
    """Range of each headline quantity across the two feedback sweeps."""
    rows = []
    for kind, label in (("cattle_penalty", "Cattle removal feedback"),
                        ("hunter_penalty", "Open access feedback")):
        d = sweeps[sweeps.sweep == kind].sort_values("value")
        rows.append({
            "Feedback": label,
            "Range tested": f"0 to {d.value.max() * 100:.0f}%",
            "Asymmetry ratio": f"{d.asym_ratio.min():.1f} to {d.asym_ratio.max():.1f}",
            "S6 exchange ratio": f"{d.eff_S6_rancher.min():.1f} to {d.eff_S6_rancher.max():.1f}",
            "S5 exchange ratio": f"{d.eff_S5_rancher.min():.2f} to {d.eff_S5_rancher.max():.2f}",
            "S7 exchange ratio": f"{d.eff_S7_hunter.min():.2f} to {d.eff_S7_hunter.max():.2f}",
            "S2 removal paddocks": f"{d.S2_n_removal.iloc[0]:.0f} to {d.S2_n_removal.iloc[-1]:.0f}",
            "S2 Alt 1 paddocks": f"{d.S2_n_alt1.iloc[0]:.0f} to {d.S2_n_alt1.iloc[-1]:.0f}",
            "S2 no-change paddocks": f"{d.S2_n_alt11.iloc[0]:.0f} to {d.S2_n_alt11.iloc[-1]:.0f}",
        })
    tab = pd.DataFrame(rows)
    tab.to_csv(f"{out}/TableS5_fire_feedback_summary.csv", index=False)
    return tab


def table_landscape_thresholds(out, la):
    """Smallest weight on fire risk at which the roadside fuelbreak is built."""
    rows = []
    for (sid, budget), g in la.groupby(["scenario", "budget"]):
        built = g[g.roadside_built].fire_weight
        rows.append({"scenario": SCENARIOS[sid][0],
                     "budget": f"${budget / 1e6:.0f}M",
                     "threshold_fire_weight": (float(built.min()) if len(built)
                                               else np.nan),
                     "built_at_zero_weight": bool(
                         g[g.fire_weight == 0].roadside_built.iloc[0])})
    tab = pd.DataFrame(rows).sort_values(["scenario", "budget"])
    tab.to_csv(f"{out}/TableS6_landscape_action_thresholds.csv", index=False)
    return tab


def figure_landscape(out, la):
    """Where a landscape-scale action earns its place once fire risk is scored
    on an absolute rather than a within-paddock scale."""
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6),
                             gridspec_kw={"width_ratios": [1.15, 1]})

    ax = axes[0]
    order = list(SCENARIOS)
    weights = sorted(la.fire_weight.unique())
    M = np.array([[la[(la.scenario == sid) & (la.fire_weight == w)].roadside_built.sum()
                   for w in weights] for sid in order], dtype=float)
    im = ax.imshow(M, cmap="Blues", vmin=0, vmax=len(BUDGETS), aspect="auto")
    for i in range(M.shape[0]):
        for j in range(M.shape[1]):
            ax.text(j, i, f"{M[i, j]:.0f}", ha="center", va="center", fontsize=7,
                    color="white" if M[i, j] > len(BUDGETS) * 0.6 else INK)
    ax.set_xticks(range(0, len(weights), 2))
    ax.set_xticklabels([f"{weights[k]:.1f}" for k in range(0, len(weights), 2)], fontsize=8)
    ax.set_yticks(range(len(order)))
    ax.set_yticklabels([SCENARIOS[s][0] for s in order], fontsize=8)
    ax.set_xlabel("Weight on fire risk as a fundamental objective")
    ax.tick_params(length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_title(f"Budgets (of {len(BUDGETS)}) where the roadside fuelbreak is built",
                 loc="left", fontsize=10, color=INK)
    cb = fig.colorbar(im, ax=ax, fraction=0.04, pad=0.02)
    cb.ax.tick_params(labelsize=8)
    _panel(ax, "A", x=-0.28)

    ax = axes[1]
    d20 = la[(la.scenario == "S1") & (la.budget == B20)].sort_values("fire_weight")
    x = d20.fire_weight.values
    comp = np.vstack([d20.n_alt7.values,
                      (d20.n_removal - d20.n_alt7).values,
                      d20.n_alt1.values,
                      d20.n_alt11.values])
    comp = np.vstack([comp, N_PADDOCKS - comp.sum(axis=0)])
    bottom = np.zeros(len(x))
    for k, (label, color) in enumerate(FEEDBACK_CATS):
        ax.bar(x, comp[k], bottom=bottom, width=(x[1] - x[0]) * 0.85, color=color,
               edgecolor="white", linewidth=0.6, label=label)
        bottom += comp[k]
    built = d20[d20.roadside_built].fire_weight
    if len(built):
        ax.axvline(float(built.min()), color=INK, lw=1.2, ls="--")
        ax.text(float(built.min()), N_PADDOCKS + 0.6, " roadside fuelbreak built",
                fontsize=8, color=INK, ha="left", va="bottom")
    ax.set_ylim(0, N_PADDOCKS + 2)
    ax.set_xlabel("Weight on fire risk as a fundamental objective")
    ax.set_ylabel(f"Paddocks (of {N_PADDOCKS})")
    ax.set_title("Balanced portfolio at $20M", loc="left", fontsize=10, color=INK)
    ax.legend(frameon=False, fontsize=7, loc="upper center", bbox_to_anchor=(0.5, -0.18),
              ncol=2)
    _panel(ax, "B")
    fig.tight_layout()
    _save(fig, f"{out}/FigS8_landscape_action")


def table_decay(out, sweep, thr):
    """Effect of the roadside taper on where the fuelbreak is built."""
    rows = []
    for dv, g in sweep.groupby("roadside_decay"):
        built = g[g.roadside_built]
        rows.append({"roadside_decay": dv,
                     "scenario_budget_combinations_built": int(len(built)),
                     "budgets_built": ", ".join(f"${b/1e6:.0f}M" for b in sorted(built.budget.unique())) or "none",
                     "asymmetry_ratio": round(float(g.asym_ratio.iloc[0]), 2),
                     "S6_exchange_ratio": round(float(g.eff_S6_rancher.iloc[0]), 2)})
    tab = pd.DataFrame(rows)
    tab.to_csv(f"{out}/TableS7_roadside_taper.csv", index=False)
    return tab


def figure_decay(out, sweep, thr):
    """How the taper changes the roadside decision and its weight threshold."""
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.2))

    ax = axes[0]
    for k, budget in enumerate(sorted(sweep.budget.unique())):
        g = sweep[sweep.budget == budget].groupby("roadside_decay").roadside_built.sum()
        if g.max() == 0:
            continue
        ax.plot(g.index, g.values, lw=2, marker="o", ms=5,
                color=["#9ec5f4", "#5c9ee8", "#2a78d6", "#1b5aa6", "#0d3a73"][k],
                label=f"${budget/1e6:.0f}M")
    ax.set_ylim(-0.3, 7.4)
    ax.set_xlabel("Taper in roadside benefit with distance from the highway")
    ax.set_ylabel("Scenarios building it (of 7)")
    ax.legend(title="Budget", frameon=False, fontsize=8, title_fontsize=8)
    ax.grid(axis="y", color=GRID_GREY, lw=0.6); ax.set_axisbelow(True)
    ax.set_title("Where the roadside fuelbreak is built", loc="left", color=INK)
    _panel(ax, "A")

    ax = axes[1]
    marks = ["o", "s", "^"]
    for k, dv in enumerate(sorted(thr.roadside_decay.unique())):
        ys = []
        budgets = sorted(thr.budget.unique())
        for budget in budgets:
            g = thr[(thr.roadside_decay == dv) & (thr.budget == budget) & thr.roadside_built]
            ys.append(g.fire_weight.min() if len(g) else np.nan)
        ax.plot([b/1e6 for b in budgets], ys, lw=2, marker=marks[k], ms=6, mfc="white",
                mew=1.4, color=["#2a78d6", "#eb6834", "#4a3aa7"][k],
                label=f"taper {dv:.1f}")
    ax.set_xlabel("Budget ($ million)")
    ax.set_ylabel("Fire weight at which it is built")
    ax.set_xticks([5, 10, 20, 40, 60])
    ax.legend(frameon=False, fontsize=8)
    ax.grid(axis="y", color=GRID_GREY, lw=0.6); ax.set_axisbelow(True)
    ax.set_title("Threshold weight on fire risk, lowest across scenarios", loc="left", color=INK)
    _panel(ax, "B")
    fig.tight_layout()
    _save(fig, f"{out}/FigS9_roadside_taper")


def stage_figures(out):
    """Build every figure and summary table from the stored results."""
    _set_style()
    have = lambda *names: all(os.path.exists(f"{out}/{n}") for n in names)

    if have("sa_baseline_metrics.csv", "sa_oat.csv", "sa_montecarlo.csv", "sa_weight_sweep.csv"):
        base = pd.read_csv(f"{out}/sa_baseline_metrics.csv").iloc[0]
        oat = pd.read_csv(f"{out}/sa_oat.csv")
        mc = pd.read_csv(f"{out}/sa_montecarlo.csv")
        ws = pd.read_csv(f"{out}/sa_weight_sweep.csv")
        designs = [d for d in DESIGN_LABELS if d[0] in set(mc.run)]
        joint = mc[mc.run == "joint_pm1"]

        table_robustness(out, base, oat, mc, designs)
        table_paddock_stability(out, base, joint)
        figure_montecarlo(out, base, mc, designs)
        figure_budget_bands(out, base, joint)
        figure_weight_sweep(out, ws)
        figure_tornado(out, base, oat)

    landscape_path = f"{out}/la_fire_objective.csv"
    if os.path.exists(landscape_path):
        la = pd.read_csv(landscape_path)
        figure_landscape(out, la)
        table_landscape_thresholds(out, la)

    decay_path = f"{out}/rd_decay_sweep.csv"
    if os.path.exists(decay_path) and os.path.exists(f"{out}/rd_decay_thresholds.csv"):
        sweep = pd.read_csv(decay_path)
        thr = pd.read_csv(f"{out}/rd_decay_thresholds.csv")
        figure_decay(out, sweep, thr)
        table_decay(out, sweep, thr)

    sweeps_path = f"{out}/ff_sweeps.csv"
    if os.path.exists(sweeps_path):
        sweeps = pd.read_csv(sweeps_path)
        figure_fire_feedbacks(out, sweeps)
        table_fire_feedbacks(out, sweeps)


# ======================================================================
# 8. ENTRY POINT
# ======================================================================

def main(argv=None):
    ap = argparse.ArgumentParser(description="Sensitivity analysis of the Puʻuwaʻawaʻa "
                                             "SDM portfolio model.")
    ap.add_argument("input", help="input workbook (.xlsx)")
    ap.add_argument("outdir", help="directory for results, figures, and tables")
    ap.add_argument("--draws", type=int, default=500,
                    help="Monte Carlo draws for the joint design (default 500)")
    ap.add_argument("--stages", default="sensitivity,feedbacks,landscape,decay,figures",
                    help="comma-separated subset of sensitivity, feedbacks, "
                         "landscape, decay, figures")
    args = ap.parse_args(argv)

    stages = [s.strip() for s in args.stages.split(",") if s.strip()]
    os.makedirs(args.outdir, exist_ok=True)
    start = time.time()

    if any(s in stages for s in ("sensitivity", "feedbacks", "landscape", "decay")):
        with Pool(os.cpu_count(), initializer=_init_worker, initargs=(args.input,)) as pool:
            if "sensitivity" in stages:
                stage_sensitivity(args.input, args.outdir, args.draws, pool)
                print(f"sensitivity done ({time.time() - start:.0f}s)", flush=True)
            if "feedbacks" in stages:
                stage_feedbacks(args.input, args.outdir, args.draws, pool)
                print(f"fire feedbacks done ({time.time() - start:.0f}s)", flush=True)
            if "landscape" in stages:
                stage_landscape(args.input, args.outdir, pool)
                print(f"landscape action done ({time.time() - start:.0f}s)", flush=True)
            if "decay" in stages:
                stage_decay(args.input, args.outdir, pool)
                print(f"roadside taper done ({time.time() - start:.0f}s)", flush=True)

    if "figures" in stages:
        stage_figures(args.outdir)
        print(f"figures and tables done ({time.time() - start:.0f}s)", flush=True)

    baseline_path = f"{args.outdir}/sa_baseline_metrics.csv"
    if os.path.exists(baseline_path):
        base = pd.read_csv(baseline_path).iloc[0]
        print("\nBaseline values")
        for key, label in (("asym_ratio", "Asymmetry ratio"),
                           ("eff_S6_rancher", "S6 rancher points per T&E point lost"),
                           ("eff_S5_rancher", "S5 rancher points per T&E point lost"),
                           ("eff_S7_hunter", "S7 hunter points per T&E point lost"),
                           ("S6_alt1_count", "Alt 1 paddocks under S6 at $20M")):
            print(f"  {label:<40s} {float(base[key]):.2f}")


if __name__ == "__main__":
    sys.exit(main())
