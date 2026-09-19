"""
Sensitivity analysis for the Puʻuwaʻawaʻa SDM optimization (CSP2-26-0352 revision).

Responds to Reviewer 2 ("robustness of these results to uncertainty of the
elicited values in Table 1") and the AE request for sensitivity analysis.

Three analyses:
  1. One-at-a-time (OAT): shift each Table 1 input by +/-1 score point (or
     +/-50% for zone multipliers, 25-75% fuelbreak effect, 10-30% roadside
     effect, +/-30% cost) holding everything else at baseline.
  2. Monte Carlo (MC): perturb inputs jointly and by source, rerun all 35
     scenario x budget optimizations per draw, and record whether each
     headline finding still holds.
  3. Weight sweep: continuous ecological weight (0-1) at every budget, and a
     2-D grid of ecological weight x rancher share at $20M.

Usage: python pww_sensitivity.py pww_sdm_input_data.xlsx out_dir [n_draws]
"""
import sys, os, itertools, time
import numpy as np
import pandas as pd
from multiprocessing import Pool
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pww_core as c

K = ["te", "habitat", "rancher", "hunter", "recreationist"]
B20 = 20_000_000
ZONES = ["Makai", "Middle", "Mauka"]


# ------------------------------------------------------------------
# Headline metrics (each tied to a manuscript claim)
# ------------------------------------------------------------------
def metrics(res):
    df = pd.DataFrame([{k: v for k, v in r.items() if k != "choices"} for r in res])
    ch = {(r["scenario"], r["budget"]): r["choices"] for r in res}
    b = df[df.budget == B20].set_index("scenario")
    dlt = {s: b.loc[s, K] - b.loc["S1", K] for s in b.index}
    m = {"n_infeasible": 35 - len(res)}
    # Asymmetry: T&E lost moving to Community Priority / T&E gained moving to Conservation Priority
    gain = dlt["S2"]["te"]
    m["asym_ratio"] = -dlt["S5"]["te"] / gain if gain > 1e-9 else np.inf
    m["asym_holds"] = m["asym_ratio"] > 1
    # Rancher points gained per T&E point lost
    def eff(s, key):
        loss = -dlt[s]["te"]
        g = dlt[s][key]
        if loss <= 1e-9:
            return np.inf if g > 0 else np.nan
        return g / loss
    m["eff_S6_rancher"] = eff("S6", "rancher")
    m["eff_S5_rancher"] = eff("S5", "rancher")
    m["eff_S7_hunter"] = eff("S7", "hunter")
    m["S6_beats_S5"] = m["eff_S6_rancher"] > m["eff_S5_rancher"]
    m["hunter_weaker_than_rancher"] = m["eff_S7_hunter"] < m["eff_S6_rancher"]
    # Alternative 1 is the modal alternative under Rancher-Conservation at $20M
    cnt6 = np.bincount(ch[("S6", B20)], minlength=11)
    m["S6_alt1_count"] = int(cnt6[0])
    m["S6_alt1_modal"] = cnt6[0] == cnt6.max()
    # Recreationist cost of Rancher-Conservation
    m["S6_rec_change"] = dlt["S6"]["recreationist"]
    m["S2_rec_change"] = dlt["S2"]["recreationist"]
    # Conservation scenarios converge at $20M
    m["S2_S3_S4_identical"] = bool((ch[("S2", B20)] == ch[("S3", B20)]).all()
                                   and (ch[("S2", B20)] == ch[("S4", B20)]).all())
    # Budget binding: Conservation Priority spends >=95% of every budget;
    # Community Priority leaves >=10% unspent at $60M
    s2 = df[df.scenario == "S2"]
    m["S2_min_spend_share"] = float((s2.total_cost / s2.budget).min())
    s5_60 = df[(df.scenario == "S5") & (df.budget == 60_000_000)]
    m["S5_spend_share_60M"] = float(s5_60.total_cost.iloc[0] / 60e6)
    m["budget_asym_holds"] = (m["S2_min_spend_share"] >= 0.95) and (m["S5_spend_share_60M"] <= 0.90)
    # Alternatives 8-11 never selected across all 35 runs
    used = np.unique(np.concatenate([r["choices"] for r in res]))
    m["alts_8_11_never"] = not any(a in used for a in (7, 8, 9, 10))
    m["alts_used"] = ";".join(str(a + 1) for a in used)
    # Budget vs weights: mean pairwise portfolio difference among scenarios at $20M
    # vs mean within-scenario difference between $10M and $40M
    S = list(c.SCENARIOS)
    m["hamming_between_scen_20M"] = float(np.mean([(ch[(a, B20)] != ch[(bb, B20)]).sum()
                                                   for a, bb in itertools.combinations(S, 2)]))
    m["hamming_within_10v40"] = float(np.mean([(ch[(s, 10e6)] != ch[(s, 40e6)]).sum() for s in S]))
    m["budget_beats_weights"] = m["hamming_within_10v40"] > m["hamming_between_scen_20M"]
    # T&E and rancher totals for bands
    for s in S:
        for bud in c.BUDGETS:
            row = df[(df.scenario == s) & (df.budget == bud)]
            ok = len(row) > 0
            m[f"te_{s}_{int(bud/1e6)}"] = float(row.te.iloc[0]) if ok else np.nan
            m[f"rancher_{s}_{int(bud/1e6)}"] = float(row.rancher.iloc[0]) if ok else np.nan
    # Per-paddock choices at $20M for stability maps
    for s in ["S1", "S2", "S5", "S6", "S7"]:
        m[f"choices_{s}_20"] = ",".join(str(a + 1) for a in ch[(s, B20)])
    return m


