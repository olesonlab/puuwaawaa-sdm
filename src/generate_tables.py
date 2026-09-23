"""
generate_tables.py
=========================
Generates Table 1 and Appendix S1 Tables S1 and S3 for the Puʻuwaʻawaʻa SDM paper.
The other Appendix S1 tables come from src/sensitivity/pww_sensitivity_analysis.py
(Tables S2 and S4 to S7) and from the puuwaawaa-normalization repository (S8 to S10).

Inputs (expected in the same directory, or pass --data-dir):
  - sdm_results_summary.csv       (from pww_sdm_optimizer.py)
  - sdm_results_paddock_detail.csv (from pww_sdm_optimizer.py)
  - sdm_scenario_definitions.csv  (from pww_sdm_optimizer.py)
  - pww_sdm_input_data.xlsx       (costs read from paddock_data sheet)

Outputs (written to --out-dir, default = current directory):
  - table1.csv                  Table 1, management alternatives with costs and scores
  - tableS1_scenario_weights.csv  Table S1, scenario weight definitions
  - tableS3_efficiency_20M.csv    Table S3, score changes and exchange ratios at $20M

Usage:
  python generate_tables.py
  python generate_tables.py --data-dir /path/to/data --out-dir /path/to/output
"""

import argparse
from pathlib import Path

import pandas as pd
import numpy as np


SCENARIO_TITLES = {
    "Balanced": "Balanced", "Conservation priority": "Conservation Priority",
    "T&E emphasis": "T&E Emphasis", "Habitat emphasis": "Habitat Emphasis",
    "Community priority": "Community Priority", "Rancher-conservation": "Rancher-Conservation",
    "Hunter-recreationist": "Hunter-Recreationist",
}


# ─────────────────────────────────────────────────────────────────────────────
# Table 1 – Management alternatives
# ─────────────────────────────────────────────────────────────────────────────

def build_table1(data_dir: Path) -> pd.DataFrame:
    """
    Table 1: Management alternatives, conservation benefit scores,
    community interest base scores, and mean costs.

    Costs are mean per-paddock costs across 22 paddocks, read from the
    paddock_data sheet (columns 5-15, rows 2-23). Community scores are
    base scores for the Makai zone (multiplier = 1).
    Alternative 2 incurs a shared landscape-level cost of $80,728 rather
    than per-paddock costs, reported as $0* in the table.
    """
    raw = pd.read_excel(data_dir / "pww_sdm_input_data.xlsx",
                        sheet_name="paddock_data", header=None)
    costs = np.zeros((22, 11))
    for i in range(22):
        for j in range(11):
            val = raw.iloc[i + 2, 5 + j]
            costs[i, j] = val if pd.notna(val) else 0.0

    alt_descriptions = {
        1:  "Fence/fuelbreaks",
        2:  "Roadside fuelbreak",
        3:  "Fence/intensify grazing",
        4:  "Fence/fuelbreak/remove cattle",
        5:  "Fence/fuelbreak/remove cattle + ungulates",
        6:  "Alt 5 + weed control around T&E",
        7:  "Full restoration",
        8:  "Fence/fuelbreak/weed control",
        9:  "Fence/fuelbreak/remove cattle/weed",
        10: "Fence/plant native species",
        11: "No change",
    }
    direct_cons  = {1: 1, 2: 1, 3: -1, 4: 2, 5: 3, 6: 3, 7: 6, 8: 1, 9: 2, 10: 1, 11: 1}
    fire_reduc   = {1: "50%", 2: "20%", 3: "50%", 4: "50%", 5: "50%",
                    6: "50%", 7: "Reclassify", 8: "50%", 9: "50%", 10: "None", 11: "None"}
    rancher_base = {1: 3,  2: 1,  3: 4,  4: -4, 5: -4, 6: -4, 7: -4, 8: 1,  9: -4, 10: 2,  11: 0}
    hunter_base  = {1: 1,  2: 1,  3: 1,  4: -2, 5: -4, 6: -4, 7: -4, 8: 1,  9: -3, 10: 2,  11: 0}
    rec_base     = {1: 1,  2: 3,  3: 3,  4: 1,  5: 1,  6: 1,  7: 3,  8: 1,  9: 1,  10: 2,  11: 0}

    rows = []
    for i in range(1, 12):
        mc = costs[:, i - 1].mean() / 1e3
        cost_str = "$0*" if i == 2 else ("$0" if i == 11 else f"${mc:.0f}K")
        rows.append({
            "Alt":               i,
            "Management actions": alt_descriptions[i],
            "Direct cons.":      direct_cons[i],
            "Fire reduction":    fire_reduc[i],
            "Rancher":           rancher_base[i],
            "Hunter":            hunter_base[i],
            "Recreat.":          rec_base[i],
            "Mean cost":         cost_str,
        })
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
# Table S1 – Scenario weight definitions
# ─────────────────────────────────────────────────────────────────────────────

