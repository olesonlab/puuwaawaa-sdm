"""Model access for the Paddock 9 scripts.

Everything here comes from src/pww_sdm_optimizer.py, so the Paddock 9 runs use
the same model as the main analysis rather than a separate copy. Two additions:
solve_scenario_budget reports total cost including the Paddock 9 commitment and
the roadside fuelbreak, and symmetry_metrics computes the $20M exchange ratios
against Balanced, as the sensitivity baseline does.
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

normalize_within_unit = opt.normalize_within_paddock
normalize_global_linear = opt.normalize_to_01
B20 = 20_000_000


def solve_scenario_budget(input_data, weights, budget):
    """The optimizer's solve, with total_cost covering every committed cost."""
    res = opt.solve_scenario_budget(input_data, weights, budget)
    if res is None:
        return None
    res = dict(res)
    res["total_cost"] = float(res["total_cost"] + res["fixed_cost"]
                              + (ROADSIDE_COST if res["roadside_built"] else 0.0))
    return res


def symmetry_metrics(grid):
    """Exchange ratios and the findings they support, at $20M against Balanced."""
    base = grid.get(("Balanced", B20))
    if base is None:
        return {}

    def delta(label, key):
        r = grid.get((label, B20))
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
    spend = [grid[("Conservation priority", b)]["total_cost"] / b
             for b in BUDGETS if ("Conservation priority", b) in grid]
    s5_60 = grid.get(("Community priority", 60_000_000))
    return {
        "asym_ratio": asym,
        "S6_rancher_per_te": s6,
        "S5_rancher_per_te": s5,
        "S7_hunter_per_te": s7,
        "S6_te_change": delta("Rancher-conservation", "te"),
        "S6_rancher_change": delta("Rancher-conservation", "rancher"),
        "S2_spend_min_share": min(spend) if spend else np.nan,
        "S5_spend_share_60M": s5_60["total_cost"] / 60e6 if s5_60 else np.nan,
        "S6_beats_S5": bool(np.nan_to_num(s6, nan=-1) > np.nan_to_num(s5, nan=-1)),
        "asym_holds": bool(asym > 1),
        "hunter_weaker": bool(np.nan_to_num(s7, nan=-1) < np.nan_to_num(s6, nan=-1)),
    }
