"""
Fire feedback sensitivity for the Puʻuwaʻawaʻa SDM optimization.

Reviewer 1 (comment 16) asks why only fuelbreaks change fire risk in Table 1,
and specifically whether removing grazers should raise fire risk. The submitted
model assigns a 0% change in fire probability to cattle and ungulate removal and
no fire effect at all to continued public access.

This script adds two feedbacks and tests how far they can go before conclusions
change:
  cattle_penalty   proportional increase in post-treatment Q3 fire probability
                   for alternatives that remove cattle (4, 5, 6, 9) and for full
                   restoration (7), swept 0 to 1.0
  hunter_penalty   proportional increase for alternatives that leave the paddock
                   open to hunters and other users (1, 2, 3, 8, 10, 11), swept
                   0 to 0.5

Three analyses: a one-dimensional sweep of each penalty across all 35
scenario-budget combinations, a two-dimensional grid at $20 million, and a Monte
Carlo run that adds both penalties to the joint +/-1 perturbation of all elicited
inputs.

Usage: python pww_fire_feedback.py pww_sdm_input_data.xlsx out_dir [n_draws]
"""
import sys, os, time
import numpy as np
import pandas as pd
from multiprocessing import Pool
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pww_core as c
from pww_sensitivity import metrics, draw_params, B20

CATTLE_GRID = np.round(np.arange(0, 1.001, 0.05), 3)
HUNTER_GRID = np.round(np.arange(0, 0.501, 0.025), 3)
CATTLE_GRID_2D = np.round(np.arange(0, 1.001, 0.1), 3)
HUNTER_GRID_2D = np.round(np.arange(0, 0.501, 0.05), 3)

_D = None


def _init(path):
    global _D
    _D = c.load(path)


def extra(res, m):
    """Metrics specific to the fire feedbacks, at $20M."""
    ch = {(r["scenario"], r["budget"]): r["choices"] for r in res}
    df = pd.DataFrame([{k: v for k, v in r.items() if k != "choices"} for r in res])
    for s in ["S1", "S2", "S5", "S6", "S7"]:
        if (s, B20) not in ch:
            continue
        cnt = np.bincount(ch[(s, B20)], minlength=11)
        m[f"{s}_n_removal"] = int(cnt[[3, 4, 5, 6, 8]].sum())   # alts 4,5,6,7,9
        m[f"{s}_n_alt7"] = int(cnt[6])
        m[f"{s}_n_alt1"] = int(cnt[0])
        m[f"{s}_n_alt3"] = int(cnt[2])
        m[f"{s}_n_alt2"] = int(cnt[1])
        row = df[(df.scenario == s) & (df.budget == B20)]
        m[f"{s}_fire"] = float(row.fire.iloc[0])
    return m


def run_point(p):
    res = c.run(_D, p)
    return extra(res, metrics(res))


def _sweep_job(args):
    kind, v = args
    p = c.default_params()
    p[kind] = float(v)
    m = run_point(p)
    m.update(sweep=kind, value=float(v))
    return m


def _grid_job(args):
    cp, hp = args
    p = c.default_params()
    p["cattle_penalty"], p["hunter_penalty"] = float(cp), float(hp)
    res = c.run(_D, p, budgets=[B20, 10_000_000, 40_000_000])
    m = extra(res, {})
    b = pd.DataFrame([{k: v for k, v in r.items() if k != "choices"} for r in res])
    b20 = b[b.budget == B20].set_index("scenario")
    K = ["te", "habitat", "rancher", "hunter", "recreationist"]
    d6 = b20.loc["S6", K] - b20.loc["S1", K]
    d5 = b20.loc["S5", K] - b20.loc["S1", K]
    d2 = b20.loc["S2", K] - b20.loc["S1", K]
    m["eff_S6_rancher"] = d6["rancher"] / -d6["te"] if d6["te"] < 0 else np.inf
    m["eff_S5_rancher"] = d5["rancher"] / -d5["te"] if d5["te"] < 0 else np.inf
    m["asym_ratio"] = -d5["te"] / d2["te"] if d2["te"] > 1e-9 else np.inf
    m.update(cattle_penalty=float(cp), hunter_penalty=float(hp))
    return m


def _mc_job(args):
    seed, cattle_hi, hunter_hi = args
    rng = np.random.default_rng(seed)
    p = draw_params(rng, ["conservation", "community", "fire_cost"], 1.0)
    p["cattle_penalty"] = float(rng.uniform(0, cattle_hi))
    p["hunter_penalty"] = float(rng.uniform(0, hunter_hi))
    m = run_point(p)
    m.update(run="joint_with_feedbacks", seed=seed,
             cattle_penalty=p["cattle_penalty"], hunter_penalty=p["hunter_penalty"])
    return m


if __name__ == "__main__":
    path, out = sys.argv[1], sys.argv[2]
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 400
    os.makedirs(out, exist_ok=True)
    t0 = time.time()
    with Pool(os.cpu_count(), initializer=_init, initargs=(path,)) as pool:
        jobs = [("cattle_penalty", v) for v in CATTLE_GRID] + \
               [("hunter_penalty", v) for v in HUNTER_GRID]
        pd.DataFrame(pool.map(_sweep_job, jobs)).to_csv(f"{out}/ff_sweeps.csv", index=False)
        print("sweeps done", time.time() - t0, flush=True)

        grid = [(cp, hp) for cp in CATTLE_GRID_2D for hp in HUNTER_GRID_2D]
        pd.DataFrame(pool.map(_grid_job, grid)).to_csv(f"{out}/ff_grid.csv", index=False)
        print("grid done", time.time() - t0, flush=True)

        mc = pool.map(_mc_job, [(5000 + i, 1.0, 0.5) for i in range(n)], chunksize=4)
        pd.DataFrame(mc).to_csv(f"{out}/ff_montecarlo.csv", index=False)
        print("mc done", time.time() - t0, flush=True)
