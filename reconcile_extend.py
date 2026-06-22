"""Sadka (2010) Table III - Table 1 reconciliation + sample extension (single driver).

Reuses the same engine as run_replication.py (the `sadka` package). Two stages:

  python reconcile_extend.py reconcile   # 1994-2008: our sample vs Sadka Table 1 (USD + all-currency)
  python reconcile_extend.py extend      # extend to 2019-09; exact Sadka-LIQ Table 3 (capped at 2012-12)
  python reconcile_extend.py all         # both, then a summary workbook

Inputs (see README): pull TASS first with `python wrds_pull.py` (writes
data/raw/tass/manual_exports/tr_tass_returns_1994_latest.parquet + tr_tass_fundinfo_full.parquet).
External factors live under data/raw/external_factors/; Sadka liquidity under data/raw/liquidity/.
Outputs go to outputs/reconciliation/, outputs/extension/, outputs/prvt_ready/ (aggregate only).
"""
import argparse
import json
import sys
from pathlib import Path

import pandas as pd

import sadka.factors as factors_mod
import sadka.tass as tass_mod
from sadka.core import load_config
from sadka.tass import clean_tass, parse_month_series, normalize_source_status
from sadka.analysis import build_equal_weight_style_returns, run_table3
from sadka.liquidity import load_sadka_liquidity_xlsx, make_liquidity_variant

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data/raw/tass/manual_exports"
CFG = "config/spec_table3_main.yaml"
MODEL2 = ["MKT-RF", "SMB", "DTERM", "DCREDIT", "PTFSBD", "PTFSFX", "PTFSCOM", "Liquidity"]
STATS = ["min", "p1", "p25", "p50", "p75", "p99", "max", "std"]
QMAP = {"p1": 0.01, "p25": 0.25, "p50": 0.50, "p75": 0.75, "p99": 0.99}
MAIN_END = pd.Timestamp("2019-09-30")          # John's main extension target
RET = "ret_excess"

# Sadka (2010) Table 1, transcribed from the paper (Panel B per style + Panel C Overall): N, distribution.
SADKA_B = [
    ("Convertible Arbitrage", 258, -0.0936, -0.0767, -0.0067, 0.0023, 0.0114, 0.0740, 0.0890, 0.0251),
    ("Dedicated Short Bias", 54, -0.0828, -0.0828, -0.0253, 0.0014, 0.0266, 0.0844, 0.0844, 0.0440),
    ("Emerging Markets", 656, -0.1852, -0.1352, -0.0233, 0.0024, 0.0309, 0.1840, 0.2746, 0.0572),
    ("Equity Market Neutral", 664, -0.1100, -0.0811, -0.0088, 0.0037, 0.0183, 0.0884, 0.1327, 0.0308),
    ("Event Driven", 785, -0.1499, -0.0758, -0.0066, 0.0038, 0.0148, 0.1060, 0.2091, 0.0321),
    ("Fixed Income Arbitrage", 501, -0.1262, -0.1013, -0.0066, 0.0038, 0.0142, 0.0939, 0.1365, 0.0318),
    ("Fund of Funds", 4268, -0.1843, -0.0722, -0.0102, 0.0023, 0.0156, 0.0738, 0.1978, 0.0274),
    ("Global Macro", 608, -0.1775, -0.1371, -0.0183, 0.0027, 0.0244, 0.1537, 0.2166, 0.0491),
    ("Long/Short Equity", 3574, -0.2812, -0.1161, -0.0164, 0.0058, 0.0295, 0.1446, 1.3490, 0.0731),
    ("Managed Futures", 964, -0.2799, -0.1509, -0.0231, 0.0040, 0.0317, 0.1714, 0.3443, 0.0608),
    ("Multi-Strategy", 1177, -0.1832, -0.1134, -0.0104, 0.0039, 0.0192, 0.1203, 1.0133, 0.0710),
    ("Overall", 12929, -0.4295, -0.1187, -0.0137, 0.0033, 0.0215, 0.1380, 2.4082, 0.0687),
]
# Panel A per-year N (1994-2008) for the count reconciliation.
SADKA_A_N = {1994: 1095, 1995: 1382, 1996: 1693, 1997: 1959, 1998: 2264, 1999: 2613, 2000: 2972,
             2001: 3497, 2002: 4085, 2003: 4841, 2004: 5775, 2005: 6505, 2006: 6879, 2007: 6727, 2008: 8542}


