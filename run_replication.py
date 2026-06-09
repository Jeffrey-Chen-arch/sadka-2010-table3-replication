"""Sadka (2010, JFE) Table III - closest-feasible replication: one-command pipeline.

Steps: 00 inventory | 01 liquidity | 02 factors+Table2 | 03 TASS clean | 04 style portfolios
       05 Table 3 | 06 Table 1 + Fig 2 | 07 spec grid | 08 workbook+memo | 09 sensitivity

  python run_replication.py --through 09      # run steps 0..N
  python run_replication.py --step 05         # one step
Data-dependent steps print a clear BLOCKED message if raw inputs under data/raw are absent.
"""
import argparse
import sys

import json
from pathlib import Path
from sadka.core import sha256_file
from sadka.core import ensure_dir, project_root, resolve
from sadka.core import write_run_manifest
import pandas as pd
from sadka.core import load_config
from sadka.liquidity import (  # noqa: E402
    SAMPLE_END, SAMPLE_START, CRISIS_MONTHS,
    crisis_signs_negative, load_sadka_liquidity_xlsx, make_liquidity_variant,
)
import numpy as np
from sadka.factors import build_term_credit, load_fama_french, load_hsieh_tf
from sadka.factors import TABLE2_FACTORS, build_factor_panel
from sadka.core import pvalue_from_corr
from sadka.tass import map_styles_series
from sadka.tass import clean_tass
from sadka.tass import ingest_manual_exports
from sadka.analysis import build_equal_weight_style_returns
from sadka.analysis import compare_to_targets, score_spec
from sadka.analysis import run_table3
from sadka.analysis import figure2_data, plot_figure2
from sadka.analysis import (
    compare_style_counts_to_targets, compute_monthly_cross_section_stats,
    compute_table1_style_counts, compute_table1_year_counts,
)
from sadka.core import load_yaml
from sadka.analysis import DEFAULT_GRID, run_spec_grid
from sadka.reporting import build_memo, build_workbook, is_table3_complete
import copy

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: F401

CFG = "config/spec_table3_main.yaml"
GRID = "config/spec_grid_ambiguities.yaml"

# ===================== Step 00 =====================

"""Step 00 - Project + WRDS inventory.

Census local inputs (with full SHA-256), attempt a WRDS tr_tass/tass schema inventory
(graceful failure without credentials/network), and write the run manifest.
"""

INPUT_CANDIDATES = {
    "liquidity_xlsx": "data/raw/liquidity/Sadka-LIQ-factors-1983-2012-WRDS.xlsx",
    "fama_french_zip": "data/raw/external_factors/fama_french/FF3_CSV.zip",
    "hsieh_tf": "data/raw/external_factors/hsieh/TF-Fac.xls",
    "fred_DGS10": "data/raw/external_factors/fred/DGS10.csv",
    "fred_DBAA": "data/raw/external_factors/fred/DBAA.csv",
    "fred_GS10": "data/raw/external_factors/fred/GS10.csv",
    "fred_BAA": "data/raw/external_factors/fred/BAA.csv",
}

def census_inputs() -> dict:
    found = {}
    for key, rel in INPUT_CANDIDATES.items():
        p = resolve(rel)
        if p.exists():
            found[key] = {"path": rel, "bytes": p.stat().st_size, "sha256": sha256_file(p)}
        else:
            found[key] = {"path": rel, "present": False}
    # TASS manual exports (variable file names)
    tass_dir = resolve("data/raw/tass/manual_exports")
    tass_files = [f.name for f in tass_dir.glob("*") if f.is_file() and f.name != ".gitkeep"]
    found["tass_manual_exports"] = {"dir": "data/raw/tass/manual_exports", "files": tass_files}
    return found

def wrds_inventory(logs: Path) -> dict:
    """Attempt WRDS schema inventory; must fail gracefully."""
    status = {"attempted": True}
    try:
        import os
        import wrds  # noqa: F401
        username = os.getenv("WRDS_USERNAME")
        if not username:
            status.update(available=False, reason="WRDS_USERNAME not set; skipping connection")
            return status
        db = wrds.Connection(wrds_username=username)
        libs = db.list_libraries()
        found = {}
        for schema in ("tr_tass", "tass"):
            if schema in libs:
                found[schema] = db.list_tables(library=schema)
        (logs / "wrds_tr_tass_tables.json").write_text(
            json.dumps(found, indent=2, default=str), encoding="utf-8")
        status.update(available=True, schemas_found=list(found.keys()))
    except Exception as e:
        status.update(available=False, reason=f"{type(e).__name__}: {str(e)[:160]}")
    return status

def step00(config=CFG, grid=GRID):

    logs = ensure_dir("outputs/logs")
    inputs = census_inputs()
    (logs / "input_files_found.json").write_text(
        json.dumps(inputs, indent=2, default=str), encoding="utf-8")

    # dedicated full-hash record for the restricted liquidity file
    liq = inputs.get("liquidity_xlsx", {})
    if liq.get("sha256"):
        (logs / "liquidity_file_sha256.txt").write_text(
            f"Sadka-LIQ-factors-1983-2012-WRDS.xlsx  SHA256={liq['sha256']}\n", encoding="utf-8")

    wrds_status = wrds_inventory(logs)

    inventory = {
        "project_root_name": project_root().name,
        "inputs": inputs,
        "wrds": wrds_status,
    }
    (logs / "project_inventory.json").write_text(
        json.dumps(inventory, indent=2, default=str), encoding="utf-8")

    write_run_manifest("step00_inventory", extra={"wrds_available": wrds_status.get("available")})

    print("[Step 00] inventory complete.")
    print("  inputs present:", [k for k, v in inputs.items() if isinstance(v, dict) and v.get("sha256")])
    print("  TASS manual exports:", inputs["tass_manual_exports"]["files"] or "(none yet)")
    print("  WRDS:", wrds_status.get("available"), "-", wrds_status.get("reason", "ok"))

