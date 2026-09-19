"""
Puʻuwaʻawaʻa SDM Optimizer
===========================
Integer programming optimization for fire management at Puʻuwaʻawaʻa Forest Reserve.

Selects one management alternative per paddock to maximize the weighted sum of
normalized sub-objective scores, subject to a budget constraint.

The roadside fuelbreak is a single landscape-level decision, not a paddock-level
alternative: it is either built along the road or not, it is charged once, and
when built it lowers fire probability in every paddock. Each scenario and budget
is therefore solved twice, with and without the roadside fuelbreak, and the
higher-scoring solution is kept. Paddocks choose among the ten paddock-level
alternatives.

Paddock 9 (580 T&E plants, the highest-value conservation site) is pre-assigned
to Alternative 7 (full restoration) and excluded from optimization. The optimizer
allocates the remaining budget across the other 21 paddocks.

Scoring approach:
    Conservation sub-objectives use within-paddock normalization: for each paddock,
    the best alternative scores 1.0 and worst scores 0.0. This separates "what to
    do" (action effectiveness, scored per paddock) from "where to invest" (handled
    by the budget constraint). Paddocks with zero T&E plants receive zero T&E
    scores; all paddocks contribute to the habitat objective.

    Community sub-objectives use global min-max normalization of raw scores
    (base score x elevation-zone multiplier).

    All scores are on [0, 1] before weighting (Edwards & Barron 1994).

Weights are applied hierarchically: fundamental objective level, then sub-objective
level (Keeney & von Winterfeldt 2007).

Objectives hierarchy:
    Ecological (fundamental)
        - Threatened & Endangered (T&E) plant species
        - Native forest habitat
    Social (fundamental)
        - Rancher interests
        - Hunter interests
        - Recreationist interests

Authors: Kirsten Oleson, Clay Trauernicht, Eric Lonsdorf, et al.
"""

import numpy as np
import pandas as pd
from pulp import LpMaximize, LpProblem, LpVariable, lpSum, LpStatus, value
import pulp
import warnings
import os
import sys

warnings.filterwarnings("ignore", category=UserWarning)

# Paddock 9 (0-indexed: 8) is pre-assigned to Alt 7 (0-indexed: 6)
FIXED_PADDOCK_IDX = 8   # paddock 9
FIXED_ALT_IDX = 6       # alternative 7

# Alternative 2 (0-indexed: 1) is the roadside fuelbreak, handled as a
# landscape-level decision rather than a paddock-level alternative.
ROADSIDE_ALT_IDX = 1
ROADSIDE_COST = 137677.06  # single cost for roadside fuel break, paddock_data[26,6]
ROADSIDE_REDUCTION = 0.20   # proportional cut in fire probability when built

# Paddocks the roadside fuelbreak protects. None means all paddocks, following
# the flammability sheet ("20% reduction for all paddocks"). To limit it to the
# paddocks along the road, list their 1-based numbers here.
ROADSIDE_PADDOCKS = None


# ============================================================
# DATA EXTRACTION
# ============================================================

