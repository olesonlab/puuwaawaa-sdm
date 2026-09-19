"""
Parametrized core of pww_sdm_optimizer.py for sensitivity analysis.

Same data extraction, scoring, normalization, and IP formulation as the
original script. The difference: every elicited or assumed input in Table 1
(direct conservation benefit, community base scores, elevation-zone
multipliers, fuelbreak/roadside fire effect, costs) is an explicit parameter
so it can be perturbed.
"""
import numpy as np
import pandas as pd
import pulp
from pulp import LpMaximize, LpProblem, LpVariable, lpSum, LpStatus, value

FIXED_PADDOCK_IDX = 8   # paddock 9
FIXED_ALT_IDX = 6       # alternative 7
N_P, N_A = 22, 11
BUDGETS = [5_000_000, 10_000_000, 20_000_000, 40_000_000, 60_000_000]
SHARED_FIREBREAK_COST = 80728.08

# ---------------- Table 1 elicited values (baseline) ----------------
DIRECT_BENEFIT = np.array([1, 1, -1, 2, 3, 3, 6, 1, 2, 1, 1], dtype=float)
# Community base scores per alternative, recovered from the People sheet
# (raw paddock score / zone multiplier). Verified against the sheet in load().
BASE_REC = np.array([1, 3, 3, 1, 1, 1, 3, 1, 1, 2, 0], dtype=float)
BASE_HUNT = np.array([1, 1, 1, -2, -4, -4, -4, 1, -3, 2, 0], dtype=float)
BASE_RANCH = np.array([3, 1, 4, -4, -4, -4, -4, 1, -4, 2, 0], dtype=float)
# Elevation-zone multipliers (makai, middle, mauka)
MULT_REC = {"Makai": 3.0, "Middle": 1.0, "Mauka": 2.0}
MULT_HUNT = {"Makai": 1.0, "Middle": 2.0, "Mauka": 3.0}
MULT_RANCH = {"Makai": 1.0, "Middle": 2.0, "Mauka": 3.0}
FUELBREAK_EFFECT = 0.50   # proportional reduction in Q3 fire probability
ROADSIDE_EFFECT = 0.20
FUELBREAK_ALTS = [0, 2, 3, 4, 5, 7, 8]  # alts 1,3,4,5,6,8,9 (0-indexed)
ROADSIDE_ALT = 1
# Fire feedbacks not in the submitted model (Reviewer 1, comment 16):
# removing cattle lets fine fuels accumulate, and alternatives that keep the
# paddock open to hunters and other users keep human ignition sources in it.
CATTLE_REMOVAL_ALTS = [3, 4, 5, 6, 8]    # alts 4,5,6,7,9
OPEN_ACCESS_ALTS = [0, 1, 2, 7, 9, 10]   # alts 1,2,3,8,10,11

SCENARIOS = {
    "S1": ("Balanced", 0.50, (0.50, 0.50), (0.33, 0.33, 0.34)),
    "S2": ("Conservation priority", 0.80, (0.50, 0.50), (0.33, 0.33, 0.34)),
    "S3": ("T&E emphasis", 0.80, (0.75, 0.25), (0.33, 0.33, 0.34)),
    "S4": ("Habitat emphasis", 0.80, (0.25, 0.75), (0.33, 0.33, 0.34)),
    "S5": ("Community priority", 0.20, (0.50, 0.50), (0.33, 0.33, 0.34)),
    "S6": ("Rancher-conservation", 0.50, (0.50, 0.50), (0.70, 0.15, 0.15)),
    "S7": ("Hunter-recreationist", 0.20, (0.50, 0.50), (0.10, 0.45, 0.45)),
}


def eff_weights(eco, eco_split, soc_split):
    soc = 1 - eco
    return {"te": eco * eco_split[0], "habitat": eco * eco_split[1],
            "rancher": soc * soc_split[0], "hunter": soc * soc_split[1],
            "recreationist": soc * soc_split[2]}