# ===================== Step 01 =====================

"""Step 01 - Prepare the Sadka liquidity factor (main spec: Variable-Permanent as-is)."""

def step01(config=CFG, grid=GRID):
    cfg = load_config(config)
    lcfg = cfg["liquidity"]

    src = resolve(lcfg["source_file"])
    if not src.exists():
        print(f"[Step 01] BLOCKED: liquidity file not found at {lcfg['source_file']}.")
        print("          Place Sadka-LIQ-factors-1983-2012-WRDS.xlsx in data/raw/liquidity/ "
              "(excluded from the committable zip for redistribution reasons). No output generated.")
        sys.exit(2)

    raw = load_sadka_liquidity_xlsx(lcfg["source_file"], lcfg["sheet_name"])
    panel_full = make_liquidity_variant(raw, lcfg["baseline_transform"])  # as_is
    panel = panel_full[(panel_full["month"] >= SAMPLE_START) & (panel_full["month"] <= SAMPLE_END)].reset_index(drop=True)

    # --- hard assertions ---
    assert len(panel) == 180, f"expected 180 months, got {len(panel)}"
    assert panel["month"].min() == SAMPLE_START and panel["month"].max() == SAMPLE_END
    assert panel["Liquidity"].notna().all(), "Liquidity has missing values"
    signs = crisis_signs_negative(panel)
    for m, v in signs.items():
        assert v < 0, f"crisis month {m} not negative: {v}"

    ensure_dir("data/processed")
    tables = ensure_dir("outputs/tables")
    figs = ensure_dir("outputs/figures")

    panel.to_parquet(resolve("data/processed/liquidity_main.parquet"), index=False)

    # key months (crisis + most-negative)
    km = panel[panel["month"].isin(CRISIS_MONTHS)][["month", "Liquidity", "Liquidity_raw"]].copy()
    km["label"] = "crisis"
    most_neg = panel.nsmallest(6, "Liquidity")[["month", "Liquidity", "Liquidity_raw"]].copy()
    most_neg["label"] = "most_negative"
    key = pd.concat([km, most_neg]).drop_duplicates("month").sort_values("month")
    key.to_csv(tables / "liquidity_key_months.csv", index=False)

    # summary stats
    summ = panel["Liquidity"].describe().to_frame("Liquidity").T
    summ["lag1_autocorr"] = panel["Liquidity"].autocorr(1)
    summ.to_csv(tables / "liquidity_summary_stats.csv")

    # Figure 1
    fig, ax = plt.subplots(figsize=(11, 4.2))
    ax.plot(panel["month"], panel["Liquidity"], color="#1f3b73", lw=1.1)
    ax.axhline(0, color="black", lw=0.6)
    for yr in range(1994, 2009):
        ax.axvline(pd.Timestamp(f"{yr}-01-01"), color="grey", ls=":", lw=0.4)
    for m in CRISIS_MONTHS:
        v = float(panel.set_index("month")["Liquidity"].get(m))
        ax.annotate(m.strftime("%Y-%m"), (m, v), textcoords="offset points",
                    xytext=(0, -14), ha="center", fontsize=7, color="firebrick")
    ax.set_title("Figure 1 (replication): liquidity innovations (Sadka permanent-variable, as-is)")
    ax.set_ylabel("Liquidity")
    fig.tight_layout()
    fig.savefig(figs / "figure1_liquidity_innovations_replication.png", dpi=130)
    plt.close(fig)

    print("[Step 01] liquidity_main.parquet:", len(panel), "months",
          panel["month"].min().date(), "->", panel["month"].max().date())
    print("  crisis-month signs (all must be < 0):")
    for m, v in signs.items():
        print(f"    {m}: {v:+.5f}")
    print("  lag1 autocorr:", round(panel["Liquidity"].autocorr(1), 3))
    print("  wrote liquidity_key_months.csv, liquidity_summary_stats.csv, figure1_*.png")

# ===================== Step 02 =====================

"""Step 02 - External factors + Table 2 reproduction (+ liquidity-variant bake-off).

If DTERM/DCREDIT cannot be built, halt with BLOCKED status; do NOT claim Table 2 done.
"""

LIQ_TARGET_FACTORS = ["MKT-RF", "SMB", "DTERM", "DCREDIT", "PTFSBD", "PTFSFX", "PTFSCOM"]

