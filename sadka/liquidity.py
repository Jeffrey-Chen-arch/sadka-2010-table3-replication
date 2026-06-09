"""Sadka liquidity factor (permanent-variable): loader, variants, crisis-sign check (Step 01)."""
import numpy as np
import pandas as pd
import statsmodels.api as sm
from .core import resolve


# ===== from liquidity.py =====
SAMPLE_START = pd.Timestamp("1994-01-31")
SAMPLE_END = pd.Timestamp("2008-12-31")


def load_sadka_liquidity_xlsx(path, sheet_name: str = "Sheet1") -> pd.DataFrame:
    df = pd.read_excel(resolve(path), sheet_name=sheet_name, engine="openpyxl")
    required = ["Date", "Fixed-Transitory", "Variable-Permanent"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing liquidity columns: {missing} (have {list(df.columns)})")
    out = df[required].copy()
    out = out[pd.to_numeric(out["Date"], errors="coerce").notna()].copy()
    out["yyyymm"] = out["Date"].astype(int).astype(str)
    out["month"] = pd.to_datetime(out["yyyymm"], format="%Y%m") + pd.offsets.MonthEnd(0)
    out = out.rename(columns={
        "Fixed-Transitory": "liq_fixed_transitory",
        "Variable-Permanent": "Liquidity_raw",
    })
    out["liq_fixed_transitory"] = pd.to_numeric(out["liq_fixed_transitory"], errors="coerce")
    out["Liquidity_raw"] = pd.to_numeric(out["Liquidity_raw"], errors="coerce")
    return out[["month", "Liquidity_raw", "liq_fixed_transitory"]].sort_values("month").reset_index(drop=True)


def _ar_residual(level: pd.Series, months: pd.Series, p: int = 3,
                 lo=SAMPLE_START, hi=SAMPLE_END) -> pd.Series:
    """OLS of level on p lags; regression sample restricted to [lo, hi] (lags may reach
    before lo since the full series is provided). Residuals aligned to input index."""
    X = pd.DataFrame({f"lag{k}": level.shift(k) for k in range(1, p + 1)})
    X = sm.add_constant(X)
    in_sample = (months >= lo) & (months <= hi)
    use = in_sample & X.notna().all(axis=1) & level.notna()
    res = sm.OLS(level[use], X[use]).fit()
    resid = pd.Series(np.nan, index=level.index)
    resid[use] = res.resid
    return resid


def make_liquidity_variant(df: pd.DataFrame, transform: str) -> pd.DataFrame:
    out = df.copy()
    x = out["Liquidity_raw"].astype(float)
    if transform == "as_is":
        out["Liquidity"] = x
    elif transform == "flipped":
        out["Liquidity"] = -x
    elif transform == "times_100":
        out["Liquidity"] = x * 100.0
    elif transform == "divide_100":
        out["Liquidity"] = x / 100.0
    elif transform == "zscore":
        out["Liquidity"] = (x - x.mean()) / x.std(ddof=1)
    elif transform == "lag1":
        out["Liquidity"] = x.shift(1)
    elif transform == "lead1":
        out["Liquidity"] = x.shift(-1)
    elif transform == "ar3_resid":
        out["Liquidity"] = _ar_residual(x, out["month"], p=3)  # liquidity-oriented, no flip
    elif transform == "ar3_resid_neg":
        out["Liquidity"] = -_ar_residual(x, out["month"], p=3)
    else:
        raise ValueError(f"Unknown liquidity transform: {transform}")
    return out[["month", "Liquidity", "Liquidity_raw", "liq_fixed_transitory"]]


CRISIS_MONTHS = [pd.Timestamp("1998-09-30"), pd.Timestamp("2001-01-31"),
                 pd.Timestamp("2007-08-31"), pd.Timestamp("2008-09-30")]


def crisis_signs_negative(panel: pd.DataFrame) -> dict:
    """Return {month: value} for crisis months (expected all negative)."""
    s = panel.set_index("month")["Liquidity"]
    return {m.strftime("%Y-%m"): float(s.get(m, float("nan"))) for m in CRISIS_MONTHS}

