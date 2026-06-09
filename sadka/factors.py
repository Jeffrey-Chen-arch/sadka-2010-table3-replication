"""External factors (Fama-French, Hsieh PTFS, FRED term/credit) + monthly factor panel (Step 02)."""
import zipfile
import pandas as pd
from .core import resolve


# ===== from external_factors.py =====
START = pd.Timestamp("1994-01-31")
END = pd.Timestamp("2008-12-31")


def _to_month_end(yyyymm) -> pd.Timestamp:
    return pd.to_datetime(str(int(yyyymm)), format="%Y%m") + pd.offsets.MonthEnd(0)


def load_fama_french(zip_path="data/raw/external_factors/fama_french/FF3_CSV.zip") -> pd.DataFrame:
    z = zipfile.ZipFile(resolve(zip_path))
    name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
    raw = z.read(name).decode("latin1").splitlines()
    start = next(i for i, ln in enumerate(raw) if ln.replace(" ", "").startswith(",Mkt-RF"))
    rows = []
    for line in raw[start + 1:]:
        s = line.strip()
        if not s:
            break
        parts = [p.strip() for p in s.split(",")]
        if len(parts) != 5 or not parts[0].isdigit() or len(parts[0]) != 6:
            break
        rows.append(parts)
    ff = pd.DataFrame(rows, columns=["yyyymm", "MKT-RF", "SMB", "HML", "RF"])
    for c in ["MKT-RF", "SMB", "HML", "RF"]:
        ff[c] = ff[c].astype(float) / 100.0  # percent -> decimal
    ff["month"] = ff["yyyymm"].apply(_to_month_end)
    ff = ff[(ff["month"] >= START) & (ff["month"] <= END)]
    return ff[["month", "MKT-RF", "SMB", "RF"]].reset_index(drop=True)


def load_hsieh_tf(xls_path="data/raw/external_factors/hsieh/TF-Fac.xls") -> pd.DataFrame:
    df = pd.read_excel(resolve(xls_path), engine="xlrd", header=14)
    df = df.rename(columns={df.columns[0]: "yyyymm"})
    df = df[pd.to_numeric(df["yyyymm"], errors="coerce").notna()].copy()
    df["month"] = df["yyyymm"].apply(_to_month_end)
    keep = df[["month", "PTFSBD", "PTFSFX", "PTFSCOM"]].copy()
    for c in ["PTFSBD", "PTFSFX", "PTFSCOM"]:
        keep[c] = pd.to_numeric(keep[c], errors="coerce")
    # auto scale: Hsieh PTFS are returns in decimal (|median| << 1); leave as-is
    keep = keep[(keep["month"] >= START) & (keep["month"] <= END)]
    return keep.reset_index(drop=True)


def _read_fred_csv(path) -> pd.Series:
    df = pd.read_csv(resolve(path))
    datecol = df.columns[0]
    valcol = df.columns[1]
    df[datecol] = pd.to_datetime(df[datecol])
    df[valcol] = pd.to_numeric(df[valcol], errors="coerce")
    return df.dropna(subset=[valcol]).set_index(datecol)[valcol]


def build_term_credit(fred_dir="data/raw/external_factors/fred", source=None):
    """Return (DataFrame[month, DTERM, DCREDIT, level_10y, level_baa], source) or (None, None).

    source: None -> auto (daily EOM preferred, else monthly avg);
            "fred_daily_eom" / "fred_monthly_average" -> force that source (None if absent).
    """
    d = resolve(fred_dir)
    daily_10 = d / "DGS10.csv"
    daily_baa = d / "DBAA.csv"
    mon_10 = d / "GS10.csv"
    mon_baa = d / "BAA.csv"
    use_daily = source in (None, "fred_daily_eom") and daily_10.exists() and daily_baa.exists()
    use_monthly = (not use_daily) and source in (None, "fred_monthly_average") and mon_10.exists() and mon_baa.exists()

    if use_daily:
        s10 = _read_fred_csv(daily_10).resample("ME").last()   # month-end last available
        sbaa = _read_fred_csv(daily_baa).resample("ME").last()
        source = "fred_daily_eom"
    elif use_monthly:
        s10 = _read_fred_csv(mon_10)
        s10.index = s10.index + pd.offsets.MonthEnd(0)
        sbaa = _read_fred_csv(mon_baa)
        sbaa.index = sbaa.index + pd.offsets.MonthEnd(0)
        source = "fred_monthly_average"
    else:
        return None, None

    df = pd.DataFrame({"level_10y": s10, "level_baa": sbaa}).dropna()
    df["credit"] = df["level_baa"] - df["level_10y"]
    df["DTERM"] = df["level_10y"].diff()       # percentage points
    df["DCREDIT"] = df["credit"].diff()
    df = df.reset_index().rename(columns={"index": "month", df.reset_index().columns[0]: "month"})
    df = df.rename(columns={df.columns[0]: "month"})
    df["month"] = pd.to_datetime(df["month"]) + pd.offsets.MonthEnd(0)
    out = df[(df["month"] >= START) & (df["month"] <= END)][
        ["month", "DTERM", "DCREDIT", "level_10y", "level_baa"]].reset_index(drop=True)
    return out, source


# ===== from factor_panel.py =====
FACTOR_COLS = ["MKT-RF", "SMB", "RF", "DTERM", "DCREDIT", "PTFSBD", "PTFSFX", "PTFSCOM", "Liquidity"]
PANEL_COLS = ["month"] + FACTOR_COLS + ["Liquidity_raw", "liq_fixed_transitory"]
TABLE2_FACTORS = ["MKT-RF", "SMB", "DTERM", "DCREDIT", "PTFSBD", "PTFSFX", "PTFSCOM", "Liquidity"]


def build_factor_panel(liquidity_main, ff, hsieh, term_credit) -> pd.DataFrame:
    liq = pd.read_parquet(resolve(liquidity_main)) if isinstance(liquidity_main, str) else liquidity_main
    panel = (
        liq.merge(ff, on="month", how="inner")
        .merge(hsieh, on="month", how="inner")
        .merge(term_credit[["month", "DTERM", "DCREDIT"]], on="month", how="inner")
    )
    panel = panel[PANEL_COLS].sort_values("month").reset_index(drop=True)
    assert len(panel) == 180, f"factor panel has {len(panel)} months, expected 180"
    assert panel["month"].min() == START and panel["month"].max() == END
    miss = panel[FACTOR_COLS].isna().sum().sum()
    assert miss == 0, f"factor panel has {miss} missing factor values"
    return panel