def step02(config=CFG, grid=GRID):
    cfg = load_config(config)
    tables = ensure_dir("outputs/tables")
    logs = ensure_dir("outputs/logs")
    ensure_dir("data/processed")

    liq_path = resolve("data/processed/liquidity_main.parquet")
    if not liq_path.exists():
        print("[Step 02] BLOCKED: liquidity_main.parquet missing. Run Step 01 first.")
        sys.exit(2)
    ff_zip = resolve("data/raw/external_factors/fama_french/FF3_CSV.zip")
    hsieh_xls = resolve("data/raw/external_factors/hsieh/TF-Fac.xls")
    miss = [str(p.name) for p in [ff_zip, hsieh_xls] if not p.exists()]
    if miss:
        print(f"[Step 02] BLOCKED: missing raw factor inputs {miss} (excluded from committable zip).")
        print("          See data/raw/external_factors/ READMEs. No factor output generated.")
        sys.exit(2)
    liq_main = pd.read_parquet(liq_path)

    ff = load_fama_french()
    hsieh = load_hsieh_tf()
    term_credit, tc_source = build_term_credit()

    # ---- BLOCKED gate ----
    if term_credit is None or len(term_credit) < 180:
        msg = ("BLOCKED: DTERM/DCREDIT unavailable. Provide DGS10.csv/DBAA.csv (preferred) "
               "or GS10.csv/BAA.csv (fallback) in data/raw/external_factors/fred/. "
               "Table 2 NOT replicated; no final comparison written.")
        (logs / "step02_BLOCKED.txt").write_text(msg + "\n", encoding="utf-8")
        # partial audit (no DTERM/DCREDIT) so the cause is visible
        part = liq_main.merge(ff, on="month").merge(hsieh, on="month")
        cols = [c for c in ["MKT-RF", "SMB", "PTFSBD", "PTFSFX", "PTFSCOM", "Liquidity"] if c in part]
        part[cols].corr().to_csv(tables / "table2_PARTIAL_audit_no_term_credit.csv")
        print(msg)
        sys.exit(2)

    # ---- factor panel ----
    panel = build_factor_panel(liq_main, ff, hsieh, term_credit)
    panel.to_parquet(resolve("data/processed/factors_main.parquet"), index=False)

    # ---- factor summary stats ----
    summ = panel[TABLE2_FACTORS + ["RF"]].agg(["mean", "std", "min", "max"]).T
    summ.to_csv(tables / "factor_summary_stats.csv")

    # ---- factor scale audit (units & scale decisions for Table 3 coefficients) ----
    meta = {
        "MKT-RF": ("Ken French 3-factor", "percent", "decimal", "divided by 100",
                   "decimal returns; market beta comparable to paper"),
        "SMB": ("Ken French 3-factor", "percent", "decimal", "divided by 100", "decimal returns"),
        "RF": ("Ken French 3-factor", "percent", "decimal", "divided by 100",
               "excess-return construction ONLY; not a Table 3 RHS factor"),
        "DTERM": ("FRED GS10 (monthly avg)", "percent yield", "percentage points",
                  "diff of yield; NOT divided by 100", "loading is return-per-pp; matches paper"),
        "DCREDIT": ("FRED BAA-GS10 (monthly avg)", "percent yield spread", "percentage points",
                    "diff of spread; NOT divided by 100", "loading is return-per-pp; matches paper"),
        "PTFSBD": ("Hsieh TF-Fac", "decimal return", "decimal (as-read)", "as-read; NOT divided by 100",
                   "dividing by 100 would inflate PTFS coefficients 100x"),
        "PTFSFX": ("Hsieh TF-Fac", "decimal return", "decimal (as-read)", "as-read; NOT divided by 100",
                   "dividing by 100 would inflate PTFS coefficients 100x"),
        "PTFSCOM": ("Hsieh TF-Fac", "decimal return", "decimal (as-read)", "as-read; NOT divided by 100",
                    "dividing by 100 would inflate PTFS coefficients 100x"),
        "Liquidity": ("WRDS Variable-Permanent", "innovation level", "as-is", "as-is; no AR/flip/scale",
                      "small magnitude -> large betas (~0.4-1.5) as in paper"),
    }
    audit = pd.DataFrame([
        {"factor": f, "source": m[0], "raw_unit": m[1], "final_unit": m[2],
         "std_1994_2008": round(float(panel[f].std()), 6),
         "scale_decision": m[3], "coefficient_implication": m[4]}
        for f, m in meta.items()
    ])
    audit.to_csv(tables / "factor_scale_audit.csv", index=False)

    # ---- Table 2 correlations (replication) ----
    corr = panel[TABLE2_FACTORS].corr()
    corr.to_csv(tables / "table2_factor_correlations_replication.csv")

    targets = pd.read_csv(resolve("data/benchmarks/sadka_table2_corr_targets.csv"))
    rows = []
    for _, t in targets.iterrows():
        r, c = t["row_factor"], t["col_factor"]
        rep = float(corr.loc[r, c]) if (r in corr.index and c in corr.columns) else np.nan
        rows.append({
            "row_factor": r, "col_factor": c,
            "corr_target": t["corr_target"], "corr_rep": round(rep, 4),
            "diff": round(rep - t["corr_target"], 4), "abs_diff": round(abs(rep - t["corr_target"]), 4),
            "sign_match": bool(np.sign(rep) == np.sign(t["corr_target"]) or abs(t["corr_target"]) < 0.005),
            "within_0p05": bool(abs(rep - t["corr_target"]) <= 0.05),
            "pvalue_rep_n180": round(pvalue_from_corr(rep, 180), 4),
        })
    diff = pd.DataFrame(rows)
    diff.to_csv(tables / "table2_factor_correlations_diff.csv", index=False)

    # ---- liquidity-variant bake-off ----
    raw_liq = load_sadka_liquidity_xlsx(cfg["liquidity"]["source_file"], cfg["liquidity"]["sheet_name"])
    factor_only = panel[["month"] + LIQ_TARGET_FACTORS]
    liq_targets = targets[targets["row_factor"] == "Liquidity"].set_index("col_factor")["corr_target"]
    bake = []
    for variant in ["as_is", "flipped", "ar3_resid", "ar3_resid_neg"]:
        v = make_liquidity_variant(raw_liq, variant)
        v = v[(v["month"] >= SAMPLE_START) & (v["month"] <= SAMPLE_END)]
        merged = v[["month", "Liquidity"]].merge(factor_only, on="month")
        signs = {m.strftime("%Y-%m"): float(v.set_index("month")["Liquidity"].get(m, np.nan)) for m in CRISIS_MONTHS}
        crisis_pass = all((s is not None and s < 0) for s in signs.values())
        cors = {f: float(merged["Liquidity"].corr(merged[f])) for f in LIQ_TARGET_FACTORS}
        rmse = float(np.sqrt(np.mean([(cors[f] - liq_targets[f]) ** 2 for f in LIQ_TARGET_FACTORS])))
        bake.append({
            "variant": variant, "crisis_signs_pass": crisis_pass,
            "corr_liq_dcredit": round(cors["DCREDIT"], 4), "corr_liq_mktrf": round(cors["MKT-RF"], 4),
            "corr_liq_ptfsbd": round(cors["PTFSBD"], 4), "corr_liq_ptfsfx": round(cors["PTFSFX"], 4),
            "corr_liq_ptfscom": round(cors["PTFSCOM"], 4), "table2_corr_rmse": round(rmse, 4),
        })
    bake = pd.DataFrame(bake)
    # MAIN spec is as_is (paper-faithful: treat the WRDS file as the final factor).
    # AR(3) is diagnostic; it only displaces as_is if "clearly better": rmse lower by >0.02.
    passing = bake[bake["crisis_signs_pass"]]
    lowest_rmse = passing.sort_values("table2_corr_rmse")["variant"].iloc[0] if len(passing) else None
    as_is_rmse = float(bake.loc[bake["variant"] == "as_is", "table2_corr_rmse"].iloc[0])
    best_rmse = float(bake.loc[bake["variant"] == lowest_rmse, "table2_corr_rmse"].iloc[0]) if lowest_rmse else None
    ar3_clearly_better = bool(lowest_rmse != "as_is" and best_rmse is not None and (as_is_rmse - best_rmse) > 0.02)

    def verdict(r):
        if not r["crisis_signs_pass"]:
            return "FAIL crisis signs"
        if r["variant"] == "as_is":
            return "MAIN (paper-faithful as-is)"
        if r["variant"] == lowest_rmse:
            return "lowest Table2 RMSE (diagnostic; not clearly better)"
        return "diagnostic (passes signs)"
    bake["verdict"] = bake.apply(verdict, axis=1)
    bake.to_csv(tables / "liquidity_variant_bakeoff.csv", index=False)

    write_run_manifest("step02_factors", extra={
        "term_credit_source": tc_source,
        "table2_pairs_within_0.05": int(diff["within_0p05"].sum()),
        "table2_pairs_total": int(len(diff)),
        "table2_sign_matches": int(diff["sign_match"].sum()),
        "liquidity_main_spec": "as_is",
        "bakeoff_lowest_rmse_variant": lowest_rmse,
        "ar3_clearly_better_than_as_is": ar3_clearly_better,
    })

    print(f"[Step 02] factors_main.parquet built (term_credit_source={tc_source}).")
    print(f"  Table 2: {int(diff['within_0p05'].sum())}/{len(diff)} pairs within 0.05; "
          f"{int(diff['sign_match'].sum())}/{len(diff)} sign matches.")
    key = diff[diff.apply(lambda r: (r['row_factor'], r['col_factor']) in
              [('Liquidity', 'DCREDIT'), ('Liquidity', 'MKT-RF'), ('DCREDIT', 'DTERM'),
               ('DCREDIT', 'MKT-RF')], axis=1)]
    print(key[["row_factor", "col_factor", "corr_target", "corr_rep", "abs_diff"]].to_string(index=False))
    print("  Bake-off:")
    print(bake[["variant", "crisis_signs_pass", "corr_liq_dcredit", "table2_corr_rmse", "verdict"]].to_string(index=False))