def load_input_data(filepath):
    """
    Extract all input data from the workshop spreadsheet.

    Returns a dict with arrays for all 22 paddocks. The caller uses
    FIXED_PADDOCK_IDX to identify the pre-assigned paddock.
    """
    xls = pd.ExcelFile(filepath)

    # -- Paddock metadata from data(2) sheet --
    # Support both original ("data (2)") and cleaned ("paddock_data") sheet names
    if "paddock_data" in xls.sheet_names:
        data = pd.read_excel(xls, "paddock_data", header=None)
    else:
        data = pd.read_excel(xls, "data (2)", header=None)
    n_paddocks = 22
    n_alts = 11

    paddocks = pd.DataFrame({
        "paddock": list(range(1, n_paddocks + 1)),
        "area": [data.iloc[i + 2, 1] for i in range(n_paddocks)],
        "elevation": [data.iloc[i + 2, 2] for i in range(n_paddocks)],
        "size_m2": [data.iloc[i + 2, 3] for i in range(n_paddocks)],
    })

    # -- Costs per paddock per alternative --
    costs = np.zeros((n_paddocks, n_alts))
    for i in range(n_paddocks):
        for j in range(n_alts):
            val = data.iloc[i + 2, 5 + j]
            costs[i, j] = val if pd.notna(val) else 0.0

    # The roadside fuelbreak column is not a per-paddock cost. The spreadsheet
    # distributes the landscape cost across paddocks by area; the optimizer
    # charges ROADSIDE_COST once instead, so the column is not used.
    costs[:, ROADSIDE_ALT_IDX] = 0.0

    # -- T&E plant counts and native cover (raw ecological metrics) --
    rp = pd.read_excel(xls, "native_rareplants", header=None)

    te_count = np.array([rp.iloc[i + 4, 2] for i in range(n_paddocks)], dtype=float)
    native_cover = np.array([rp.iloc[i + 4, 1] for i in range(n_paddocks)], dtype=float)

    # -- Community interest scores (raw, from People sheet) --
    ppl = pd.read_excel(xls, "People", header=None)

    community_raw = np.zeros((n_paddocks, n_alts))
    hunter_raw = np.zeros((n_paddocks, n_alts))
    rancher_raw = np.zeros((n_paddocks, n_alts))

    for i in range(n_paddocks):
        for j in range(n_alts):
            c_val = ppl.iloc[i + 2, 2 + j]
            community_raw[i, j] = c_val if pd.notna(c_val) else 0.0

            h_val = ppl.iloc[i + 2, 15 + j]
            hunter_raw[i, j] = h_val if pd.notna(h_val) else 0.0

            r_val = ppl.iloc[i + 2, 28 + j]
            rancher_raw[i, j] = r_val if pd.notna(r_val) else 0.0

    # -- Fire probability data --
    flam = pd.read_excel(xls, "flammability", header=None)

    fire_prob_baseline = np.zeros(n_paddocks)
    fire_prob = np.zeros((n_paddocks, n_alts))

    for i in range(n_paddocks):
        fire_prob_baseline[i] = flam.iloc[i + 4, 1]  # current Q3
        for j in range(n_alts):
            fire_prob[i, j] = flam.iloc[i + 4, 5 + j]

    # The roadside column of the fire model describes the landscape action, not
    # a paddock treatment, so an untreated paddock keeps its baseline value.
    fire_prob[:, ROADSIDE_ALT_IDX] = fire_prob_baseline

    return {
        "paddocks": paddocks,
        "costs": costs,
        "te_count": te_count,
        "native_cover": native_cover,
        "community_raw": community_raw,
        "hunter_raw": hunter_raw,
        "rancher_raw": rancher_raw,
        "fire_prob_baseline": fire_prob_baseline,
        "fire_prob": fire_prob,
        "roadside_cost": ROADSIDE_COST,
    }


# ============================================================
# DIRECT BENEFIT SCORES
# ============================================================

# Expert-elicited direct conservation benefit per unit of ecological metric,
# for each of the 11 management alternatives.
# Scale: -1 (degradation) to 6 (full restoration).
# Source: DOFAW managers (coauthors EP, KG, MN, MW).
DIRECT_BENEFIT = np.array([1, 1, -1, 2, 3, 3, 6, 1, 2, 1, 1], dtype=float)

# Paddock-level alternatives, in 0-indexed form: everything except the roadside
# fuelbreak, which is decided once for the landscape.
PADDOCK_ALTS = [j for j in range(11) if j != ROADSIDE_ALT_IDX]


# ============================================================
# NORMALIZATION AND SCORING
# ============================================================

def normalize_to_01(scores):
    """
    Min-max normalization across all elements to [0, 1].
    Edwards & Barron (1994).
    """
    smin = scores.min()
    smax = scores.max()
    if smax == smin:
        return np.zeros_like(scores)
    return (scores - smin) / (smax - smin)


