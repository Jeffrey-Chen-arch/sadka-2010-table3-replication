"""Consolidated test suite for the Sadka Table III replication.

Unit tests use only synthetic fixtures + committed benchmark files (no raw data); the single
integration test (real factor files) is marked and skips when those files are absent.
Run unit-only:  python -m pytest -q -m "not integration"
"""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import sadka
from sadka.analysis import (
    MODEL1_TERMS, MODEL2_TERMS, build_equal_weight_style_returns, classify_spec,
    compare_style_counts_to_targets, compare_to_targets, compute_monthly_cross_section_stats,
    compute_table1_style_counts, figure2_data, run_spec_grid, run_table3,
)
from sadka.core import load_config, load_yaml, pvalue_from_corr, resolve
from sadka.reporting import build_memo, build_workbook, is_table3_complete
from sadka.tass import (
    CANONICAL_11, clean_tass, fund_info_conflicts, map_styles_series, normalize_return_scale,
    normalize_source_status, parse_month_series, standardize_returns,
    standardize_wide_returns,
)

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "data" / "benchmarks"
ALIAS = load_yaml("config/tass_column_aliases.yaml")


def _all11_fund_month(ret_each=(0.01, 0.03), months=3):
    rows = []
    ms = pd.date_range("2000-01-31", periods=months, freq="ME")
    for st in CANONICAL_11:
        for k, r in enumerate(ret_each):
            for m in ms:
                rows.append({"fund_id": f"{st[:3]}{k}", "month": m, "style": st,
                             "investment_style_raw": st, "source_status": "live", "ret_excess": r})
    return pd.DataFrame(rows)


# ---------- benchmark target files ----------
def test_table1_targets():
    t1 = pd.read_csv(BENCH / "sadka_table1_style_targets.csv")
    by = dict(zip(t1["style"], t1["n_target"]))
    assert by["Overall"] == 12929 and by["Fund of Funds"] == 4268
    assert all(s in by for s in CANONICAL_11)


def test_table2_signs_and_formula():
    t2 = pd.read_csv(BENCH / "sadka_table2_corr_targets.csv")

    def c(r, col):
        return float(t2[(t2["row_factor"] == r) & (t2["col_factor"] == col)]["corr_target"].iloc[0])
    assert c("Liquidity", "DCREDIT") == -0.34 and c("Liquidity", "PTFSFX") == -0.10
    assert c("DCREDIT", "DTERM") == -0.48 and c("Liquidity", "MKT-RF") == 0.13
    for _, row in t2.iterrows():
        assert abs(float(row["pvalue_formula_n180"])
                   - round(pvalue_from_corr(float(row["corr_target"]), 180), 4)) < 1e-6


def test_table3_targets_structure():
    t3 = pd.read_csv(BENCH / "sadka_table3_targets.csv")
    assert len(t3) == 132 and set(t3["style"].unique()) == set(CANONICAL_11)
    dsb = t3[(t3["style"] == "Dedicated Short Bias") & (t3["spec"] == "model2") & (t3["term"] == "Liquidity")]
    assert float(dsb["coef_target"].iloc[0]) == -0.1554


# ---------- package import guard ----------
def test_imports_from_flat_sadka_package():
    f = Path(sadka.__file__).resolve()
    assert f.parent.name == "sadka" and sadka.__version__


# ---------- TASS standardize / clean mechanics ----------
def test_messy_columns_and_wrds_dates():
    df = pd.DataFrame({"Fund ID": [1], "Return Date": ["1994-01-31"], "Rate of Return": [1.2]})
    std = standardize_returns(df, ALIAS, "returns_live.csv")
    assert std["fund_id"].iloc[0] == "1" and std["month"].iloc[0] == pd.Timestamp("1994-01-31")
    out = parse_month_series(pd.Series([199401, "199402", 19940331, "1994-04-15"]))
    assert list(out) == [pd.Timestamp("1994-01-31"), pd.Timestamp("1994-02-28"),
                         pd.Timestamp("1994-03-31"), pd.Timestamp("1994-04-30")]


def test_fund_id_missing_and_wide_format():
    df = pd.DataFrame({"fundno": [1, "2", None, float("nan"), ""], "rdate": ["1999-01-31"] * 5, "ror": [0.01] * 5})
    assert len(standardize_returns(df, ALIAS, "live.csv")) == 2  # missing fund_ids dropped
    wide = pd.DataFrame({"fundno": ["A", "B"], "199401": [1.0, 2.0], "199402": [-1.0, 0.5]})
    w = standardize_wide_returns(wide, ALIAS, "returns_graveyard.csv")
    assert len(w) == 4 and (w["source_status"] == "graveyard").all()