# ===================== Step 03 =====================

"""Step 03 - Standardize + clean TASS manual exports into a fund-month panel.

Requires WRDS TASS exports in data/raw/tass/manual_exports/ (see that folder's README).
Exits cleanly (no mock data) if none are present.
"""

def _w(res, key, tables, name):
    if key in res and hasattr(res[key], "to_csv"):
        res[key].to_csv(tables / name, index=False)

def step03(config=CFG, grid=GRID):
    cfg = load_config(config)
    tables = ensure_dir("outputs/tables")
    ensure_dir("data/interim")
    ensure_dir("data/processed")

    returns_std, info_std, log, info_conflicts = ingest_manual_exports()
    if len(returns_std) == 0:
        print("[Step 03] No TASS returns found in data/raw/tass/manual_exports/.")
        print("          Add WRDS exports (see data/raw/tass/README.md), then re-run.")
        if len(log):
            print("          files seen:", log.to_dict("records"))
        sys.exit(0)

    returns_std.to_parquet(resolve("data/interim/tass_returns_standardized.parquet"), index=False)
    info_std.to_parquet(resolve("data/interim/tass_fund_info_standardized.parquet"), index=False)

    # fund_info conflicts (flag real style conflicts on the canonical-mapped style)
    n_style_conf = 0
    nonstyle_conflicts = {}
    if len(info_conflicts):
        ic = info_conflicts.copy()
        ic["mapped_style"] = map_styles_series(ic["investment_style_raw"], cfg["styles"]["style_mapping_variant"])
        ic.to_csv(tables / "fund_info_duplicate_conflicts.csv", index=False)
        # classify conflicts by field (canonical style is the only hard stop)
        fields = [("canonical_style", "mapped_style", "stop"),
                  ("currency", "currency", "hard_warning"),
                  ("reporting_frequency", "reporting_frequency", "hard_warning"),
                  ("net_of_fees_flag", "net_of_fees_flag", "warning"),
                  ("live_graveyard_status", "live_graveyard_status", "warning")]
        summary = []
        for label, col, sev in fields:
            n = int((ic.groupby("fund_id")[col].nunique(dropna=True) > 1).sum()) if col in ic.columns else 0
            summary.append({"conflict_field": label, "n_fund_ids": n, "severity": sev})
            if label == "canonical_style":
                n_style_conf = n
            else:
                nonstyle_conflicts[label] = n
        pd.DataFrame(summary).to_csv(tables / "fund_info_conflict_summary.csv", index=False)
        if (n_style_conf > 0 and cfg.get("fund_info_conflicts", {})
                .get("canonical_style_conflict_behavior", "stop") == "stop"):
            print(f"[Step 03] STOP: {n_style_conf} fund_id(s) map to CONFLICTING canonical styles "
                  "(see fund_info_duplicate_conflicts.csv). Style determines portfolio membership; "
                  "resolve before the main replication.")
            sys.exit(7)
        for label, n in nonstyle_conflicts.items():
            if n > 0:
                print(f"[Step 03] WARNING: {n} fund_id(s) have conflicting '{label}' across exports "
                      "(see fund_info_conflict_summary.csv).")

    ff = load_fama_french()
    res = clean_tass(returns_std, info_std, ff, cfg)

    for key, name in [
        ("funnel", "tass_filter_funnel.csv"), ("source_counts", "tass_source_counts.csv"),
        ("source_coverage_audit", "source_coverage_audit.csv"),
        ("style_mapping_audit", "style_mapping_audit.csv"), ("unmapped_styles", "unmapped_styles.csv"),
        ("duplicate_fund_month_conflicts", "duplicate_fund_month_conflicts.csv"),
        ("return_sentinel_filter_audit", "return_sentinel_filter_audit.csv"),
        ("filter_field_coverage_audit", "filter_field_coverage_audit.csv"),
        ("return_scale_audit", "return_scale_audit.csv"),
        ("return_scale_by_source_audit", "return_scale_by_source_audit.csv"),
        ("data_error_filter_audit", "data_error_filter_audit.csv"),
        ("return_excess_mode_comparison", "return_excess_mode_comparison.csv"),
        ("rf_merge_audit", "rf_merge_audit.csv"),
    ]:
        _w(res, key, tables, name)

    fe = res.get("fatal_error")
    if fe == "duplicate_fund_month_conflicts":
        print(f"[Step 03] STOP: {len(res['duplicate_fund_month_conflicts'])} non-exact duplicate "
              "fund-month conflicts. See duplicate_fund_month_conflicts.csv.")
        sys.exit(4)
    if fe == "missing_rf_after_merge":
        print("[Step 03] STOP: RF missing after merge. See rf_merge_audit.csv.")
        sys.exit(6)
    if fe == "return_scale_inconsistent_across_sources":
        print("[Step 03] STOP: return scale differs across sources (see return_scale_by_source_audit.csv). "
              "Refusing global normalization. Override via returns.scale_inconsistency_behavior if intended.")
        sys.exit(8)
    if fe and fe.endswith("_present_but_unrecognized"):
        print(f"[Step 03] STOP: paper-required field '{fe.replace('_present_but_unrecognized', '')}' is "
              "present but no values were recognized (see filter_field_coverage_audit.csv). "
              "Extend the recognizer/aliases or fix the export before the main replication.")
        sys.exit(9)

    if res["unmapped_share"] > cfg["styles"]["stop_if_unmapped_share_exceeds"]:
        print(f"[Step 03] STOP: unmapped style share {res['unmapped_share']:.3f} > threshold. "
              "Inspect unmapped_styles.csv; consider expanded_alias_map.")
        sys.exit(3)

    # non-fatal warnings
    cov = res["source_coverage_audit"].iloc[0]
    if not (cov["has_live"] and cov["has_graveyard"]):
        print(f"[Step 03] WARNING: Live/Graveyard not both present -> NOT paper-faithful "
              f"(has_live={cov['has_live']}, has_graveyard={cov['has_graveyard']}).")
    if not res.get("paper_faithful_fields", False):
        print("[Step 03] WARNING: currency/reporting_frequency not applied -> closest-feasible, not paper-faithful.")
    if not res.get("net_of_fees_applied", False):
        print("[Step 03] NOTE: net-of-fees flag not applied; relying on TASS ROR being net of fees (assumption).")
    if res.get("scale_inconsistent_across_sources"):
        print("[Step 03] WARNING: return scale differs across sources (see return_scale_by_source_audit.csv).")
    if n_style_conf > 0:
        print(f"[Step 03] WARNING: {n_style_conf} fund_id(s) map to CONFLICTING canonical styles "
              "(see fund_info_duplicate_conflicts.csv).")

    fm = res["fund_month"]
    fm.to_parquet(resolve("data/processed/tass_fund_month_returns.parquet"), index=False)
    write_run_manifest("step03_tass", extra={
        "fund_month_rows": int(len(fm)), "unique_funds": int(fm["fund_id"].nunique()),
        "unmapped_share": round(res["unmapped_share"], 4), "styles_present": res["styles_present"],
        "has_live": bool(cov["has_live"]), "has_graveyard": bool(cov["has_graveyard"]),
        "paper_faithful_fields": bool(res.get("paper_faithful_fields", False)),
        "style_conflict_funds": n_style_conf,
        "nonstyle_info_conflicts": nonstyle_conflicts,
    })
    print(f"[Step 03] fund-month panel: {len(fm)} rows, {fm['fund_id'].nunique()} funds, "
          f"{fm['month'].nunique()} months, {len(res['styles_present'])}/11 styles.")
    print(res["funnel"].to_string(index=False))