def load(filepath):
    xls = pd.ExcelFile(filepath)
    data = pd.read_excel(xls, "paddock_data", header=None)
    zones = [str(data.iloc[i + 2, 2]).strip() for i in range(N_P)]
    costs = np.array([[data.iloc[i + 2, 5 + j] if pd.notna(data.iloc[i + 2, 5 + j]) else 0.0
                       for j in range(N_A)] for i in range(N_P)], dtype=float)
    costs[:, 1] = 0.0
    rp = pd.read_excel(xls, "native_rareplants", header=None)
    te_count = np.array([rp.iloc[i + 4, 2] for i in range(N_P)], dtype=float)
    ppl = pd.read_excel(xls, "People", header=None)
    raw = {k: np.array([[ppl.iloc[i + 2, c + j] if pd.notna(ppl.iloc[i + 2, c + j]) else 0.0
                         for j in range(N_A)] for i in range(N_P)], dtype=float)
           for k, c in (("rec", 2), ("hunt", 15), ("ranch", 28))}
    flam = pd.read_excel(xls, "flammability", header=None)
    fp0 = np.array([flam.iloc[i + 4, 1] for i in range(N_P)], dtype=float)
    fp = np.array([[flam.iloc[i + 4, 5 + j] for j in range(N_A)] for i in range(N_P)], dtype=float)
    d = dict(zones=zones, costs=costs, te_count=te_count, fp0=fp0, fp=fp, raw=raw)
    # sanity check: reconstructed community scores == sheet
    base = default_params()
    for k, b, m in (("rec", "base_rec", "mult_rec"), ("hunt", "base_hunt", "mult_hunt"),
                    ("ranch", "base_ranch", "mult_ranch")):
        rec = community_matrix(zones, base[b], base[m])
        assert np.allclose(rec, raw[k]), f"community reconstruction failed for {k}"
    return d


def default_params():
    return dict(direct=DIRECT_BENEFIT.copy(), base_rec=BASE_REC.copy(),
                base_hunt=BASE_HUNT.copy(), base_ranch=BASE_RANCH.copy(),
                mult_rec=dict(MULT_REC), mult_hunt=dict(MULT_HUNT),
                mult_ranch=dict(MULT_RANCH), fuelbreak=FUELBREAK_EFFECT,
                roadside=ROADSIDE_EFFECT, cost_mult=np.ones(N_A),
                cattle_penalty=0.0, hunter_penalty=0.0)


def community_matrix(zones, base, mult):
    return np.array([base * mult[z] for z in zones])


def fire_matrix(d, p):
    """Rescale the modeled reductions for fuelbreak and roadside alternatives."""
    fp0, fp = d["fp0"], d["fp"].copy()
    red = fp0[:, None] - fp
    red[:, FUELBREAK_ALTS] *= p["fuelbreak"] / FUELBREAK_EFFECT
    red[:, ROADSIDE_ALT] *= p["roadside"] / ROADSIDE_EFFECT
    fp = fp0[:, None] - red
    # Fire feedbacks: proportional increases in post-treatment fire probability
    if p.get("cattle_penalty"):
        fp[:, CATTLE_REMOVAL_ALTS] *= 1.0 + p["cattle_penalty"]
    if p.get("hunter_penalty"):
        fp[:, OPEN_ACCESS_ALTS] *= 1.0 + p["hunter_penalty"]
    return np.minimum(fp, 1.0)


