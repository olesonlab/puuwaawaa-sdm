"""Model access for the Appendix S1 normalization comparison.

Data loading, action effectiveness, the roadside fuelbreak, scenarios, weights
and the integer program all come from src/pww_sdm_optimizer.py, so the comparison
uses the same model as the main analysis. Three additions:

- normalize_vector, the third conservation scaling compared in Appendix S1;
- prepare_scores_method, which builds the conservation scores under within-unit,
  global linear or vector normalization and the community scores under within-unit
  or global linear normalization, so the two choices can be crossed;
- solve_scenario_budget, the optimizer's solve with a choice of normalization,
  reporting total cost including the Paddock 9 commitment and the roadside
  fuelbreak.

With within-unit conservation scores and global linear community scores,
prepare_scores_method returns exactly the scores of pww_sdm_optimizer.prepare_scores.
"""
import pathlib
import sys

import numpy as np

SRC = pathlib.Path(__file__).resolve().parents[1]
REPO = SRC.parent
DATA = REPO / "data" / "pww_sdm_input_data.xlsx"
sys.path.insert(0, str(SRC))

import pww_sdm_optimizer as opt  # noqa: E402
from pww_sdm_optimizer import (  # noqa: E402,F401
    BUDGETS, FIXED_ALT_IDX, FIXED_PADDOCK_IDX, PADDOCK_ALTS, ROADSIDE_COST,
    apply_roadside, build_scenarios, compute_action_effectiveness,
    effective_weights, load_input_data,
)

normalize_global_linear = opt.normalize_to_01
normalize_within_unit = opt.normalize_within_paddock
METHODS = ["global_linear", "vector", "within_unit"]
B20 = 20_000_000


def normalize_vector(scores):
    """Divide by the Euclidean norm of the whole score matrix."""
    norm = np.sqrt(np.sum(scores ** 2))
    if norm == 0:
        return np.zeros_like(scores)
    return scores / norm


SCALERS = {"global_linear": normalize_global_linear, "vector": normalize_vector,
           "within_unit": normalize_within_unit}


def prepare_scores_method(input_data, method, roadside_built=False,
                          comm_method="global_linear"):
    """Score matrices (21 x 10) for the optimized paddocks.

    `method` scales the two conservation sub-objectives and `comm_method` the
    three community sub-objectives.

    Within-unit: action effectiveness is rescaled within each paddock, and T&E
    scores are zero where no T&E plants are recorded (as in the main analysis).
    Global linear and vector: action effectiveness is multiplied by the
    paddock's T&E count or native cover, then the whole matrix is rescaled.
    """
    n_paddocks = input_data["costs"].shape[0]
    opt_indices = [i for i in range(n_paddocks) if i != FIXED_PADDOCK_IDX]
    fire_prob = apply_roadside(input_data["fire_prob"], roadside_built)
    action_raw = compute_action_effectiveness(input_data["fire_prob_baseline"], fire_prob)
    action = action_raw[np.ix_(opt_indices, PADDOCK_ALTS)]

    if method in ("global_linear", "vector"):
        f = SCALERS[method]
        te_scores = f(action * input_data["te_count"][opt_indices, None])
        habitat_scores = f(action * input_data["native_cover"][opt_indices, None])
    elif method == "within_unit":
        within = normalize_within_unit(action)
        te_scores = within.copy()
        for idx, orig_i in enumerate(opt_indices):
            if input_data["te_count"][orig_i] == 0:
                te_scores[idx, :] = 0.0
        habitat_scores = within.copy()
    else:
        raise ValueError(f"unknown method: {method}")

    g = SCALERS[comm_method]
    scores = {
        "te": te_scores,
        "habitat": habitat_scores,
        "recreationist": g(input_data["community_raw"][np.ix_(opt_indices, PADDOCK_ALTS)]),
        "hunter": g(input_data["hunter_raw"][np.ix_(opt_indices, PADDOCK_ALTS)]),
        "rancher": g(input_data["rancher_raw"][np.ix_(opt_indices, PADDOCK_ALTS)]),
    }
    return scores, opt_indices


def solve_scenario_budget(input_data, method, weights, budget, comm_method="global_linear"):
    """pww_sdm_optimizer.solve_scenario_budget under a chosen normalization.

    Tries both states of the roadside fuelbreak and keeps the better solution.
    total_cost includes the Paddock 9 commitment and, when built, the fuelbreak.
    """
    fixed_cost = input_data["costs"][FIXED_PADDOCK_IDX, FIXED_ALT_IDX]
    best = None
    for roadside_built in (False, True):
        scores, opt_indices = prepare_scores_method(input_data, method, roadside_built, comm_method)
        available = budget - fixed_cost - (ROADSIDE_COST if roadside_built else 0.0)
        if available < 0:
            continue
        costs_opt = input_data["costs"][np.ix_(opt_indices, PADDOCK_ALTS)]
        res = opt.optimize(scores, costs_opt, available, weights)
        if res["status"] != "Optimal":
            continue
        res.update(roadside_built=roadside_built)
        res["total_cost"] = float(res["total_cost"] + fixed_cost
                                  + (ROADSIDE_COST if roadside_built else 0.0))
        if best is None or res["objective_value"] > best["objective_value"]:
            best = res
    return best


def grid(input_data, eco, comm):
    """All scenarios and budgets under one pair of normalizations."""
    out = {}
    for sdef in build_scenarios().values():
        w = effective_weights(sdef)
        for budget in BUDGETS:
            res = solve_scenario_budget(input_data, eco, w, budget, comm)
            if res is not None:
                out[(sdef["label"], budget)] = res
    return out


def symmetry_metrics(g):
    """Exchange ratios and the findings they support, at $20M against Balanced."""
    base = g.get(("Balanced", B20))
    if base is None:
        return {}

    def delta(label, key):
        r = g.get((label, B20))
        return np.nan if r is None else r["sub_scores"][key] - base["sub_scores"][key]

    def exchange(label, key):
        loss = -delta(label, "te")
        gained = delta(label, key)
        if not np.isfinite(loss) or loss <= 1e-9:
            return np.inf if gained > 0 else np.nan
        return gained / loss

    gain = delta("Conservation priority", "te")
    asym = -delta("Community priority", "te") / gain if gain > 1e-9 else np.inf
    s6 = exchange("Rancher-conservation", "rancher")
    s5 = exchange("Community priority", "rancher")
    s7 = exchange("Hunter-recreationist", "hunter")
    spend = [g[("Conservation priority", b)]["total_cost"] / b
             for b in BUDGETS if ("Conservation priority", b) in g]
    s5_60 = g.get(("Community priority", 60_000_000))
    return {
        "asym_ratio": asym,
        "S6_rancher_per_te": s6,
        "S5_rancher_per_te": s5,
        "S7_hunter_per_te": s7,
        "S6_te_change": delta("Rancher-conservation", "te"),
        "S6_rancher_change": delta("Rancher-conservation", "rancher"),
        "S2_spend_min_share": float(min(spend)) if spend else np.nan,
        "S5_spend_share_60M": float(s5_60["total_cost"] / 60e6) if s5_60 else np.nan,
        "S6_beats_S5": bool(np.nan_to_num(s6, nan=-1) > np.nan_to_num(s5, nan=-1)),
        "asym_holds": bool(asym > 1),
        "hunter_weaker": bool(np.nan_to_num(s7, nan=-1) < np.nan_to_num(s6, nan=-1)),
    }