# ===================== Step 04 =====================

"""Step 04 - Equal-weighted monthly style portfolios (Table 3 dependent variables)."""

def step04(config=CFG, grid=GRID):
    load_config(config)
    tables = ensure_dir("outputs/tables")
    ensure_dir("data/processed")

    fm_path = resolve("data/processed/tass_fund_month_returns.parquet")
    if not fm_path.exists():
        print("[Step 04] Missing tass_fund_month_returns.parquet. Run Step 03 first.")
        sys.exit(0)
    fm = pd.read_parquet(fm_path)

    sp = build_equal_weight_style_returns(fm, ret_col="ret_excess")
    sp.to_parquet(resolve("data/processed/style_portfolio_returns.parquet"), index=False)

    summ = (sp.groupby("style")
              .agg(months=("month", "nunique"), mean_ret=("style_ret", "mean"),
                   std_ret=("style_ret", "std"), avg_n_funds=("n_funds", "mean"))
              .reset_index())
    summ.to_csv(tables / "style_portfolio_summary.csv", index=False)
    sp.pivot(index="month", columns="style", values="n_funds").to_csv(tables / "style_monthly_n_funds.csv")

    print(f"[Step 04] style portfolios: {sp['style'].nunique()} styles, "
          f"{sp['month'].nunique()} months.")
    print(summ.to_string(index=False))