# ------------------------------------------------------------------
# Perturbations
# ------------------------------------------------------------------
def draw_params(rng, sources, width=1.0):
    p = c.default_params()
    if "conservation" in sources:
        p["direct"] = p["direct"] + rng.uniform(-width, width, 11)
    if "community" in sources:
        for k in ("base_rec", "base_hunt", "base_ranch"):
            e = rng.uniform(-width, width, 11)
            e[10] = 0.0  # Alt 11 (no change) is the zero anchor
            p[k] = p[k] + e
        for k in ("mult_rec", "mult_hunt", "mult_ranch"):
            p[k] = {z: v * rng.uniform(1 - 0.5 * width, 1 + 0.5 * width) for z, v in p[k].items()}
    if "fire_cost" in sources:
        p["fuelbreak"] = rng.uniform(0.25, 0.75)
        p["roadside"] = rng.uniform(0.10, 0.30)
        p["cost_mult"] = rng.uniform(0.7, 1.3, 11)
    return p


_D = None


def _init(path):
    global _D
    _D = c.load(path)


def _mc_job(args):
    seed, sources, width, label = args
    rng = np.random.default_rng(seed)
    p = draw_params(rng, sources, width)
    m = metrics(c.run(_D, p))
    m.update(run=label, seed=seed)
    return m


def _oat_job(args):
    name, p = args
    m = metrics(c.run(_D, p))
    m["param"] = name
    return m


def oat_params():
    base = c.default_params()
    alts = [f"A{j+1}" for j in range(11)]
    jobs = []
    labels = {"direct": "Conservation benefit", "base_rec": "Recreationist score",
              "base_hunt": "Hunter score", "base_ranch": "Rancher score"}
    for key, lab in labels.items():
        for j in range(11):
            if key != "direct" and j == 10:
                continue
            for sgn in (-1, 1):
                p = c.default_params()
                p[key] = p[key].copy()
                p[key][j] += sgn
                jobs.append((f"{lab}|{alts[j]}|{sgn:+d}", p))
    for key, lab in (("mult_rec", "Recreationist multiplier"), ("mult_hunt", "Hunter multiplier"),
                     ("mult_ranch", "Rancher multiplier")):
        for z in ZONES:
            for f, sgn in ((0.5, -1), (1.5, 1)):
                p = c.default_params()
                p[key] = dict(p[key]); p[key][z] *= f
                jobs.append((f"{lab}|{z}|{sgn:+d}", p))
    for v, sgn in ((0.25, -1), (0.75, 1)):
        p = c.default_params(); p["fuelbreak"] = v
        jobs.append((f"Fuelbreak effect|50%|{sgn:+d}", p))
    for v, sgn in ((0.10, -1), (0.30, 1)):
        p = c.default_params(); p["roadside"] = v
        jobs.append((f"Roadside effect|20%|{sgn:+d}", p))
    for j in range(11):
        if j == 10 or j == 1:
            continue  # Alt 11 costs zero; Alt 2 per-paddock cost is zero
        for f, sgn in ((0.7, -1), (1.3, 1)):
            p = c.default_params(); p["cost_mult"] = np.ones(11); p["cost_mult"][j] = f
            jobs.append((f"Cost|{alts[j]}|{sgn:+d}", p))
    return jobs


