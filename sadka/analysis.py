"""Style portfolios, Table 3 OLS, target comparison, spec grid, Table 1 diagnostics, Figure 2 (Steps 04-07,09)."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from .tass import CANONICAL_11
import statsmodels.api as sm
import itertools
from .factors import build_term_credit, load_fama_french, load_hsieh_tf
from .liquidity import SAMPLE_END, SAMPLE_START, load_sadka_liquidity_xlsx, make_liquidity_variant
from .tass import map_styles_series


# ===== from portfolios.py =====
def build_equal_weight_style_returns(fund_month: pd.DataFrame, ret_col: str = "ret_excess") -> pd.DataFrame:
    required = ["fund_id", "month", "style", ret_col]
    missing = [c for c in required if c not in fund_month.columns]
    if missing:
        raise ValueError(f"Missing columns for style portfolios: {missing}")

    valid = fund_month.dropna(subset=required).copy()
    out = (
        valid.groupby(["month", "style"], as_index=False)
        .agg(style_ret=(ret_col, "mean"),
             n_funds=("fund_id", "nunique"),
             n_obs=(ret_col, "count"))
        .sort_values(["style", "month"])
        .reset_index(drop=True)
    )

    present = set(out["style"].unique())
    missing_styles = set(CANONICAL_11) - present
    if missing_styles:
        raise ValueError(f"Missing canonical styles in portfolio output: {sorted(missing_styles)}")
    return out


# ===== from regressions.py =====
MODEL1_TERMS = ["MKT-RF", "Liquidity"]
MODEL2_TERMS = ["MKT-RF", "SMB", "DTERM", "DCREDIT", "PTFSBD", "PTFSFX", "PTFSCOM", "Liquidity"]


def run_ols(y: pd.Series, x: pd.DataFrame, tstat_type: str = "ols"):
    x = sm.add_constant(x, has_constant="add")
    model = sm.OLS(y, x, missing="drop")
    if tstat_type == "ols":
        return model.fit()
    if tstat_type == "hac_3":
        return model.fit(cov_type="HAC", cov_kwds={"maxlags": 3})
    if tstat_type == "hac_6":
        return model.fit(cov_type="HAC", cov_kwds={"maxlags": 6})
    raise ValueError(f"Unknown tstat_type: {tstat_type}")


def run_table3(style_returns_long: pd.DataFrame, factors: pd.DataFrame,
               tstat_type: str = "ols") -> pd.DataFrame:
    """style_returns_long: [month, style, style_ret]; factors: [month, <factor cols>]."""
    panel = style_returns_long.merge(factors, on="month", how="inner")
    rows = []
    for style, g in panel.groupby("style"):
        for spec, terms in [("model1", MODEL1_TERMS), ("model2", MODEL2_TERMS)]:
            y = g["style_ret"]
            x = g[terms]
            res = run_ols(y, x, tstat_type=tstat_type)
            for raw_term, coef in res.params.items():
                term = "Intercept" if raw_term == "const" else raw_term
                rows.append({
                    "style": style, "spec": spec, "term": term,
                    "coef": float(coef), "tstat": float(res.tvalues[raw_term]),
                    "pvalue": float(res.pvalues[raw_term]), "nobs": int(res.nobs),
                    "r2": float(res.rsquared), "adj_r2": float(res.rsquared_adj),
                    "tstat_type": tstat_type,
                })
    return pd.DataFrame(rows)


# ===== from compare.py =====
def compare_to_targets(rep: pd.DataFrame, target: pd.DataFrame) -> pd.DataFrame:
    m = target.merge(rep, on=["style", "spec", "term"], how="left")
    m["coef_diff"] = m["coef"] - m["coef_target"]
    m["tstat_diff"] = m["tstat"] - m["tstat_target"]
    m["r2_diff"] = m["r2"] - m["r2_target"]
    m["adj_r2_diff"] = m["adj_r2"] - m["adj_r2_target"]
    m["coef_abs_diff"] = m["coef_diff"].abs()
    m["tstat_abs_diff"] = m["tstat_diff"].abs()
    m["same_coef_sign"] = (
        m["coef"].isna() | (m["coef_target"] == 0) | (m["coef"] == 0)
        | ((m["coef"] * m["coef_target"]) > 0)
    )
    m["target_sig_5pct"] = m["tstat_target"].abs() >= 1.96
    m["rep_sig_5pct"] = m["tstat"].abs() >= 1.96
    m["sig_match_5pct"] = m["target_sig_5pct"] == m["rep_sig_5pct"]
    return m


def score_spec(comp: pd.DataFrame) -> dict:
    liq = comp[comp["term"] == "Liquidity"].copy()
    allt = comp.copy()
    return {
        "coef_mae_all": float(allt["coef_abs_diff"].mean()),
        "tstat_mae_all": float(allt["tstat_abs_diff"].mean()),
        "r2_mae": float(allt["r2_diff"].abs().mean()),
        "liq_coef_mae": float(liq["coef_abs_diff"].mean()),
        "liq_tstat_mae": float(liq["tstat_abs_diff"].mean()),
        "liq_sign_match_rate": float(liq["same_coef_sign"].mean()),
        "liq_sig_match_rate": float(liq["sig_match_5pct"].mean()),
    }


# ===== from sample_diagnostics.py =====
def compute_table1_style_counts(fund_month: pd.DataFrame) -> pd.DataFrame:
    return fund_month.groupby("style")["fund_id"].nunique().reset_index(name="n_rep")


def compute_table1_year_counts(fund_month: pd.DataFrame) -> pd.DataFrame:
    x = fund_month.copy()
    x["year"] = x["month"].dt.year
    return x.groupby("year")["fund_id"].nunique().reset_index(name="n_rep")


def _q(p):
    def f(s):
        return s.quantile(p)
    return f


def compute_monthly_cross_section_stats(fund_month: pd.DataFrame, group_cols, col="ret_excess") -> pd.DataFrame:
    """Stats computed each month from the cross-section, then averaged over months."""
    gc = list(group_cols)
    per = (fund_month.groupby(gc + ["month"])[col]
           .agg(minimum="min", p01=_q(0.01), p25=_q(0.25), p50=_q(0.50),
                p75=_q(0.75), p99=_q(0.99), maximum="max", std="std")
           .reset_index())
    if gc:
        return per.groupby(gc).mean(numeric_only=True).reset_index()
    return per.drop(columns=["month"]).mean(numeric_only=True).to_frame().T


def compare_style_counts_to_targets(style_counts: pd.DataFrame, targets: pd.DataFrame) -> pd.DataFrame:
    m = targets.merge(style_counts, on="style", how="left")
    m["diff"] = m["n_rep"] - m["n_target"]
    m["pct_diff"] = (m["diff"] / m["n_target"] * 100).round(1)
    return m


# ===== from spec_grid.py =====
MAIN_SPEC = {"return_excess_mode": "subtract_ff_rf", "style_mapping_variant": "strict_11_only",
             "liquidity_variant": "as_is", "tstat_type": "ols"}

DEFAULT_GRID = {
    "return_excess_mode": ["subtract_ff_rf", "as_reported"],
    "style_mapping_variant": ["strict_11_only", "expanded_alias_map"],
    "liquidity_variant": ["as_is", "flipped", "ar3_resid"],
    "term_credit_source": ["fred_monthly_average", "fred_daily_eom"],
    "tstat_type": ["ols", "hac_3", "hac_6"],
}


def _build_factors(liquidity_raw, ff, hsieh, term_credit, liq_variant) -> pd.DataFrame:
    liqv = make_liquidity_variant(liquidity_raw, liq_variant)
    liqv = liqv[(liqv["month"] >= SAMPLE_START) & (liqv["month"] <= SAMPLE_END)][["month", "Liquidity"]]
    f = (ff.merge(hsieh, on="month")
           .merge(term_credit[["month", "DTERM", "DCREDIT"]], on="month")
           .merge(liqv, on="month"))
    return f.dropna()


def _is_main(spec: dict) -> bool:
    return all(spec.get(k) == v for k, v in MAIN_SPEC.items())


def classify_spec(spec: dict, allowed_main_liquidity_variants=("as_is",)) -> dict:
    """Tag a spec. Diagnostic liquidity variants can never be the main/closest-feasible spec."""
    is_allowed_main = spec.get("liquidity_variant") in set(allowed_main_liquidity_variants)
    return {
        "is_paper_faithful": _is_main(spec),
        "is_diagnostic": not is_allowed_main,
        "is_allowed_main": is_allowed_main,
        "tier": "tier1_allowed" if is_allowed_main else "diagnostic_only",
    }


def run_spec_grid(fund_month: pd.DataFrame, targets: pd.DataFrame, liquidity_path: str,
                  grid: dict | None = None, fred_dir="data/raw/external_factors/fred",
                  sheet="Sheet1", allowed_main_liquidity_variants=("as_is",)):
    grid = grid or DEFAULT_GRID
    allowed = set(allowed_main_liquidity_variants)
    ff = load_fama_french()
    hsieh = load_hsieh_tf()
    liquidity_raw = load_sadka_liquidity_xlsx(liquidity_path, sheet)
    dims = list(grid.keys())
    rows = []
    for combo in itertools.product(*[grid[d] for d in dims]):
        spec = dict(zip(dims, combo))
        tc, src = build_term_credit(fred_dir, source=spec.get("term_credit_source"))
        if tc is None:
            rows.append({**spec, "status": "skipped_no_term_credit"})
            continue
        factors = _build_factors(liquidity_raw, ff, hsieh, tc, spec["liquidity_variant"])
        fm = fund_month.copy()
        if spec["style_mapping_variant"] != "strict_11_only":
            fm["style"] = map_styles_series(fm["investment_style_raw"], spec["style_mapping_variant"])
            fm = fm[fm["style"].notna()]
        retcol = ("ret_excess_subtract_ff_rf" if spec["return_excess_mode"] == "subtract_ff_rf"
                  else "ret_excess_as_reported")
        try:
            sp = build_equal_weight_style_returns(fm, ret_col=retcol)
            rep = run_table3(sp[["month", "style", "style_ret"]], factors, tstat_type=spec["tstat_type"])
            comp = compare_to_targets(rep, targets)
            sc = score_spec(comp)
        except Exception as e:
            rows.append({**spec, "status": f"error:{type(e).__name__}"})
            continue
        rows.append({**spec, "status": "ok", "term_credit_source_used": src,
                     **classify_spec(spec, allowed), **sc})
    scores = pd.DataFrame(rows)
    ok = scores[scores["status"] == "ok"].copy() if "status" in scores else scores
    best_any = (ok.sort_values("liq_coef_mae").iloc[0].to_dict() if len(ok) else None)
    ok_allowed = ok[ok["is_allowed_main"]] if "is_allowed_main" in ok else ok.iloc[0:0]
    best_allowed = (ok_allowed.sort_values("liq_coef_mae").iloc[0].to_dict() if len(ok_allowed) else None)
    return scores, best_allowed, best_any


# ===== from figures.py =====



def figure2_data(style_returns: pd.DataFrame, factors: pd.DataFrame) -> pd.DataFrame:
    """Per style: average monthly excess return and Model-2 liquidity beta."""
    avg = style_returns.groupby("style")["style_ret"].mean().reset_index(name="avg_excess_ret")
    rep = run_table3(style_returns[["month", "style", "style_ret"]], factors)
    beta = (rep[(rep["spec"] == "model2") & (rep["term"] == "Liquidity")][["style", "coef"]]
            .rename(columns={"coef": "liquidity_beta"}))
    return avg.merge(beta, on="style").sort_values("liquidity_beta").reset_index(drop=True)


def plot_figure2(fig2: pd.DataFrame, path) -> None:
    fig, ax1 = plt.subplots(figsize=(11, 5))
    x = range(len(fig2))
    ax1.bar(list(x), fig2["avg_excess_ret"] * 100, color="#9ecae1", label="Avg excess return")
    ax1.set_ylabel("Average monthly excess return (%)")
    ax1.set_xticks(list(x))
    ax1.set_xticklabels(fig2["style"], rotation=60, ha="right", fontsize=7)
    ax2 = ax1.twinx()
    ax2.plot(list(x), fig2["liquidity_beta"], "o-", color="firebrick", label="Liquidity beta")
    ax2.set_ylabel("Liquidity beta (Model 2)")
    ax1.set_title("Figure 2 (replication): style avg excess return vs liquidity beta")
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)