def normalize_within_paddock(scores):
    """
    Normalize each paddock's scores so best alternative = 1.0, worst = 0.0.

    This separates action effectiveness (scored here) from spatial priority
    (handled by the budget constraint in the optimizer). Each paddock
    contributes equally to the sub-objective when weights are applied.
    """
    out = np.zeros_like(scores)
    for i in range(scores.shape[0]):
        row = scores[i, :]
        rmin, rmax = row.min(), row.max()
        if rmax > rmin:
            out[i, :] = (row - rmin) / (rmax - rmin)
    return out


def roadside_mask(n_paddocks):
    """Boolean mask of the paddocks the roadside fuelbreak protects."""
    if ROADSIDE_PADDOCKS is None:
        return np.ones(n_paddocks, dtype=bool)
    mask = np.zeros(n_paddocks, dtype=bool)
    for p in ROADSIDE_PADDOCKS:
        mask[p - 1] = True
    return mask


def apply_roadside(fire_prob, roadside_built):
    """Lower fire probability in the protected paddocks when the roadside
    fuelbreak is built."""
    if not roadside_built:
        return fire_prob
    fp = fire_prob.copy()
    mask = roadside_mask(fp.shape[0])
    fp[mask, :] *= (1.0 - ROADSIDE_REDUCTION)
    return fp


def compute_action_effectiveness(fire_prob_baseline, fire_prob):
    """
    Compute conservation action effectiveness scores for each paddock x alternative.

    Combines the direct conservation benefit (expert-scored, same for all paddocks)
    with the fire risk reduction benefit (spatially varying, derived from the 30m
    fire probability model).

    Fire risk reduction is scaled to [0, 6] to match the direct benefit scale
    before combining.

    Returns:
        action_raw: array (n_paddocks x n_alts) of combined scores
    """
    fire_reduction = fire_prob_baseline[:, None] - fire_prob  # positive = good

    max_reduction = fire_reduction.max()
    if max_reduction > 0:
        scaled_fire = fire_reduction / max_reduction * 6.0
    else:
        scaled_fire = np.zeros_like(fire_reduction)

    # Combine: direct benefit (broadcast across paddocks) + spatially varying fire benefit
    action_raw = DIRECT_BENEFIT[None, :] + scaled_fire
    return action_raw


def prepare_scores(input_data, roadside_built):
    """
    Build normalized score matrices for the 21 optimized paddocks, for a given
    state of the roadside fuelbreak.

    Conservation scores: within-paddock normalization of action effectiveness.
    T&E scores zeroed for paddocks with no T&E plants. All paddocks contribute
    to the habitat objective.

    Community scores: global min-max normalization of raw scores.

    Only the ten paddock-level alternatives are scored; columns follow
    PADDOCK_ALTS order.

    Returns:
        scores: dict of score arrays, each (21 x 10)
        opt_indices: list of 21 original paddock indices included in optimization
        fire_prob: fire probability matrix (22 x 11) under this roadside state
        fixed_score: normalized conservation score of the pre-assigned paddock
    """
    n_paddocks = input_data["costs"].shape[0]
    opt_indices = [i for i in range(n_paddocks) if i != FIXED_PADDOCK_IDX]

    fire_prob = apply_roadside(input_data["fire_prob"], roadside_built)
    action_raw = compute_action_effectiveness(
        input_data["fire_prob_baseline"], fire_prob)

    # Subset to 21 optimized paddocks and the paddock-level alternatives
    action_21 = action_raw[np.ix_(opt_indices, PADDOCK_ALTS)]

    # Within-paddock normalization
    action_within = normalize_within_paddock(action_21)

    # T&E scores: zero out paddocks with no T&E plants
    te_scores = action_within.copy()
    for idx, orig_i in enumerate(opt_indices):
        if input_data["te_count"][orig_i] == 0:
            te_scores[idx, :] = 0.0

    # Habitat scores: all paddocks contribute (all have some native cover)
    habitat_scores = action_within.copy()

    # Community scores: global min-max on the 21-paddock subset
    scores = {
        "te": te_scores,
        "habitat": habitat_scores,
        "recreationist": normalize_to_01(
            input_data["community_raw"][np.ix_(opt_indices, PADDOCK_ALTS)]),
        "hunter": normalize_to_01(
            input_data["hunter_raw"][np.ix_(opt_indices, PADDOCK_ALTS)]),
        "rancher": normalize_to_01(
            input_data["rancher_raw"][np.ix_(opt_indices, PADDOCK_ALTS)]),
    }

    # Score of the pre-assigned paddock under full restoration
    p9_action = action_raw[FIXED_PADDOCK_IDX, :]
    p9_min, p9_max = p9_action.min(), p9_action.max()
    fixed_score = ((p9_action[FIXED_ALT_IDX] - p9_min) / (p9_max - p9_min)
                   if p9_max > p9_min else 0.0)

    return scores, opt_indices, fire_prob, fixed_score