def weight_sweep(d):
    rows = []
    for eco in np.round(np.arange(0, 1.0001, 0.05), 2):
        w = c.eff_weights(eco, (0.5, 0.5), (0.33, 0.33, 0.34))
        for r in c.run(d, c.default_params(), weights_override={f"eco{eco}": w}):
            rows.append(dict(eco_weight=eco, rancher_share=0.33, budget=r["budget"],
                             **{k: r[k] for k in K}, total_cost=r["total_cost"],
                             n_alt7=int((r["choices"] == 6).sum()),
                             n_alt1=int((r["choices"] == 0).sum()),
                             n_alt3=int((r["choices"] == 2).sum())))
    for eco in np.round(np.arange(0, 1.0001, 0.1), 2):
        for rs in np.round(np.arange(0, 1.0001, 0.1), 2):
            w = c.eff_weights(eco, (0.5, 0.5), (rs, (1 - rs) / 2, (1 - rs) / 2))
            for r in c.run(d, c.default_params(), weights_override={"x": w}, budgets=[B20]):
                rows.append(dict(eco_weight=eco, rancher_share=rs, budget=B20, grid=True,
                                 **{k: r[k] for k in K}, total_cost=r["total_cost"],
                                 n_alt7=int((r["choices"] == 6).sum()),
                                 n_alt1=int((r["choices"] == 0).sum()),
                                 n_alt3=int((r["choices"] == 2).sum())))
    return pd.DataFrame(rows)


if __name__ == "__main__":
    path, out = sys.argv[1], sys.argv[2]
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 500
    os.makedirs(out, exist_ok=True)
    d = c.load(path)
    t0 = time.time()

    base = metrics(c.run(d, c.default_params())); base["run"] = "baseline"
    pd.DataFrame([base]).to_csv(f"{out}/sa_baseline_metrics.csv", index=False)
    print("baseline done", time.time() - t0, flush=True)

    weight_sweep(d).to_csv(f"{out}/sa_weight_sweep.csv", index=False)
    print("weights done", time.time() - t0, flush=True)

    with Pool(os.cpu_count(), initializer=_init, initargs=(path,)) as pool:
        oat = pd.DataFrame(pool.map(_oat_job, oat_params()))
        oat.to_csv(f"{out}/sa_oat.csv", index=False)
        print("OAT done", time.time() - t0, flush=True)

        designs = [("conservation_only", ["conservation"], 1.0, n // 2),
                   ("community_only", ["community"], 1.0, n // 2),
                   ("fire_cost_only", ["fire_cost"], 1.0, n // 2),
                   ("joint_pm1", ["conservation", "community", "fire_cost"], 1.0, n),
                   ("joint_pm2", ["conservation", "community", "fire_cost"], 2.0, n // 2)]
        seed = 1000
        allmc = []
        for label, src, width, nd in designs:
            jobs = [(seed + i, src, width, label) for i in range(nd)]
            seed += nd
            allmc += pool.map(_mc_job, jobs, chunksize=4)
            pd.DataFrame(allmc).to_csv(f"{out}/sa_montecarlo.csv", index=False)
            print(label, "done", time.time() - t0, flush=True)