def build_scores(d, p):
    fp = fire_matrix(d, p)
    red = d["fp0"][:, None] - fp   # negative where a feedback raises fire probability
    scaled = red / red.max() * 6.0 if red.max() > 0 else np.zeros_like(red)
    action = p["direct"][None, :] + scaled
    opt = [i for i in range(N_P) if i != FIXED_PADDOCK_IDX]
    a = action[opt]
    within = np.zeros_like(a)
    for i in range(a.shape[0]):
        lo, hi = a[i].min(), a[i].max()
        if hi > lo:
            within[i] = (a[i] - lo) / (hi - lo)
    te = within.copy()
    for k, oi in enumerate(opt):
        if d["te_count"][oi] == 0:
            te[k] = 0
    def mm(x):
        return (x - x.min()) / (x.max() - x.min()) if x.max() > x.min() else np.zeros_like(x)
    z = d["zones"]
    scores = {
        "te": te, "habitat": within.copy(),
        "recreationist": mm(community_matrix(z, p["base_rec"], p["mult_rec"])[opt]),
        "hunter": mm(community_matrix(z, p["base_hunt"], p["mult_hunt"])[opt]),
        "rancher": mm(community_matrix(z, p["base_ranch"], p["mult_ranch"])[opt]),
    }
    p9 = action[FIXED_PADDOCK_IDX]
    p9n = (p9[FIXED_ALT_IDX] - p9.min()) / (p9.max() - p9.min()) if p9.max() > p9.min() else 0.0
    costs = (d["costs"] * p["cost_mult"][None, :])[opt]
    return scores, opt, costs, fp, p9n


def optimize(scores, costs, budget, w, shared_cost):
    n, m = costs.shape
    prob = LpProblem("PWW", LpMaximize)
    x = [[LpVariable(f"x_{i}_{j}", cat="Binary") for j in range(m)] for i in range(n)]
    y = LpVariable("any_alt2", cat="Binary")
    prob += lpSum(w[k] * scores[k][i, j] * x[i][j]
                  for k in w if w[k] != 0 for i in range(n) for j in range(m))
    for i in range(n):
        prob += lpSum(x[i]) == 1
        prob += x[i][1] <= y
    prob += lpSum(costs[i, j] * x[i][j] for i in range(n) for j in range(m)) + shared_cost * y <= budget
    prob.solve(pulp.PULP_CBC_CMD(msg=0))
    if LpStatus[prob.status] != "Optimal":
        return None
    ch = np.array([max(range(m), key=lambda j: value(x[i][j])) for i in range(n)])
    cost = sum(costs[i, ch[i]] for i in range(n)) + (shared_cost if (ch == 1).any() else 0)
    sub = {k: float(sum(scores[k][i, ch[i]] for i in range(n))) for k in scores}
    return dict(choices=ch, cost=cost, sub=sub, obj=value(prob.objective))


def run(d, p, scenario_ids=None, budgets=None, weights_override=None):
    """Run scenario x budget grid. Returns list of result dicts."""
    scores, opt, costs, fp, p9n = build_scores(d, p)
    fixed_cost = d["costs"][FIXED_PADDOCK_IDX, FIXED_ALT_IDX] * p["cost_mult"][FIXED_ALT_IDX]
    out = []
    items = weights_override.items() if weights_override else \
        ((s, eff_weights(*SCENARIOS[s][1:])) for s in (scenario_ids or SCENARIOS))
    for sid, w in items:
        for b in (budgets or BUDGETS):
            r = optimize(scores, costs, b - fixed_cost, w, SHARED_FIREBREAK_COST)
            if r is None:
                continue
            ch22 = np.zeros(N_P, dtype=int)
            ch22[FIXED_PADDOCK_IDX] = FIXED_ALT_IDX
            for k, oi in enumerate(opt):
                ch22[oi] = r["choices"][k]
            fire = float(np.mean([d["fp0"][i] - fp[i, ch22[i]] for i in range(N_P)]))
            out.append(dict(scenario=sid, budget=b, choices=ch22,
                            total_cost=r["cost"] + fixed_cost,
                            te=r["sub"]["te"] + p9n, habitat=r["sub"]["habitat"] + p9n,
                            rancher=r["sub"]["rancher"], hunter=r["sub"]["hunter"],
                            recreationist=r["sub"]["recreationist"], fire=fire))
    return out