# ============================================================
# SCENARIOS
# ============================================================

def build_scenarios():
    """
    Seven scenarios with hierarchical weights.

    Each scenario specifies:
        eco_weight: weight on ecological fundamental objective
        soc_weight: weight on social fundamental objective (= 1 - eco_weight)
        eco_split: (te_share, habitat_share) within ecological, summing to 1
        soc_split: (rancher_share, hunter_share, recreationist_share), summing to 1

    Effective weight on each sub-objective = fundamental_weight x within_share.
    """
    scenarios = {
        "S1_balanced": {
            "label": "Balanced",
            "eco_weight": 0.50,
            "eco_split": (0.50, 0.50),
            "soc_split": (0.33, 0.33, 0.34),
        },
        "S2_conservation": {
            "label": "Conservation priority",
            "eco_weight": 0.80,
            "eco_split": (0.50, 0.50),
            "soc_split": (0.33, 0.33, 0.34),
        },
        "S3_te_emphasis": {
            "label": "T&E emphasis",
            "eco_weight": 0.80,
            "eco_split": (0.75, 0.25),
            "soc_split": (0.33, 0.33, 0.34),
        },
        "S4_habitat_emphasis": {
            "label": "Habitat emphasis",
            "eco_weight": 0.80,
            "eco_split": (0.25, 0.75),
            "soc_split": (0.33, 0.33, 0.34),
        },
        "S5_community": {
            "label": "Community priority",
            "eco_weight": 0.20,
            "eco_split": (0.50, 0.50),
            "soc_split": (0.33, 0.33, 0.34),
        },
        "S6_rancher_conservation": {
            "label": "Rancher-conservation",
            "eco_weight": 0.50,
            "eco_split": (0.50, 0.50),
            "soc_split": (0.70, 0.15, 0.15),
        },
        "S7_hunter_recreationist": {
            "label": "Hunter-recreationist",
            "eco_weight": 0.20,
            "eco_split": (0.50, 0.50),
            "soc_split": (0.10, 0.45, 0.45),
        },
    }
    return scenarios


def effective_weights(scenario):
    """
    Compute the five effective sub-objective weights from a scenario definition.

    Returns dict with keys: te, habitat, rancher, hunter, recreationist.
    """
    eco = scenario["eco_weight"]
    soc = 1.0 - eco
    te_share, hab_share = scenario["eco_split"]
    ranch_share, hunt_share, rec_share = scenario["soc_split"]

    return {
        "te": eco * te_share,
        "habitat": eco * hab_share,
        "rancher": soc * ranch_share,
        "hunter": soc * hunt_share,
        "recreationist": soc * rec_share,
    }


# ============================================================
# OPTIMIZER
# ============================================================

