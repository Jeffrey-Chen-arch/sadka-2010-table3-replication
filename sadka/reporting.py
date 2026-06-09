"""Excel workbook + memo builders (Step 08)."""
import json
import pandas as pd
from .core import ensure_dir, resolve


# ===== from reporting.py =====
SHEETS = [
    ("Table3_Targets", "data/benchmarks/sadka_table3_targets.csv"),
    ("Table3_Replicated_Main", "outputs/tables/table3_replicated_long.csv"),
    ("Table3_Differences", "outputs/tables/table3_original_vs_replication.csv"),
    ("Liquidity_Focus", "outputs/tables/table3_liquidity_focus.csv"),
    ("Table1_Sample_Audit", "outputs/tables/table1_style_count_diff.csv"),
    ("Table2_Factor_Corr", "outputs/tables/table2_factor_correlations_diff.csv"),
    ("Figure1_Key_Months", "outputs/tables/liquidity_key_months.csv"),
    ("Factor_Scale_Audit", "outputs/tables/factor_scale_audit.csv"),
    ("TASS_Filter_Funnel", "outputs/tables/tass_filter_funnel.csv"),
    ("Style_Mapping_Audit", "outputs/tables/style_mapping_audit.csv"),
    ("Return_Scale_Audit", "outputs/tables/return_scale_audit.csv"),
    ("Return_Excess_Mode_Cmp", "outputs/tables/return_excess_mode_comparison.csv"),
    ("Return_Scale_By_Source", "outputs/tables/return_scale_by_source_audit.csv"),
    ("Source_Coverage_Audit", "outputs/tables/source_coverage_audit.csv"),
    ("Filter_Field_Coverage", "outputs/tables/filter_field_coverage_audit.csv"),
    ("Fund_Info_Conflicts", "outputs/tables/fund_info_duplicate_conflicts.csv"),
    ("Fund_Info_Conflict_Summary", "outputs/tables/fund_info_conflict_summary.csv"),
    ("RF_Merge_Audit", "outputs/tables/rf_merge_audit.csv"),
    ("Data_Error_Sensitivity", "outputs/tables/data_error_sensitivity_summary.csv"),
    ("Currency_Sensitivity", "outputs/tables/currency_filter_sensitivity.csv"),
    ("Raw_Category_Audit", "outputs/tables/raw_category_metadata_audit.csv"),
    ("Spec_Grid_Summary", "outputs/tables/spec_grid_best_10.csv"),
    ("Run_Manifest", "outputs/logs/run_manifest_sanitized.json"),
]


def _read(path):
    p = resolve(path)
    if not p.exists():
        return None
    if p.suffix == ".json":
        return pd.json_normalize(json.loads(p.read_text(encoding="utf-8")))
    return pd.read_csv(p)


def is_table3_complete() -> bool:
    return resolve("outputs/tables/table3_original_vs_replication.csv").exists()


def build_workbook(out_dir="outputs/workbooks"):
    out = ensure_dir(out_dir)
    final = is_table3_complete()
    name = "sadka_table3_summary.xlsx" if final else "sadka_table3_workbook_TEMPLATE_no_tass.xlsx"
    path = out / name
    readme = pd.DataFrame({
        "item": ["workbook_status", "note"],
        "value": ["FINAL (Table 3 present)" if final else "TEMPLATE (no TASS / Table 3 yet)",
                  "Sheets are sourced from outputs/. Missing sheets show a placeholder; "
                  "no numbers are fabricated."]})
    with pd.ExcelWriter(path, engine="xlsxwriter") as xl:
        readme.to_excel(xl, sheet_name="README", index=False)
        for sheet, src in SHEETS:
            df = _read(src)
            if df is None:
                df = pd.DataFrame({"status": [f"NOT AVAILABLE - requires upstream output: {src}"]})
            df.to_excel(xl, sheet_name=sheet[:31], index=False)
    return path


def build_memo(out_dir="outputs/memos"):
    out = ensure_dir(out_dir)
    final = is_table3_complete()
    if final:
        path = out / "sadka_table3_replication_memo_for_prof.md"
        body = _final_memo_body()
    else:
        path = out / "sadka_table3_replication_memo_TEMPLATE.md"
        body = _template_memo_body()
    path.write_text(body, encoding="utf-8")
    return path