def _need(path, hint):
    if not Path(path).exists():
        sys.exit(f"[input missing] {path}\n  -> {hint}")


def _std_frames():
    """Build standardized returns/info frames from the WRDS pull (1994-latest)."""
    rp = RAW / "tr_tass_returns_1994_latest.parquet"
    ip = RAW / "tr_tass_fundinfo_full.parquet"
    _need(rp, "run `python wrds_pull.py` first (needs WRDS_USER / WRDS_PASS in your env).")
    _need(ip, "run `python wrds_pull.py` first.")
    ret = pd.read_parquet(rp)
    info = pd.read_parquet(ip)
    returns_std = pd.DataFrame({
        "fund_id": tass_mod._fund_id(ret["fund_id"]),
        "month": parse_month_series(ret["date"]),
        "ret_raw": pd.to_numeric(ret["ror"], errors="coerce"),
    })
    stat = info[["fund_id", "status"]].copy()
    stat["fund_id"] = tass_mod._fund_id(stat["fund_id"])
    stat["source_status"] = stat["status"].map(normalize_source_status)
    returns_std = returns_std.merge(stat[["fund_id", "source_status"]], on="fund_id", how="left")
    returns_std["source_status"] = returns_std["source_status"].fillna("unknown")
    returns_std = returns_std.dropna(subset=["fund_id", "month"])
    info_std = pd.DataFrame({
        "fund_id": tass_mod._fund_id(info["fund_id"]),
        "investment_style_raw": info["strategy"].astype(str),
        "currency": info.get("currency"),
        "reporting_frequency": info.get("frequency"),
        "net_of_fees_flag": info.get("net_of_fees"),
        "live_graveyard_status": info["status"].map(normalize_source_status),
    }).dropna(subset=["fund_id"]).drop_duplicates("fund_id")
    return returns_std, info_std


def _ff(end):
    factors_mod.START = pd.Timestamp("1994-01-31")
    factors_mod.END = end
    return factors_mod.load_fama_french()


def _clean_both(returns_std, info_std, ff, cfg, end):
    tass_mod.START = pd.Timestamp("1994-01-31")
    tass_mod.END = end
    rf = ff[["month", "RF"]]
    usd = clean_tass(returns_std, info_std, rf, cfg)
    allc = clean_tass(returns_std, info_std.drop(columns=["currency"]), rf, cfg)
    for tag, r in [("usd", usd), ("all", allc)]:
        if r.get("fatal_error"):
            sys.exit(f"[clean_tass fatal:{tag}] {r['fatal_error']}")
    return usd["fund_month"], allc["fund_month"]


def _avg_monthly(df):
    g = df.groupby("month")[RET]
    mx = pd.DataFrame({"min": g.min(), "max": g.max(), "std": g.std(),
                       **{k: g.quantile(q) for k, q in QMAP.items()}})[STATS]
    return mx.mean() if len(mx) else pd.Series({s: float("nan") for s in STATS})