def optimize(scores, costs, budget, weights):
    """
    Integer programming: select one paddock-level alternative per paddock to
    maximize the weighted sum of normalized scores, subject to a budget
    constraint.

    Operates on the 21 optimized paddocks (paddock 9 excluded) and the ten
    paddock-level alternatives. The roadside fuelbreak is handled outside this
    function: its cost is deducted from the budget and its effect is already in
    the scores.

    Args:
        scores: dict of normalized score arrays, each (21 x 10)
        costs: array (21 x 10) of per-paddock costs
        budget: maximum total cost available to the optimized paddocks
        weights: dict of effective weights per sub-objective

    Returns:
        dict with status, choices (21-element array of PADDOCK_ALTS indices),
        total_cost, objective_value, sub_scores, paddock_scores
    """
    n_paddocks, n_alts = costs.shape

    prob = LpProblem("PWW_SDM", LpMaximize)

    # Decision variables: x[i][j] = 1 if paddock i gets paddock-level alternative j
    x = [[LpVariable(f"x_{i}_{j}", cat="Binary") for j in range(n_alts)]
         for i in range(n_paddocks)]

    # Objective: maximize weighted sum of normalized scores
    obj_terms = []
    for key, w in weights.items():
        if w == 0:
            continue
        sc = scores[key]
        for i in range(n_paddocks):
            for j in range(n_alts):
                obj_terms.append(w * sc[i, j] * x[i][j])
    prob += lpSum(obj_terms)

    # Constraint: exactly one alternative per paddock
    for i in range(n_paddocks):
        prob += lpSum(x[i]) == 1

    # Budget constraint
    prob += lpSum(costs[i, j] * x[i][j]
                  for i in range(n_paddocks) for j in range(n_alts)) <= budget

    prob.solve(pulp.PULP_CBC_CMD(msg=0))

    if LpStatus[prob.status] != "Optimal":
        return {"status": LpStatus[prob.status], "choices": None}

    choices = np.zeros(n_paddocks, dtype=int)
    for i in range(n_paddocks):
        for j in range(n_alts):
            if value(x[i][j]) > 0.5:
                choices[i] = j
                break

    total_cost = sum(costs[i, choices[i]] for i in range(n_paddocks))

    sub_scores = {}
    paddock_scores = {}
    for key in scores:
        ps = np.array([scores[key][i, choices[i]] for i in range(n_paddocks)])
        paddock_scores[key] = ps
        sub_scores[key] = float(np.sum(ps))

    return {
        "status": "Optimal",
        "choices": choices,
        "total_cost": total_cost,
        "objective_value": value(prob.objective),
        "sub_scores": sub_scores,
        "paddock_scores": paddock_scores,
    }


def solve_scenario_budget(input_data, weights, budget):
    """
    Solve one scenario at one budget, trying both states of the roadside
    fuelbreak and keeping the better-scoring solution.

    Returns the winning result dict with the roadside state attached, or None
    if neither state is feasible.
    """
    fixed_cost = input_data["costs"][FIXED_PADDOCK_IDX, FIXED_ALT_IDX]
    best = None
    for roadside_built in (False, True):
        scores, opt_indices, fire_prob, fixed_score = prepare_scores(
            input_data, roadside_built)
        costs_opt = input_data["costs"][np.ix_(opt_indices, PADDOCK_ALTS)]
        available = budget - fixed_cost - (ROADSIDE_COST if roadside_built else 0.0)
        if available < 0:
            continue
        result = optimize(scores, costs_opt, available, weights)
        if result["status"] != "Optimal":
            continue
        result.update(roadside_built=roadside_built, opt_indices=opt_indices,
                      fire_prob=fire_prob, fixed_score=fixed_score,
                      fixed_cost=fixed_cost)
        if best is None or result["objective_value"] > best["objective_value"]:
            best = result
    return best


# ============================================================
# FIRE RISK ANALYSIS
# ============================================================