def test_scale_detection_and_source_status():
    _, lab = normalize_return_scale(pd.Series([1.5, -2.0, 0.8, 30.0]))
    assert lab == "percent_to_decimal"
    assert normalize_source_status("No longer reporting") == "graveyard"
    assert normalize_source_status("Currently reporting") == "live"


def test_style_mapping_strict_vs_expanded_and_conflicts():
    strict = map_styles_series(pd.Series(["Convertible Arbitrage", "Distressed", "FoF"]), "strict_11_only")
    assert list(strict) == ["Convertible Arbitrage", None, "Fund of Funds"]
    exp = map_styles_series(pd.Series(["Distressed", "CTA"]), "expanded_alias_map")
    assert list(exp) == ["Event Driven", "Managed Futures"]
    info = pd.DataFrame({"fund_id": ["A", "A", "B"], "investment_style_raw": ["Event Driven"] * 2 + ["Global Macro"],
                         "currency": ["USD", "EUR", "USD"]})
    assert set(fund_info_conflicts(info)["fund_id"]) == {"A"}


def _info_for(fid):
    return pd.DataFrame({"fund_id": [fid], "investment_style_raw": ["Event Driven"], "currency": ["USD"],
                         "reporting_frequency": ["Monthly"], "net_of_fees_flag": [1], "live_graveyard_status": ["live"]})


def test_dup_conflict_and_required_filter_stop():
    rstd = pd.DataFrame({"fund_id": ["X", "X"], "month": [pd.Timestamp("2000-01-31")] * 2,
                         "ret_raw": [0.01, 0.05], "source_status": ["live", "graveyard"]})
    ff = pd.DataFrame({"month": [pd.Timestamp("2000-01-31")], "RF": [0.004]})
    assert clean_tass(rstd, _info_for("X"), ff, load_config()).get("fatal_error") == "duplicate_fund_month_conflicts"
    months = pd.date_range("2000-01-31", periods=3, freq="ME")
    r2 = pd.DataFrame({"fund_id": ["A"] * 3, "month": months, "ret_raw": [0.01] * 3, "source_status": ["live"] * 3})
    i2 = _info_for("A").assign(reporting_frequency=["Quarterly"])  # present but unrecognized -> STOP
    ff2 = pd.DataFrame({"month": months, "RF": [0.004] * 3})
    assert clean_tass(r2, i2, ff2, load_config()).get("fatal_error") == "reporting_frequency_present_but_unrecognized"


def test_sentinel_drops_but_keeps_within_ceiling():
    months = pd.date_range("2000-01-31", periods=12, freq="ME")
    r = pd.DataFrame({"fund_id": ["A"] * 12, "month": months, "ret_raw": [0.01] * 10 + [-99.0, 0.50],
                      "source_status": ["live"] * 12})
    res = clean_tass(r, _info_for("A"), pd.DataFrame({"month": months, "RF": [0.004] * 12}), load_config())
    assert int(res["return_sentinel_filter_audit"]["rows_dropped"].iloc[0]) == 1
    assert len(res["fund_month"]) == 11 and res["fund_month"]["ret_decimal"].max() > 0.4


# ---------- portfolios / regressions / diagnostics ----------
def test_portfolio_equal_weight():
    sp = build_equal_weight_style_returns(_all11_fund_month())
    one = sp[sp["style"] == "Event Driven"].iloc[0]
    assert abs(one["style_ret"] - 0.02) < 1e-12 and one["n_funds"] == 2


