"""Solver runs behind the Appendix S1 normalization comparison.

Writes, to this folder:
  appendix_score_spread.csv          per-paddock T&E score spread under each
                                     conservation normalization (Table S8, Figure S10)
  appendix_normalization_portfolios.csv
                                     portfolios for every scenario and budget under
                                     each conservation normalization, community scores
                                     global linear (Table S9, Figure S11)
  normalization_symmetry.csv         $20M exchange ratios for four crossed pairings
                                     of conservation and community normalization
                                     (Table S10)

    python src/normalization/normalization_runs.py

CBC via PuLP 2.9.0, as in the main analysis.
"""
import pathlib

import pandas as pd

import norm_model as m

HERE = pathlib.Path(__file__).resolve().parent
ECO_COMM_PAIRS = [("within_unit", "global_linear"), ("global_linear", "within_unit"),
                  ("global_linear", "global_linear"), ("within_unit", "within_unit")]


def score_spread(data):
    rows = []
    for method in m.METHODS:
        for built in (False, True):
            scores, opt_indices = m.prepare_scores_method(data, method, built)
            te = scores["te"]
            for idx, orig_i in enumerate(opt_indices):
                rows.append({"method": method, "paddock": orig_i + 1,
                             "te_count": data["te_count"][orig_i],
                             "spread": float(te[idx].max() - te[idx].min()),
                             "roadside_built": built})
    return pd.DataFrame(rows)


def portfolios(data):
    rows = []
    for eco in m.METHODS:
        for (label, budget), r in m.grid(data, eco, "global_linear").items():
            alts = [m.PADDOCK_ALTS[c] + 1 for c in r["choices"]]
            rows.append({
                "method_eco": eco, "method_comm": "global_linear",
                "scenario": label, "budget": budget, "budget_M": budget / 1e6,
                "roadside_built": r["roadside_built"], "total_cost": r["total_cost"],
                **{k: r["sub_scores"][k] for k in
                   ("te", "habitat", "rancher", "hunter", "recreationist")},
                "n_conservation_alts": sum(1 for a in alts if a in (4, 5, 6, 7)),
                "n_alt3": alts.count(3), "n_alt1": alts.count(1), "n_alt7": alts.count(7),
                "choices": ",".join(str(a) for a in alts),
            })
    return pd.DataFrame(rows)


def symmetry(data):
    rows = []
    for eco, comm in ECO_COMM_PAIRS:
        met = m.symmetry_metrics(m.grid(data, eco, comm))
        met.update(eco=eco, comm=comm)
        rows.append(met)
    return pd.DataFrame(rows)


if __name__ == "__main__":
    data = m.load_input_data(str(m.DATA))
    sp = score_spread(data)
    sp.to_csv(HERE / "appendix_score_spread.csv", index=False)
    print("Paddocks (of 21) with T&E spread below each threshold, no roadside fuelbreak")
    for method in m.METHODS:
        s = sp[(sp.method == method) & ~sp.roadside_built].spread
        print(f"  {method:<14s} {int((s < 0.01).sum()):>3d} {int((s < 0.05).sum()):>3d} "
              f"{int((s < 0.10).sum()):>3d}")
    pf = portfolios(data)
    pf.to_csv(HERE / "appendix_normalization_portfolios.csv", index=False)
    print(f"Portfolios: {len(pf)} rows")
    sy = symmetry(data)
    sy.to_csv(HERE / "normalization_symmetry.csv", index=False)
    print(sy[["eco", "comm", "asym_ratio", "S6_rancher_per_te", "S5_rancher_per_te",
              "S7_hunter_per_te"]].to_string(index=False, float_format=lambda v: f"{v:.4f}"))