def compute_fire_risk_reduction(fire_prob_baseline, fire_prob, choices_22):
    """
    Compute fire risk reduction for a full 22-paddock portfolio.

    Args:
        fire_prob: fire probability matrix under the chosen roadside state
        choices_22: array of length 22 with the selected alternative (0-indexed
                    into the full 11-alternative list) per paddock
    Returns:
        mean_reduction, paddock_reductions (length-22 array)
    """
    reductions = np.array([
        fire_prob_baseline[i] - fire_prob[i, choices_22[i]]
        for i in range(22)
    ])
    return float(np.mean(reductions)), reductions


# ============================================================
# MAIN: RUN ALL SCENARIOS
# ============================================================

BUDGETS = [5_000_000, 10_000_000, 20_000_000, 40_000_000, 60_000_000]

ALTERNATIVE_NAMES = [
    "1: fence + fuelbreaks",
    "2: roadside fuelbreak",
    "3: fence + intensify grazing",
    "4: fence + fuelbreak + remove cattle",
    "5: fence + fuelbreak + remove cattle + remove ungulates",
    "6: Alt5 + weed control around T&E",
    "7: full restoration",
    "8: fence + fuelbreak + weed control around T&E",
    "9: fence + fuelbreak + remove cattle + weed control",
    "10: fence + plant native species",
    "11: no change",
]