def build_table2(data_dir: Path) -> pd.DataFrame:
    """
    Table S1: Scenario weight definitions.
    Effective weight on each sub-objective equals the product of its
    fundamental objective weight and its within-group share.
    All numeric columns rounded to 3 decimal places.
    """
    scen = pd.read_csv(data_dir / "sdm_scenario_definitions.csv")
    t2 = scen[[
        "scenario_id", "label", "eco_weight", "soc_weight",
        "w_te", "w_habitat", "w_rancher", "w_hunter", "w_recreationist"
    ]].copy()
    t2.columns = [
        "Scenario ID", "Scenario", "Eco wt", "Soc wt",
        "w(T&E)", "w(Hab)", "w(Ranch)", "w(Hunt)", "w(Rec)"
    ]
    for col in ["Eco wt", "Soc wt", "w(T&E)", "w(Hab)", "w(Ranch)", "w(Hunt)", "w(Rec)"]:
        t2[col] = t2[col].round(3)
    t2["Scenario"] = t2["Scenario"].map(SCENARIO_TITLES).fillna(t2["Scenario"])
    return t2.reset_index(drop=True)


# ─────────────────────────────────────────────────────────────────────────────
# Table S3 – Efficiency comparison at $20M
# ─────────────────────────────────────────────────────────────────────────────

def build_table3(data_dir: Path) -> pd.DataFrame:
    """
    Table S3: change in each sub-objective score relative to Balanced (S1) at the
    $20 million budget, with rancher and hunter points gained per T&E point lost.
    The ratios are left blank where a scenario gives up no T&E score.
    """
    summ = pd.read_csv(data_dir / "sdm_results_summary.csv")
    summ = summ[summ["budget"] == 20_000_000]
    bal = summ[summ["scenario"] == "Balanced"].iloc[0]
    cols = [("te_score", "Change in T&E"), ("habitat_score", "Change in habitat"),
            ("rancher_score", "Change in rancher"), ("hunter_score", "Change in hunter"),
            ("recreationist_score", "Change in recreationist")]
    rows = []
    for k, (scenario, row) in enumerate(summ.set_index("scenario").loc[list(SCENARIO_TITLES)].iterrows(), 1):
        out = {"Scenario": f"{SCENARIO_TITLES[scenario]} (S{k})"}
        for c, lab in cols:
            out[lab] = round(row[c] - bal[c], 2)
        te_loss = bal.te_score - row.te_score
        lost = te_loss > 1e-9
        out["Rancher pts per T&E pt lost"] = round((row.rancher_score - bal.rancher_score) / te_loss, 2) if lost else None
        out["Hunter pts per T&E pt lost"] = round((row.hunter_score - bal.hunter_score) / te_loss, 2) if lost else None
        rows.append(out)
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Generate Table 1 and Tables S1 and S3 for the Puʻuwaʻawaʻa SDM paper."
    )
    parser.add_argument("--data-dir", default=".",
                        help="Directory containing input CSV/XLSX files.")
    parser.add_argument("--out-dir",  default=".",
                        help="Directory to write output CSVs.")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    out_dir  = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Building Table 1 (management alternatives)...")
    t1 = build_table1(data_dir)
    t1.to_csv(out_dir / "table1.csv", index=False)
    print(t1.to_string(index=False))

    print("\nBuilding Table S1 (scenario weight definitions)...")
    t2 = build_table2(data_dir)
    t2.to_csv(out_dir / "tableS1_scenario_weights.csv", index=False)
    print(t2.to_string(index=False))

    print("\nBuilding Table S3 (efficiency comparison at $20M)...")
    t3 = build_table3(data_dir)
    t3.to_csv(out_dir / "tableS3_efficiency_20M.csv", index=False)
    print(t3.to_string(index=False))

    print(f"\nDone. CSVs written to: {out_dir.resolve()}")


if __name__ == "__main__":
    main()