# ===================================================================== RECONCILE
def stage_reconcile():
    out = ROOT / "outputs/reconciliation"
    out.mkdir(parents=True, exist_ok=True)
    cfg = load_config(CFG)
    returns_std, info_std = _std_frames()
    ff = _ff(pd.Timestamp("2008-12-31"))
    fm_usd, fm_all = _clean_both(returns_std, info_std, ff, cfg, pd.Timestamp("2008-12-31"))
    for d in (fm_usd, fm_all):
        d["year"] = d["month"].dt.year
    sB = pd.DataFrame(SADKA_B, columns=["style", "N"] + STATS)
    styles = sB[sB["style"] != "Overall"]["style"].tolist()

    # ---- per-style N + distribution (USD + all-currency) ----
    nrows, drows = [], []
    for st in styles + ["Overall"]:
        s_n = int(sB.loc[sB["style"] == st, "N"].iloc[0])
        for tag, fm in [("usd", fm_usd), ("allcurrency", fm_all)]:
            g = fm if st == "Overall" else fm[fm["style"] == st]
            our = g["fund_id"].nunique()
            nrows.append({"style": st, "sample": tag, "our_N": our, "sadka_N": s_n,
                          "pct_diff": round((our - s_n) / s_n * 100, 1)})
            if st != "Overall":
                dist = _avg_monthly(g)
                for s in STATS:
                    drows.append({"style": st, "sample": tag, "stat": s,
                                  "ours": round(float(dist[s]), 4),
                                  "sadka": float(sB.loc[sB["style"] == st, s].iloc[0])})
    pd.DataFrame(nrows).to_csv(out / "table1_style_N_recon.csv", index=False)
    pd.DataFrame(drows).to_csv(out / "table1_style_distribution_recon.csv", index=False)

    # ---- per-year N ----
    yr = []
    for y, s_n in SADKA_A_N.items():
        for tag, fm in [("usd", fm_usd), ("allcurrency", fm_all)]:
            our = fm[fm["year"] == y]["fund_id"].nunique()
            yr.append({"year": y, "sample": tag, "our_N": our, "sadka_N": s_n,
                       "pct_diff": round((our - s_n) / s_n * 100, 1)})
    pd.DataFrame(yr).to_csv(out / "table1_year_N_recon.csv", index=False)

    # ---- distribution-method diagnostic on Overall (which matches Sadka Panel C) ----
    ov = {s: float(sB.loc[sB["style"] == "Overall", s].iloc[0]) for s in STATS}
    mrows = []
    for tag, fm in [("usd", fm_usd), ("allcurrency", fm_all)]:
        pooled = {"min": fm[RET].min(), "max": fm[RET].max(), "std": fm[RET].std(),
                  **{k: fm[RET].quantile(q) for k, q in QMAP.items()}}
        amx = {s: float(_avg_monthly(fm)[s]) for s in STATS}
        fl = fm.groupby("fund_id")[RET].mean()
        fld = {"min": fl.min(), "max": fl.max(), "std": fl.std(), **{k: fl.quantile(q) for k, q in QMAP.items()}}
        for mname, mv in [("pooled", pooled), ("avg_monthly_cross_section", amx), ("fund_level", fld)]:
            mrows.append({"sample": tag, "method": mname, **{s: round(float(mv[s]), 4) for s in STATS},
                          "err_vs_sadka_p50_std": round(abs(mv["p50"] - ov["p50"]) + abs(mv["std"] - ov["std"]), 4)})
    pd.DataFrame(mrows).to_csv(out / "distribution_method_diagnostic.csv", index=False)

    # ---- Long/Short tail audit + Managed Futures coverage ----
    tail = []
    for tag, fm in [("usd", fm_usd), ("allcurrency", fm_all)]:
        g = fm[fm["style"] == "Long/Short Equity"]
        tail.append({"sample": tag, "n_fund_months": len(g), "max_excess": round(float(g[RET].max()), 4),
                     "p99": round(float(g[RET].quantile(0.99)), 4), "n_gt_1p0": int((g[RET] > 1.0).sum()),
                     "sadka_panelB_max_avg_monthly": 1.3490})
    pd.DataFrame(tail).to_csv(out / "longshort_tail_audit.csv", index=False)
    cov = (info_std.assign(mapped=tass_mod.map_styles_series(info_std["investment_style_raw"],
                                                             cfg["styles"]["style_mapping_variant"]))
           .groupby(["investment_style_raw", "mapped"], dropna=False).size()
           .reset_index(name="n_funds_info_level").sort_values("n_funds_info_level", ascending=False))
    cov.to_csv(out / "style_mapping_coverage_info_level.csv", index=False)

    ls = next(r for r in nrows if r["style"] == "Long/Short Equity" and r["sample"] == "allcurrency")
    print(f"[reconcile] USD N={fm_usd['fund_id'].nunique()} all-cur N={fm_all['fund_id'].nunique()} (Sadka 12,929)")
    print(f"[reconcile] L/S all-currency N={ls['our_N']} ({ls['pct_diff']}% vs 3,574) | outputs -> {out.relative_to(ROOT)}")