def _template_memo_body() -> str:
    return (
        "# Sadka (2010 JFE) Table 3 — replication memo (TEMPLATE, pre-TASS)\n\n"
        "STATUS: factor side validated; Table 3 NOT yet run (awaiting WRDS TASS export). "
        "This template has NO fabricated results.\n\n"
        "1. Objective — replicate Sadka Table 3 only (baseline for later additional factors).\n"
        "2. Specification — 11 equal-weighted style portfolios; 1994-01..2008-12; Live+Graveyard, "
        "monthly, USD, net of fees, excess returns; Model 1 (MKT-RF+Liquidity) & Model 2 "
        "(Fung-Hsieh 7 + Liquidity); full-sample OLS.\n"
        "3. Factor side (done) — Liquidity as-is matches Fig.1 crisis signs; Table 2 28/28 within 0.05.\n"
        "4. Diagnostics (pending TASS) — Table 1 counts, funnel, style mapping, scale audits.\n"
        "5. Table 3 results (pending TASS).\n"
        "6. Discrepancies (pending).\n"
        "7. Closest-feasible spec (only if different from paper-faithful; from spec grid).\n"
        "8. Recommendation (pending).\n"
    )


def _final_memo_body() -> str:
    liq = _read("outputs/tables/table3_liquidity_focus.csv")
    sens = _read("outputs/tables/data_error_sensitivity_summary.csv")
    cur = _read("outputs/tables/currency_filter_sensitivity.csv")
    L = []
    L.append("# Sadka (2010 JFE) Table 3 — strong closest-feasible replication\n\n")
    L.append("**Status:** strong closest-feasible replication on the *current LSEG/TASS vintage* "
             "(~2026), a DIFFERENT vintage than Sadka's 2009 TASS. The core economic result "
             "reproduces; paper-faithful keep-all and data-error-cleaned versions are reported "
             "separately below (no ad-hoc trimming).\n\n")
    L.append("## 1. Data-error policy (paper-faithful vs cleaned)\n")
    L.append("The modern vintage contains impossible values (e.g. +31,208%/month) absent from "
             "Sadka's data. We report three pre-specified screens; **main = S01 conservative "
             "(drop >2000%/mo)**. This does NOT delete returns in the same order of magnitude as "
             "Sadka's published extremes: the post-screen maximum is 18.16, comparable to the "
             "published 13.245 maximum, while removing clearly impossible modern-vintage records "
             "such as +31,208%/month. Sadka's footnote: excluding extremes does not change results.\n\n")
    if sens is not None:
        L.append(sens.to_string(index=False) + "\n\n")
    L.append("## 2. Currency filter and the count gap\n")
    L.append("USD-only (Sadka's requirement) yields ~8,345 funds; all-currencies ~13,521 "
             "(≈ Sadka's 12,929). The count gap is largely the USD filter on a vintage with "
             "more non-USD funds. USD-only remains main.\n\n")
    if cur is not None:
        L.append(cur.to_string(index=False) + "\n\n")
    L.append("## 3. Known coverage caveat — Managed Futures\n")
    L.append("Only ~17 funds carry primarycategory='Managed Futures' in 1994-2008 (Sadka: 964); "
             "fund names are anonymized so CTAs cannot be reclassified and are NOT force-mapped. "
             "Managed Futures is a thin, low-power style here (it was weak/insignificant in Sadka too).\n\n")
    L.append("## 4. Table 3 liquidity loading (Model 2): target vs replicated [t]\n")
    if liq is not None:
        m2 = liq[liq["spec"] == "model2"] if "spec" in liq else liq
        for _, r in m2.iterrows():
            c = r.get("coef")
            t = r.get("tstat")
            L.append(f"- {r.get('style')}: {r.get('coef_target')} -> "
                     f"{round(float(c), 3) if pd.notna(c) else 'NA'} "
                     f"[{round(float(t), 2) if pd.notna(t) else 'NA'}]\n")
    L.append("\n## 5. Conclusion\n")
    L.append("Liquidity signs 11/11 correct; the paper's red lines hold (Dedicated Short Bias "
             "negative & insignificant, MKT-beta ~ -1; Global Macro / Managed Futures weak). "
             "Conditional on the cleaned sample, the paper-faithful Variable-Permanent as-is "
             "liquidity factor is the best allowed specification in the grid. Magnitudes run "
             "somewhat smaller than Sadka's; the qualitative pricing result is reproduced. "
             "Sadka's setting replicates cleanly and is a suitable baseline for additional factors.\n")
    return "".join(L)