# ===================== Step 05 =====================

"""Step 05 - Table 3 time-series regressions + comparison to published targets."""

def step05(config=CFG, grid=GRID):
    cfg = load_config(config)
    tables = ensure_dir("outputs/tables")

    sp_path = resolve("data/processed/style_portfolio_returns.parquet")
    fac_path = resolve("data/processed/factors_main.parquet")
    if not sp_path.exists():
        print("[Step 05] Missing style_portfolio_returns.parquet. Run Step 04 first.")
        sys.exit(0)
    if not fac_path.exists():
        print("[Step 05] Missing factors_main.parquet. Run Step 02 first.")
        sys.exit(0)

    sp = pd.read_parquet(sp_path)
    factors = pd.read_parquet(fac_path)
    tstat_type = cfg["regression"]["tstat_type_main"]

    rep = run_table3(sp[["month", "style", "style_ret"]], factors, tstat_type=tstat_type)
    rep.to_csv(tables / "table3_replicated_long.csv", index=False)
    (rep.pivot_table(index=["style", "spec"], columns="term", values="coef")
        .to_csv(tables / "table3_replicated_wide.csv"))

    rep[["style", "spec", "nobs"]].drop_duplicates().to_csv(
        tables / "table3_nobs_by_style_spec.csv", index=False)

    target = pd.read_csv(resolve(cfg["comparison"]["target_file"]))
    comp = compare_to_targets(rep, target)
    comp.to_csv(tables / "table3_original_vs_replication.csv", index=False)

    missing = comp[comp["coef"].isna()]
    if len(missing) > 0:
        missing.to_csv(tables / "table3_missing_cells.csv", index=False)
        print(f"[Step 05] STOP: {len(missing)} Table 3 target cells missing "
              "(see table3_missing_cells.csv). Check styles/months before reporting.")
        sys.exit(5)

    liq = comp[comp["term"] == "Liquidity"][
        ["style", "spec", "coef_target", "coef", "tstat_target", "tstat",
         "same_coef_sign", "sig_match_5pct"]]
    liq.to_csv(tables / "table3_liquidity_focus.csv", index=False)

    score = score_spec(comp)
    (resolve("outputs/logs") / "table3_score.json").write_text(json.dumps(score, indent=2), encoding="utf-8")
    write_run_manifest("step05_table3", extra={"tstat_type": tstat_type, **{k: round(v, 4) for k, v in score.items()}})

    print(f"[Step 05] Table 3 done ({tstat_type}).")
    print("  liquidity sign-match rate:", round(score["liq_sign_match_rate"], 3),
          "| liquidity sig-match rate:", round(score["liq_sig_match_rate"], 3))
    print("  liquidity coef MAE:", round(score["liq_coef_mae"], 4))

# ===================== Step 06 =====================

"""Step 06 - Table 1 sample diagnostics + Figure 2 (style return vs liquidity beta)."""