# ===================================================================== EXTEND
def stage_extend():
    out = ROOT / "outputs/extension"
    prvt = ROOT / "outputs/prvt_ready"
    out.mkdir(parents=True, exist_ok=True)
    prvt.mkdir(parents=True, exist_ok=True)
    cfg = load_config(CFG)
    lc = cfg["liquidity"]
    _need(ROOT / lc["source_file"], "place the Sadka liquidity xlsx under data/raw/liquidity/ (see README).")
    returns_std, info_std = _std_frames()

    # factors over the full available window
    ff = _ff(pd.Timestamp("2026-12-31"))
    hsieh = factors_mod.load_hsieh_tf()
    tc, _src = factors_mod.build_term_credit()
    liq = make_liquidity_variant(load_sadka_liquidity_xlsx(lc["source_file"], lc["sheet_name"]),
                                 lc["baseline_transform"])[["month", "Liquidity"]]
    liq_max = liq["month"].max()
    panel_full_end = min(ff["month"].max(), hsieh["month"].max(), tc["month"].max())

    # extended style panels (cap at FF max so RF exists), USD + all-currency
    fm_usd, fm_all = _clean_both(returns_std, info_std, ff, cfg, ff["month"].max())
    panels = {}
    for tag, fm in [("usd", fm_usd), ("allcurrency", fm_all)]:
        sp = build_equal_weight_style_returns(fm, ret_col=RET)
        panels[tag] = sp
        sp[sp["month"] <= MAIN_END].to_csv(out / f"style_panel_extended_1994_2019_{tag}.csv", index=False)
        sp.to_csv(out / f"style_panel_extended_full_{tag}.csv", index=False)

    # exact sample bound + corrected factor coverage
    exact_end = min(liq_max, panel_full_end, panels["usd"]["month"].max())
    pd.DataFrame([
        {"factor": "Fama-French", "max": str(ff['month'].max().date())},
        {"factor": "Hsieh PTFS", "max": str(hsieh['month'].max().date())},
        {"factor": "FRED term/credit", "max": str(tc['month'].max().date())},
        {"factor": "Sadka Liquidity (raw xlsx)", "max": str(liq_max.date())},
        {"factor": "== extended_panel_end (main)", "max": str(MAIN_END.date())},
        {"factor": "== exact_sadka_regression_end", "max": str(exact_end.date())},
    ]).to_csv(out / "factor_coverage_corrected.csv", index=False)

    # extended factor panel (FH7 + liq; liq NOT forward-filled)
    fh7 = ff.merge(hsieh, on="month").merge(tc[["month", "DTERM", "DCREDIT"]], on="month")
    panel_ext = fh7.merge(liq, on="month", how="left").sort_values("month")
    pcols = ["month", "MKT-RF", "SMB", "RF", "DTERM", "DCREDIT", "PTFSBD", "PTFSFX", "PTFSCOM", "Liquidity"]
    panel_ext = panel_ext[pcols]

    # exact Sadka-LIQ Table 3 (Model 2): 1994-2008 vs 1994..exact_end, OLS + NW6
    liq_panel = panel_ext.dropna(subset=["Liquidity"])
    spl = panels["usd"][["month", "style", "style_ret"]]
    res = []
    for end, tag in [(pd.Timestamp("2008-12-31"), "1994-2008"), (exact_end, f"1994-{exact_end.year}")]:
        facw = liq_panel[liq_panel["month"] <= end]
        for tt in ["ols", "hac_6"]:
            r = run_table3(spl, facw[["month"] + MODEL2], tstat_type=tt)
            res.append(r[r["spec"] == "model2"].assign(window=tag))
    m2 = pd.concat(res, ignore_index=True)
    m2.to_csv(out / "table3_model2_exact_sadka.csv", index=False)
    liqrows = m2[m2["term"] == "Liquidity"][["style", "window", "tstat_type", "coef", "tstat", "nobs", "adj_r2"]]
    liqrows.to_csv(out / "table3_model2_LIQ_by_window.csv", index=False)

    # PRVT-ready (long + wide style returns; lowercase factor panel to 2019-09; liq not ffilled)
    usd_main = panels["usd"][panels["usd"]["month"] <= MAIN_END][["month", "style", "style_ret"]]
    usd_main.to_csv(prvt / "style_returns_long.csv", index=False)
    usd_main.pivot(index="month", columns="style", values="style_ret").reset_index().to_csv(
        prvt / "style_returns_wide.csv", index=False)
    low = {"MKT-RF": "mktrf", "SMB": "smb", "RF": "rf", "DTERM": "dterm", "DCREDIT": "dcredit",
           "PTFSBD": "ptfsbd", "PTFSFX": "ptfsfx", "PTFSCOM": "ptfscom", "Liquidity": "liq"}
    fp = panel_ext[panel_ext["month"] <= MAIN_END].rename(columns=low)[
        ["month", "mktrf", "smb", "dterm", "dcredit", "ptfsbd", "ptfsfx", "ptfscom", "liq", "rf"]]
    fp.to_csv(prvt / "factor_panel_extended.csv", index=False)
    liq_last = fp.loc[fp["liq"].notna(), "month"].max()
    (prvt / "prvt_ready_schema.json").write_text(json.dumps({
        "style_returns_long": ["month", "style", "style_ret"],
        "factor_panel_wide": list(fp.columns),
        "liq_nonmissing_through": str(liq_last.date()),
        "note": "liq NaN after 2012-12 (Sadka LIQ ends there); NOT forward-filled. PRVT merges on Period('M').",
    }, indent=2), encoding="utf-8")
    months = usd_main["month"].drop_duplicates()
    exp = pd.period_range("1994-01", "2019-09", freq="M")
    gaps = [str(p) for p in exp if p not in set(months.dt.to_period("M"))]
    (prvt / "smoke_test.txt").write_text("\n".join([
        f"[{'PASS' if not gaps else 'FAIL'}] continuous 1994-01..2019-09 (missing={len(gaps)})",
        f"[{'PASS' if usd_main['style'].nunique() == 11 else 'FAIL'}] 11 styles present",
        f"[{'PASS' if set(usd_main['month'])==set(fp['month']) else 'FAIL'}] style & factor panels aligned",
        f"[INFO] liq non-missing through {liq_last.date()} (not forward-filled).",
    ]), encoding="utf-8")
    ls = liqrows[(liqrows["style"] == "Long/Short Equity") & (liqrows["tstat_type"] == "ols")]
    ls08 = ls[ls["window"] == "1994-2008"]
    lsex = ls[ls["window"] != "1994-2008"]
    print(f"[extend] exact_sadka_regression_end={exact_end.date()} | style panel -> 2019-09 (full to {panels['usd']['month'].max().date()})")
    if len(ls08) and len(lsex):
        print(f"[extend] L/S LIQ (OLS): 1994-2008 {ls08['coef'].iloc[0]:+.4f}[t {ls08['tstat'].iloc[0]:.2f}] "
              f"-> {lsex['window'].iloc[0]} {lsex['coef'].iloc[0]:+.4f}[t {lsex['tstat'].iloc[0]:.2f}]")
    print(f"[extend] outputs -> {out.relative_to(ROOT)} ; PRVT-ready -> {prvt.relative_to(ROOT)}")


def stage_workbook():
    import glob
    wb = ROOT / "outputs/Sadka_Reconciliation_Extension_summary.xlsx"
    with pd.ExcelWriter(wb, engine="openpyxl") as xl:
        for f in sorted(glob.glob(str(ROOT / "outputs/reconciliation/*.csv")) +
                        glob.glob(str(ROOT / "outputs/extension/*.csv"))):
            pd.read_csv(f).to_excel(xl, sheet_name=Path(f).stem[:31], index=False)
    print(f"[workbook] {wb.relative_to(ROOT)}")


def main():
    ap = argparse.ArgumentParser(description="Sadka Table 1 reconciliation + sample extension")
    ap.add_argument("stage", choices=["reconcile", "extend", "all"])
    a = ap.parse_args()
    if a.stage in ("reconcile", "all"):
        stage_reconcile()
    if a.stage in ("extend", "all"):
        stage_extend()
    if a.stage == "all":
        stage_workbook()


if __name__ == "__main__":
    main()