def run_all(filepath, output_dir="."):
    """
    Run the optimizer for all scenario x budget combinations.

    Paddock 9 is pre-assigned to Alternative 7. Its cost is subtracted from
    each budget before optimizing over the remaining 21 paddocks. The roadside
    fuelbreak is decided once per scenario and budget. Results are reported for
    all 22 paddocks (paddock 9 included as fixed).

    Writes three CSV files:
        sdm_results_summary.csv: one row per scenario x budget
        sdm_results_paddock_detail.csv: one row per scenario x budget x paddock
        sdm_scenario_definitions.csv: scenario weight definitions
    """
    print("Loading input data...")
    input_data = load_input_data(filepath)

    fixed_cost = input_data["costs"][FIXED_PADDOCK_IDX, FIXED_ALT_IDX]
    fixed_paddock_num = FIXED_PADDOCK_IDX + 1
    print(f"Paddock {fixed_paddock_num} pre-assigned to Alt {FIXED_ALT_IDX + 1} "
          f"(full restoration), cost: ${fixed_cost:,.0f}")
    print(f"Paddock {fixed_paddock_num} T&E count: "
          f"{input_data['te_count'][FIXED_PADDOCK_IDX]:.0f}")
    extent = ("all paddocks" if ROADSIDE_PADDOCKS is None
              else f"paddocks {ROADSIDE_PADDOCKS}")
    print(f"Roadside fuelbreak: ${ROADSIDE_COST:,.0f} once, "
          f"{ROADSIDE_REDUCTION:.0%} fire probability reduction in {extent}")

    scenarios = build_scenarios()

    # Print effective weights
    print(f"\n{'Scenario':<28s} {'T&E':>6s} {'Habitat':>8s} "
          f"{'Rancher':>8s} {'Hunter':>8s} {'Recreat':>8s}")
    for sname, sdef in scenarios.items():
        w = effective_weights(sdef)
        print(f"  {sdef['label']:<26s} {w['te']:>6.3f} {w['habitat']:>8.3f} "
              f"{w['rancher']:>8.3f} {w['hunter']:>8.3f} {w['recreationist']:>8.3f}")

    results = []
    paddock_details = []

    for sname, sdef in scenarios.items():
        w = effective_weights(sdef)
        for budget in BUDGETS:
            result = solve_scenario_budget(input_data, w, budget)
            budget_label = f"${budget / 1e6:.0f}M"

            if result is None:
                print(f"  WARNING: {sdef['label']} @ {budget_label}: infeasible")
                continue

            opt_indices = result["opt_indices"]
            roadside_built = result["roadside_built"]

            # Reconstruct full 22-paddock choices in 11-alternative indexing
            choices_22 = np.zeros(22, dtype=int)
            choices_22[FIXED_PADDOCK_IDX] = FIXED_ALT_IDX
            for idx, orig_i in enumerate(opt_indices):
                choices_22[orig_i] = PADDOCK_ALTS[result["choices"][idx]]

            total_cost = (result["total_cost"] + result["fixed_cost"]
                          + (ROADSIDE_COST if roadside_built else 0.0))

            # Fire risk reduction across all 22 paddocks
            fire_mean, fire_paddock = compute_fire_risk_reduction(
                input_data["fire_prob_baseline"], result["fire_prob"], choices_22)

            p9_norm = result["fixed_score"]

            row = {
                "scenario": sdef["label"],
                "budget": budget,
                "budget_label": budget_label,
                "roadside_built": roadside_built,
                "total_cost": total_cost,
                "objective_value": result["objective_value"],
                "te_score": result["sub_scores"]["te"] + p9_norm,
                "habitat_score": result["sub_scores"]["habitat"] + p9_norm,
                "rancher_score": result["sub_scores"]["rancher"],
                "hunter_score": result["sub_scores"]["hunter"],
                "recreationist_score": result["sub_scores"]["recreationist"],
                "mean_fire_risk_reduction": fire_mean,
            }

            row["overall_score"] = (row["te_score"] + row["habitat_score"]
                                    + row["rancher_score"] + row["hunter_score"]
                                    + row["recreationist_score"])

            results.append(row)

            # Per-paddock details for all 22 paddocks
            for i in range(22):
                alt_idx = choices_22[i]
                is_fixed = (i == FIXED_PADDOCK_IDX)

                if is_fixed:
                    te_sc = p9_norm
                    hab_sc = p9_norm
                    rec_sc = input_data["community_raw"][i, alt_idx]
                    hun_sc = input_data["hunter_raw"][i, alt_idx]
                    ran_sc = input_data["rancher_raw"][i, alt_idx]
                else:
                    opt_idx = opt_indices.index(i)
                    te_sc = result["paddock_scores"]["te"][opt_idx]
                    hab_sc = result["paddock_scores"]["habitat"][opt_idx]
                    rec_sc = result["paddock_scores"]["recreationist"][opt_idx]
                    hun_sc = result["paddock_scores"]["hunter"][opt_idx]
                    ran_sc = result["paddock_scores"]["rancher"][opt_idx]

                paddock_details.append({
                    "scenario": sdef["label"],
                    "budget": budget,
                    "paddock": i + 1,
                    "elevation": input_data["paddocks"].iloc[i]["elevation"],
                    "te_count": input_data["te_count"][i],
                    "native_cover_pct": input_data["native_cover"][i],
                    "alternative": alt_idx + 1,
                    "alternative_name": ALTERNATIVE_NAMES[alt_idx],
                    "roadside_built": roadside_built,
                    "fixed": is_fixed,
                    "cost": input_data["costs"][i, alt_idx],
                    "te_score": te_sc,
                    "habitat_score": hab_sc,
                    "rancher_score": ran_sc,
                    "hunter_score": hun_sc,
                    "recreationist_score": rec_sc,
                    "fire_risk_reduction": fire_paddock[i],
                })

            print(f"  {sdef['label']:<26s} @ {budget_label}: "
                  f"cost=${total_cost:>12,.0f}  "
                  f"obj={result['objective_value']:.4f}  "
                  f"fire={fire_mean:.4f}  "
                  f"roadside={'yes' if roadside_built else 'no'}")

    # Save results
    summary_df = pd.DataFrame(results)
    detail_df = pd.DataFrame(paddock_details)

    summary_path = os.path.join(output_dir, "sdm_results_summary.csv")
    detail_path = os.path.join(output_dir, "sdm_results_paddock_detail.csv")

    summary_df.to_csv(summary_path, index=False)
    detail_df.to_csv(detail_path, index=False)

    print(f"\nResults written to:")
    print(f"  {summary_path}")
    print(f"  {detail_path}")

    # Scenario definitions
    scenario_rows = []
    for sname, sdef in scenarios.items():
        w = effective_weights(sdef)
        scenario_rows.append({
            "scenario_id": sname,
            "label": sdef["label"],
            "eco_weight": sdef["eco_weight"],
            "soc_weight": 1 - sdef["eco_weight"],
            "te_split": sdef["eco_split"][0],
            "habitat_split": sdef["eco_split"][1],
            "rancher_split": sdef["soc_split"][0],
            "hunter_split": sdef["soc_split"][1],
            "recreationist_split": sdef["soc_split"][2],
            "w_te": w["te"],
            "w_habitat": w["habitat"],
            "w_rancher": w["rancher"],
            "w_hunter": w["hunter"],
            "w_recreationist": w["recreationist"],
        })
    scenario_df = pd.DataFrame(scenario_rows)
    scenario_path = os.path.join(output_dir, "sdm_scenario_definitions.csv")
    scenario_df.to_csv(scenario_path, index=False)
    print(f"  {scenario_path}")

    return summary_df, detail_df, scenario_df