def step06(config=CFG, grid=GRID):
    load_config(config)
    tables = ensure_dir("outputs/tables")
    figs = ensure_dir("outputs/figures")

    fm_path = resolve("data/processed/tass_fund_month_returns.parquet")
    if not fm_path.exists():
        print("[Step 06] Missing tass_fund_month_returns.parquet. Run Step 03 first.")
        sys.exit(0)
    fm = pd.read_parquet(fm_path)

    # ---- Table 1 ----
    style_counts = compute_table1_style_counts(fm)
    overall = pd.DataFrame([{"style": "Overall", "n_rep": fm["fund_id"].nunique()}])
    counts = pd.concat([style_counts, overall], ignore_index=True)
    t1_targets = pd.read_csv(resolve("data/benchmarks/sadka_table1_style_targets.csv"))
    compare_style_counts_to_targets(counts, t1_targets).to_csv(
        tables / "table1_style_count_diff.csv", index=False)

    fm_year = fm.copy()
    fm_year["year"] = fm_year["month"].dt.year
    yearN = compute_table1_year_counts(fm)
    yearStats = compute_monthly_cross_section_stats(fm_year, ["year"])
    yearN.merge(yearStats, on="year", how="left").to_csv(
        tables / "table1_panel_a_by_year_replication.csv", index=False)

    styleStats = compute_monthly_cross_section_stats(fm, ["style"])
    style_counts.merge(styleStats, on="style", how="left").to_csv(
        tables / "table1_panel_b_by_style_replication.csv", index=False)

    overallStats = compute_monthly_cross_section_stats(fm, [])
    overallStats.insert(0, "n_rep", fm["fund_id"].nunique())
    overallStats.to_csv(tables / "table1_panel_c_overall_replication.csv", index=False)

    # ---- Figure 2 (needs style returns + factor panel) ----
    sp_path = resolve("data/processed/style_portfolio_returns.parquet")
    fac_path = resolve("data/processed/factors_main.parquet")
    fig2_done = False
    if sp_path.exists() and fac_path.exists():
        sp = pd.read_parquet(sp_path)
        factors = pd.read_parquet(fac_path)
        fig2 = figure2_data(sp, factors)
        fig2.to_csv(tables / "figure2_style_return_vs_liquidity_beta.csv", index=False)
        plot_figure2(fig2, figs / "figure2_style_return_vs_liquidity_beta.png")
        fig2_done = True

    write_run_manifest("step06_diagnostics", extra={
        "overall_n": int(fm["fund_id"].nunique()),
        "styles_present": int(fm["style"].nunique()), "figure2_built": fig2_done,
    })
    print(f"[Step 06] Table 1 diagnostics done. Overall N = {fm['fund_id'].nunique()}; "
          f"Figure 2 {'built' if fig2_done else 'skipped (need Steps 04+02)'}.")

# ===================== Step 07 =====================

"""Step 07 - run the pre-specified ambiguity spec grid (config-driven; no mock results)."""

def step07(config=CFG, grid=GRID):
    cfg = load_config(config)
    tables = ensure_dir("outputs/tables")
    logs = ensure_dir("outputs/logs")

    fm_path = resolve("data/processed/tass_fund_month_returns.parquet")
    if not fm_path.exists():
        print("[Step 07] Missing tass_fund_month_returns.parquet (run Step 03). "
              "Spec grid not run; no mock results produced.")
        sys.exit(0)
    fund_month = pd.read_parquet(fm_path)
    targets = pd.read_csv(resolve(cfg["comparison"]["target_file"]))

    grid_cfg = load_yaml(grid)
    grid = grid_cfg.get("implemented_grid", DEFAULT_GRID)
    allowed = grid_cfg.get("allowed_main_liquidity_variants", ["as_is"])

    scores, best_allowed, best_any = run_spec_grid(
        fund_month, targets, liquidity_path=cfg["liquidity"]["source_file"],
        grid=grid, allowed_main_liquidity_variants=tuple(allowed))
    scores.to_csv(tables / "spec_grid_scores.csv", index=False)

    ok = scores[scores.get("status") == "ok"].copy() if "status" in scores else scores
    if len(ok):
        ok.sort_values("liq_coef_mae").head(10).to_csv(tables / "spec_grid_best_10.csv", index=False)
        focus = ["return_excess_mode", "style_mapping_variant", "liquidity_variant",
                 "term_credit_source", "tstat_type", "tier", "is_paper_faithful", "is_allowed_main",
                 "liq_coef_mae", "liq_tstat_mae", "liq_sign_match_rate", "liq_sig_match_rate"]
        ok[[c for c in focus if c in ok.columns]].to_csv(tables / "spec_grid_liquidity_focus.csv", index=False)

    # best_spec / best_allowed may ONLY be an allowed (non-diagnostic) spec
    (logs / "best_allowed_spec.json").write_text(json.dumps(best_allowed, indent=2, default=str), encoding="utf-8")
    (logs / "best_any_diagnostic_spec.json").write_text(json.dumps(best_any, indent=2, default=str), encoding="utf-8")
    (logs / "best_spec.json").write_text(json.dumps(best_allowed, indent=2, default=str), encoding="utf-8")
    (logs / "spec_grid_manifest.json").write_text(json.dumps({
        "n_specs": int(len(scores)), "n_ok": int(len(ok)),
        "allowed_main_liquidity_variants": allowed,
        "rule": "CONDITIONAL ON THE ACTIVE DATA-ERROR-CLEANED SAMPLE: closest-feasible main "
                "only from allowed (non-diagnostic) specs; diagnostic liquidity variants "
                "(flipped/ar3_resid/...) reported but never main. Data-error policy is varied "
                "separately in data_error_sensitivity_summary.csv, not inside this grid.",
    }, indent=2), encoding="utf-8")

    write_run_manifest("step07_spec_grid", extra={"n_specs": int(len(scores)), "n_ok": int(len(ok))})
    print(f"[Step 07] spec grid: {len(scores)} specs, {len(ok)} ok. "
          f"Best ALLOWED main: {best_allowed.get('liquidity_variant') if best_allowed else None}; "
          f"best ANY (incl diagnostic): {best_any.get('liquidity_variant') if best_any else None}.")

# ===================== Step 08 =====================

"""Step 08 - build the Excel workbook + memo (template-aware; no mock results)."""

def step08(config=CFG, grid=GRID):
    load_config(config)

    wb = build_workbook()
    memo = build_memo()
    complete = is_table3_complete()
    write_run_manifest("step08_outputs", extra={
        "table3_complete": complete, "workbook": wb.name, "memo": memo.name})
    print(f"[Step 08] workbook: {wb.name} | memo: {memo.name} | table3_complete={complete}")

# ===================== Step 09 =====================