def test_regression_shape_and_end_to_end():
    rng = np.random.default_rng(0)
    months = pd.date_range("1994-01-31", periods=180, freq="ME")
    factors = pd.DataFrame({"month": months})
    for c in MODEL2_TERMS:
        factors[c] = rng.normal(0, 0.02, 180)
    srl = pd.DataFrame({"month": months, "style": "Event Driven", "style_ret": rng.normal(0.004, 0.01, 180)})
    rep = run_table3(srl, factors)
    assert set(rep[rep["spec"] == "model1"]["term"]) == {"Intercept", *MODEL1_TERMS}
    assert set(rep[rep["spec"] == "model2"]["term"]) == {"Intercept", *MODEL2_TERMS}
    fm = _all11_fund_month(months=36)
    fm["month"] = np.tile(pd.date_range("1996-01-31", periods=36, freq="ME"), len(fm) // 36 + 1)[:len(fm)]
    sp = build_equal_weight_style_returns(fm)
    f2 = pd.DataFrame({"month": pd.date_range("1996-01-31", periods=36, freq="ME")})
    for c in MODEL2_TERMS:
        f2[c] = rng.normal(0, 0.02, 36)
    comp = compare_to_targets(run_table3(sp[["month", "style", "style_ret"]], f2),
                              pd.read_csv(BENCH / "sadka_table3_targets.csv"))
    assert len(comp) == 132


def test_sample_diagnostics_and_compare():
    fm = _all11_fund_month(months=6)
    sc = compute_table1_style_counts(fm)
    assert int(sc[sc["style"] == "Event Driven"]["n_rep"].iloc[0]) == 2
    stats = compute_monthly_cross_section_stats(fm.rename(columns={"ret_excess": "ret_excess"}), ["style"])
    assert {"minimum", "p50", "maximum", "std"}.issubset(stats.columns)
    out = compare_style_counts_to_targets(pd.DataFrame({"style": ["Event Driven"], "n_rep": [800]}),
                                          pd.DataFrame({"style": ["Event Driven"], "n_target": [785]}))
    assert int(out["diff"].iloc[0]) == 15


def test_spec_classification_diagnostics_never_main():
    base = {"return_excess_mode": "subtract_ff_rf", "style_mapping_variant": "strict_11_only",
            "tstat_type": "ols", "term_credit_source": "fred_monthly_average"}
    assert classify_spec({**base, "liquidity_variant": "as_is"})["is_allowed_main"] is True
    for v in ["flipped", "ar3_resid", "zscore"]:
        assert classify_spec({**base, "liquidity_variant": v})["is_allowed_main"] is False


def test_figure2_data_shape():
    rng = np.random.default_rng(7)
    months = pd.date_range("1996-01-31", periods=60, freq="ME")
    sp = pd.DataFrame([{"month": m, "style": st, "style_ret": float(rng.normal(0.004, 0.01))}
                       for st in CANONICAL_11 for m in months])
    factors = pd.DataFrame({"month": months})
    for c in MODEL2_TERMS:
        factors[c] = rng.normal(0, 0.02, 60)
    f2 = figure2_data(sp, factors)
    assert set(f2.columns) == {"style", "avg_excess_ret", "liquidity_beta"}
    assert f2["liquidity_beta"].is_monotonic_increasing


# ---------- reporting (state-robust) ----------
def test_build_workbook_and_memo():
    wb = build_workbook()
    assert wb.exists() and ("TEMPLATE" in wb.name) == (not is_table3_complete())
    assert "Table3_Targets" in pd.ExcelFile(wb).sheet_names
    assert ("TEMPLATE" in build_memo().name) == (not is_table3_complete())


# ---------- integration: real factor files ----------
@pytest.mark.integration
def test_spec_grid_real_factors():
    need = ["data/raw/liquidity/Sadka-LIQ-factors-1983-2012-WRDS.xlsx",
            "data/raw/external_factors/fama_french/FF3_CSV.zip",
            "data/raw/external_factors/hsieh/TF-Fac.xls",
            "data/raw/external_factors/fred/GS10.csv"]
    miss = [p for p in need if not resolve(p).exists()]
    if miss:
        pytest.skip(f"raw factor files absent: {miss}")
    fm = _all11_fund_month(months=36)
    fm["month"] = np.tile(pd.date_range("1996-01-31", periods=36, freq="ME"), len(fm) // 36 + 1)[:len(fm)]
    fm["ret_excess_subtract_ff_rf"] = fm["ret_excess"]
    fm["ret_excess_as_reported"] = fm["ret_excess"]
    grid = {"return_excess_mode": ["subtract_ff_rf"], "style_mapping_variant": ["strict_11_only"],
            "liquidity_variant": ["as_is", "flipped"], "term_credit_source": ["fred_monthly_average"],
            "tstat_type": ["ols"]}
    _scores, best_allowed, _best_any = run_spec_grid(
        fm, pd.read_csv(BENCH / "sadka_table3_targets.csv"),
        liquidity_path="data/raw/liquidity/Sadka-LIQ-factors-1983-2012-WRDS.xlsx", grid=grid)
    assert best_allowed["liquidity_variant"] == "as_is"  # diagnostic 'flipped' can never be main