def print_comparison_table(summary):
    """Scenario comparison at $20M: change from the Balanced baseline and the
    exchange ratio behind Table 2."""
    at20 = summary[summary.budget == 20_000_000].set_index("scenario")
    if "Balanced" not in at20.index:
        return
    base = at20.loc["Balanced"]
    print("\n" + "=" * 60)
    print("SCENARIO COMPARISON AT $20M (change from Balanced)")
    print("=" * 60)
    print(f"{'Scenario':<26s} {'dT&E':>7s} {'dRancher':>9s} {'dHunter':>8s} "
          f"{'Ratio':>7s}")
    for label, row in at20.iterrows():
        d_te = row.te_score - base.te_score
        d_ranch = row.rancher_score - base.rancher_score
        d_hunt = row.hunter_score - base.hunter_score
        ratio = d_ranch / -d_te if d_te < -1e-9 else float("nan")
        print(f"  {label:<24s} {d_te:>+7.2f} {d_ranch:>+9.2f} {d_hunt:>+8.2f} "
              f"{ratio:>7.2f}")


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    if len(sys.argv) > 1:
        spreadsheet_path = sys.argv[1]
    else:
        spreadsheet_path = "pww_sdm_input_data.xlsx"

    if len(sys.argv) > 2:
        output_dir = sys.argv[2]
    else:
        output_dir = "."

    os.makedirs(output_dir, exist_ok=True)
    summary, detail, scenarios = run_all(spreadsheet_path, output_dir)

    print("\n" + "=" * 60)
    print("SUMMARY TABLE")
    print("=" * 60)
    pivot = summary.pivot_table(
        index="scenario",
        columns="budget_label",
        values="objective_value",
        sort=False,
    )
    print(pivot.to_string(float_format="{:.4f}".format))

    # Alternative distribution summary
    print("\n" + "=" * 60)
    print("ALTERNATIVE DISTRIBUTION")
    print("=" * 60)
    for scenario in summary["scenario"].unique():
        print(f"\n  {scenario}:")
        for budget_label in summary["budget_label"].unique():
            bval = summary[(summary["scenario"] == scenario)
                           & (summary["budget_label"] == budget_label)]
            if bval.empty:
                continue
            bnum = bval["budget"].iloc[0]
            road = "roadside yes" if bool(bval["roadside_built"].iloc[0]) else "roadside no"
            d = detail[(detail["scenario"] == scenario)
                       & (detail["budget"] == bnum)
                       & (~detail["fixed"])]
            counts = d["alternative_name"].value_counts()
            alt_str = ", ".join(f"A{k.split(':')[0]}={v}" for k, v in counts.items())
            print(f"    {budget_label}: {alt_str} (+A7 fixed in pad 9), {road}")

    print_comparison_table(summary)