"""Step 09 - sensitivity package: data-error ceiling, currency filter, category metadata.

Quantifies the key caveats so paper-faithful vs closest-feasible are reported transparently.
No mock results. Reuses the same modules as the main pipeline.
"""

def _metrics(fund_month, factors, targets):
    sp = build_equal_weight_style_returns(fund_month, ret_col="ret_excess")
    rep = run_table3(sp[["month", "style", "style_ret"]], factors)
    comp = compare_to_targets(rep, targets)
    liq = comp[(comp["term"] == "Liquidity") & (comp["spec"] == "model2")]
    pos_sig = int(((liq["coef"] > 0) & (liq["tstat"].abs() > 1.96)).sum())
    def beta(style):
        r = liq[liq["style"] == style]
        return round(float(r["coef"].iloc[0]), 3) if len(r) else np.nan
    return {
        "overall_n": int(fund_month["fund_id"].nunique()),
        "fund_months": int(len(fund_month)),
        "max_ret_decimal": round(float(fund_month["ret_decimal"].max()), 3),
        "ConvArb_liq_m2": beta("Convertible Arbitrage"),
        "FixedIncArb_liq_m2": beta("Fixed Income Arbitrage"),
        "n_pos_sig_m2": pos_sig,
        "liq_sign_match_m2": round(float(liq["same_coef_sign"].mean()), 3),
        "liq_sig_match_m2": round(float(liq["sig_match_5pct"].mean()), 3),
        "liq_coef_mae_m2": round(float(liq["coef_abs_diff"].mean()), 3),
    }

def step09(config=CFG, grid=GRID):
    cfg = load_config(config)
    tables = ensure_dir("outputs/tables")
    returns_std, info_std, _log, _conf = ingest_manual_exports()
    ff = load_fama_french()
    factors = pd.read_parquet(resolve("data/processed/factors_main.parquet"))
    targets = pd.read_csv(resolve("data/benchmarks/sadka_table3_targets.csv"))

    def run(ceiling, info, label_extra=None):
        c = copy.deepcopy(cfg)
        c["returns"]["data_error_ceiling_decimal"] = ceiling
        res = clean_tass(returns_std, info, ff, c)
        m = _metrics(res["fund_month"], factors, targets)
        de = res.get("data_error_filter_audit")
        m["rows_dropped_ceiling"] = int(de["rows_dropped"].iloc[0]) if de is not None else 0
        return m

    # --- data-error sensitivity (USD-only main currency policy) ---
    rows = []
    for label, ceiling in [("S00_keep_all_except_sentinels", None),
                           ("S01_conservative_ceiling20", 20.0),
                           ("S02_aggressive_ceiling1", 1.0)]:
        m = run(ceiling, info_std)
        rows.append({"spec": label, "ceiling_decimal": ceiling, **m})
    pd.DataFrame(rows).to_csv(tables / "data_error_sensitivity_summary.csv", index=False)

    # --- currency-filter sensitivity (at the main ceiling) ---
    main_ceiling = cfg["returns"].get("data_error_ceiling_decimal")
    info_all = info_std.drop(columns=["currency"])  # drop -> USD filter skipped (all currencies)
    cur = [{"currency_policy": "USD_only (main)", **run(main_ceiling, info_std)},
           {"currency_policy": "all_currencies", **run(main_ceiling, info_all)}]
    pd.DataFrame(cur).to_csv(tables / "currency_filter_sensitivity.csv", index=False)

    # --- raw category metadata audit (names are anonymized -> structured only) ---
    info_std2 = info_std.copy()
    from sadka.tass import map_styles_series
    info_std2["strict"] = map_styles_series(info_std2["investment_style_raw"], "strict_11_only")
    info_std2["expanded"] = map_styles_series(info_std2["investment_style_raw"], "expanded_alias_map")
    cat = (info_std2.groupby("investment_style_raw")
           .agg(n_funds=("fund_id", "size"),
                n_usd=("currency", lambda s: int((s == "USD").sum())),
                mapped_strict=("strict", "first"), mapped_expanded=("expanded", "first"))
           .reset_index().sort_values("n_funds", ascending=False))
    cat["note"] = "fund names anonymized (Fund-N) -> cannot keyword-reclassify; no force-mapping"
    cat.to_csv(tables / "raw_category_metadata_audit.csv", index=False)

    print("[Step 09] sensitivity written: data_error_sensitivity_summary.csv, "
          "currency_filter_sensitivity.csv, raw_category_metadata_audit.csv")
    print(pd.DataFrame(rows)[["spec", "ceiling_decimal", "overall_n", "max_ret_decimal",
          "ConvArb_liq_m2", "FixedIncArb_liq_m2", "n_pos_sig_m2", "liq_sign_match_m2",
          "liq_coef_mae_m2"]].to_string(index=False))
    print()
    print(pd.DataFrame(cur)[["currency_policy", "overall_n", "n_pos_sig_m2", "liq_sign_match_m2"]].to_string(index=False))

STEPS = [step00, step01, step02, step03, step04, step05, step06, step07, step08, step09]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--through", type=int, default=9, help="run steps 0..N")
    ap.add_argument("--step", type=int, default=None, help="run a single step N")
    ap.add_argument("--config", default=CFG)
    ap.add_argument("--grid", default=GRID)
    a = ap.parse_args()
    todo = [a.step] if a.step is not None else list(range(0, a.through + 1))
    for i in todo:
        print(f"\n===== Step {i:02d} =====")
        STEPS[i](config=a.config, grid=a.grid)
    print("\n[run_replication] done.")


if __name__ == "__main__":
    main()
