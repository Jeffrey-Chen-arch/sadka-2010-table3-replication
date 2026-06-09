"""TASS ingest/standardize/clean (audited filter funnel) + 11-style mapping (Step 03)."""
import re
import pandas as pd
from .core import load_style_map
from pathlib import Path
from .core import load_yaml
from .core import read_table
from .core import resolve


# ===== from styles.py =====
CANONICAL_11 = [
    "Convertible Arbitrage", "Dedicated Short Bias", "Emerging Markets",
    "Equity Market Neutral", "Event Driven", "Fixed Income Arbitrage",
    "Fund of Funds", "Global Macro", "Long/Short Equity", "Managed Futures",
    "Multi-Strategy",
]


def _norm(s) -> str:
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return ""
    s = str(s).lower()
    s = re.sub(r"[-_/]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def get_variant_aliases(variant: str, style_map: dict | None = None) -> dict:
    sm = style_map or load_style_map()
    variants = sm["style_mapping_variants"]
    if variant not in variants:
        raise ValueError(f"unknown style mapping variant: {variant} (have {list(variants)})")
    return variants[variant]["aliases"]


def build_alias_lookup(aliases: dict) -> dict:
    lut = {}
    for canon, al in aliases.items():
        for a in al:
            lut[_norm(a)] = canon
    return lut


def map_styles_series(raw_series: pd.Series, variant: str, style_map: dict | None = None) -> pd.Series:
    lut = build_alias_lookup(get_variant_aliases(variant, style_map))
    return raw_series.map(lambda x: lut.get(_norm(x)))


def style_mapping_audit(raw_series: pd.Series, variant: str, style_map: dict | None = None) -> pd.DataFrame:
    mapped = map_styles_series(raw_series, variant, style_map)
    df = pd.DataFrame({"raw_style": raw_series, "mapped_style": mapped})
    out = (df.groupby(["raw_style", "mapped_style"], dropna=False)
             .size().reset_index(name="n_rows"))
    out["mapping_variant"] = variant
    out["mapping_rule"] = out["mapped_style"].apply(lambda x: "mapped" if pd.notna(x) else "UNMAPPED")
    return out.sort_values("n_rows", ascending=False).reset_index(drop=True)


# ===== from tass_standardize.py =====
def _canon_col(x) -> str:
    """Canonicalize a column name: lowercase, strip all non-alphanumerics."""
    return re.sub(r"[^a-z0-9]+", "", str(x).lower())


def _resolve(columns, aliases) -> str | None:
    lut = {_canon_col(c): c for c in columns}
    for a in aliases:
        key = _canon_col(a)
        if key in lut:
            return lut[key]
    return None


def parse_month_series(s: pd.Series) -> pd.Series:
    """Parse YYYYMM / YYYYMMDD (int or str) and normal date strings -> month-end timestamps."""
    txt = s.astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    out = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
    is6 = txt.str.fullmatch(r"\d{6}").fillna(False)
    out.loc[is6] = pd.to_datetime(txt.loc[is6], format="%Y%m", errors="coerce")
    is8 = txt.str.fullmatch(r"\d{8}").fillna(False)
    out.loc[is8] = pd.to_datetime(txt.loc[is8], format="%Y%m%d", errors="coerce")
    rest = ~(is6 | is8)
    out.loc[rest] = pd.to_datetime(s.loc[rest], errors="coerce")
    return out + pd.offsets.MonthEnd(0)


def _fund_id(series) -> pd.Series:
    """Normalize fund_id to a stripped string so returns<->info merges never silently miss.
    Missing values stay missing (never become the literal string 'nan')."""
    x = series.astype("string").str.strip().str.replace(r"\.0$", "", regex=True)
    bad = x.str.lower().isin(["", "nan", "none", "<na>", "null", "na"])
    return x.mask(bad)


_GRAVE_KW = ["grave", "dead", "defunct", "inactive", "closed", "liquidated",
             "dissolved", "terminated", "no longer", "stopped reporting"]
_LIVE_KW = ["live", "active", "currently reporting"]


def normalize_source_status(value, fname: str = "") -> str:
    t = f"{value} {fname}".lower()
    if any(k in t for k in _GRAVE_KW):
        return "graveyard"
    if any(k in t for k in _LIVE_KW):
        return "live"
    return "unknown"


def _status_from_name(fname: str) -> str:
    return normalize_source_status("", fname)


def _infer_status(fname: str, df: pd.DataFrame, status_col: str | None) -> pd.Series:
    if status_col is not None:
        return df[status_col].map(lambda v: normalize_source_status(v, fname))
    return pd.Series([_status_from_name(fname)] * len(df), index=df.index)


def standardize_returns(df: pd.DataFrame, alias: dict, fname: str) -> pd.DataFrame | None:
    cid = _resolve(df.columns, alias["returns"]["fund_id"])
    cdate = _resolve(df.columns, alias["returns"]["date"])
    cret = _resolve(df.columns, alias["returns"]["return"])
    if not (cid and cdate and cret):
        return None
    cstatus = _resolve(df.columns, alias["fund_info"]["live_graveyard_status"])
    out = pd.DataFrame({
        "fund_id": _fund_id(df[cid]),
        "month": parse_month_series(df[cdate]),
        "ret_raw": pd.to_numeric(df[cret], errors="coerce"),
    })
    out["source_status"] = _infer_status(fname, df, cstatus).str.lower().values
    return out.dropna(subset=["fund_id", "month"])


def standardize_wide_returns(df: pd.DataFrame, alias: dict, fname: str) -> pd.DataFrame | None:
    """Wide format: id column + month columns named 199401 / 19940131 / ..."""
    cid = _resolve(df.columns, alias["returns"]["fund_id"])
    if not cid:
        return None
    month_cols = [c for c in df.columns
                  if re.fullmatch(r"\d{6}", str(c).strip()) or re.fullmatch(r"\d{8}", str(c).strip())]
    if not month_cols:
        return None
    out = df.melt(id_vars=[cid], value_vars=month_cols, var_name="month_raw", value_name="ret_raw")
    out = pd.DataFrame({
        "fund_id": _fund_id(out[cid]),
        "month": parse_month_series(out["month_raw"]),
        "ret_raw": pd.to_numeric(out["ret_raw"], errors="coerce"),
        "source_status": _status_from_name(fname),
    })
    return out.dropna(subset=["fund_id", "month"])


def standardize_fund_info(df: pd.DataFrame, alias: dict, fname: str) -> pd.DataFrame | None:
    cid = _resolve(df.columns, alias["fund_info"]["fund_id"])
    cstyle = _resolve(df.columns, alias["fund_info"]["style"])
    if not (cid and cstyle):
        return None
    fi = alias["fund_info"]
    cstatus = _resolve(df.columns, fi["live_graveyard_status"])
    ccur = _resolve(df.columns, fi["currency"])
    cfreq = _resolve(df.columns, fi["reporting_frequency"])
    cnet = _resolve(df.columns, fi["net_of_fees"])
    out = pd.DataFrame({
        "fund_id": _fund_id(df[cid]),
        "investment_style_raw": df[cstyle].astype(str),
        "currency": df[ccur] if ccur else None,
        "reporting_frequency": df[cfreq] if cfreq else None,
        "net_of_fees_flag": df[cnet] if cnet else None,
        "live_graveyard_status": _infer_status(fname, df, cstatus).str.lower().values,
    })
    return out.dropna(subset=["fund_id"])


INFO_CONFLICT_COLS = ["investment_style_raw", "currency", "reporting_frequency",
                      "net_of_fees_flag", "live_graveyard_status"]


def fund_info_conflicts(info_all: pd.DataFrame) -> pd.DataFrame:
    """Rows for fund_ids whose info fields disagree across exports (before dedup)."""
    if len(info_all) == 0:
        return info_all
    cols = [c for c in INFO_CONFLICT_COLS if c in info_all.columns]
    nun = info_all.groupby("fund_id")[cols].nunique(dropna=True)
    problem = nun[(nun > 1).any(axis=1)].index
    return info_all[info_all["fund_id"].isin(problem)].sort_values("fund_id")


def ingest_manual_exports(directory="data/raw/tass/manual_exports",
                          alias_path="config/tass_column_aliases.yaml"):
    """Return (returns_std, fund_info_std, log, fund_info_conflicts). Empty if nothing found."""
    alias = load_yaml(alias_path)
    d = Path(resolve(directory))
    files = [f for f in sorted(d.glob("*"))
             if f.is_file() and f.suffix.lower() in (".csv", ".tsv", ".txt", ".parquet", ".xls", ".xlsx")]
    rets, infos, log = [], [], []
    for f in files:
        try:
            df = read_table(str(f))
        except Exception as e:
            log.append({"file": f.name, "type": "ERROR", "detail": str(e)[:120]})
            continue
        kinds = []
        r = standardize_returns(df, alias, f.name)
        if r is None or len(r) == 0:
            r = standardize_wide_returns(df, alias, f.name)
            if r is not None and len(r):
                kinds.append("returns_wide")
        elif len(r):
            kinds.append("returns")
        if r is not None and len(r):
            rets.append(r)
        i = standardize_fund_info(df, alias, f.name)
        if i is not None and len(i):
            infos.append(i)
            kinds.append("fund_info")
        log.append({"file": f.name, "type": "+".join(kinds) or "unrecognized", "rows": len(df)})

    returns_std = pd.concat(rets, ignore_index=True) if rets else pd.DataFrame(
        columns=["fund_id", "month", "ret_raw", "source_status"])
    info_cols = ["fund_id", "investment_style_raw", "currency", "reporting_frequency",
                 "net_of_fees_flag", "live_graveyard_status"]
    info_all = pd.concat(infos, ignore_index=True) if infos else pd.DataFrame(columns=info_cols)
    info_conflicts = fund_info_conflicts(info_all)
    info_std = info_all.drop_duplicates("fund_id") if len(info_all) else pd.DataFrame(columns=info_cols)
    return returns_std, info_std, pd.DataFrame(log), info_conflicts


# ===== from tass_clean.py =====
START = pd.Timestamp("1994-01-31")
END = pd.Timestamp("2008-12-31")


def normalize_return_scale(s: pd.Series):
    """Detect percent vs decimal using median/q90 (NOT max - 2006-2008 extremes kept)."""
    s = pd.to_numeric(s, errors="coerce")
    med = s.abs().median()
    q90 = s.abs().quantile(0.90)
    if med > 0.2 and q90 > 1.0:
        return s / 100.0, "percent_to_decimal"
    return s, "already_decimal"


def _is_monthly(v) -> bool:
    t = str(v).strip().lower()
    return ("month" in t) or t in {"m", "1", "monthly"}


def _is_usd(v) -> bool:
    t = str(v).strip().lower()
    return t in {"usd", "us dollar", "us dollars", "dollar", "$", "840"}


def _is_net(v) -> bool:
    return str(v).strip().lower() in {"1", "true", "yes", "y", "net", "net of fees", "net of all fees"}


def _funnel_row(step, desc, df):
    return {"step": step, "description": desc, "rows": len(df),
            "unique_funds": df["fund_id"].nunique() if "fund_id" in df else 0,
            "months": df["month"].nunique() if "month" in df else 0}


def clean_tass(returns_std: pd.DataFrame, info_std: pd.DataFrame, ff_factors: pd.DataFrame,
               cfg: dict) -> dict:
    funnel = []
    audits = {}
    df = returns_std.copy()
    funnel.append(_funnel_row("00", "raw returns rows", df))

    # 01 sample period
    df = df[(df["month"] >= START) & (df["month"] <= END)]
    funnel.append(_funnel_row("01", "sample 1994-01..2008-12", df))

    # 02 valid numeric return
    df = df[pd.to_numeric(df["ret_raw"], errors="coerce").notna()]
    funnel.append(_funnel_row("02", "valid numeric return", df))

    # 02b drop EXACT numeric sentinel codes (NOT magnitude - 2006-2008 extremes kept)
    sentinels = cfg.get("returns", {}).get("missing_sentinel_values", []) or []
    is_sent = pd.to_numeric(df["ret_raw"], errors="coerce").isin(sentinels)
    audits["return_sentinel_filter_audit"] = pd.DataFrame([{
        "sentinels": str(sentinels), "rows_dropped": int(is_sent.sum()),
        "note": "exact-match only; magnitude-based dropping NOT applied; legit extremes preserved",
    }])
    df = df[~is_sent]
    funnel.append(_funnel_row("02b", "drop exact numeric sentinels", df))

    # 03 merge fund info
    df = df.merge(info_std, on="fund_id", how="left")
    funnel.append(_funnel_row("03", "merge fund info", df))

    # 04-06 paper-required filters (monthly / USD / net-of-fees) with NO silent skip:
    # if a required field is PRESENT and nonmissing but no values are recognized, STOP.
    net_behavior = cfg.get("returns", {}).get("net_of_fees_unrecognized_behavior", "warn")
    filters = [
        ("reporting_frequency", _is_monthly, True, True, False, "", "04", "monthly reporting"),
        ("currency", _is_usd, True, True, False, "", "05", "USD currency"),
        ("net_of_fees_flag", _is_net, True, (net_behavior == "stop"), True,
         "TASS monthly ROR assumed net of fees if no explicit flag", "06", "net-of-fees"),
    ]
    field_audit = []
    for field, rec, required, fatal_unrec, ff_if_missing, assumption, step, desc in filters:
        rows_before = len(df)
        present = field in df.columns and df[field].notna().any()
        nonmissing_share = round(float(df[field].notna().mean()), 4) if field in df.columns else 0.0
        recognized_share, applied, unrecognized_stop = "", False, False
        if present:
            nonmiss = df[field].notna()
            rec_mask = (df[field].where(nonmiss)
                        .map(lambda v: bool(rec(v)) if pd.notna(v) else False)
                        .fillna(False).astype(bool))
            n_rec = int(rec_mask.sum())
            recognized_share = round(n_rec / max(int(nonmiss.sum()), 1), 4)
            if n_rec > 0:
                df = df[rec_mask]
                applied = True
            elif fatal_unrec:
                unrecognized_stop = True
        field_audit.append({
            "field": field, "present": bool(present), "nonmissing_share": nonmissing_share,
            "recognized_share": recognized_share, "filter_applied": applied,
            "rows_before": rows_before, "rows_after": len(df), "paper_required": required,
            "paper_faithful_if_missing": ff_if_missing, "assumption": assumption,
            "fatal_if_present_but_unrecognized": fatal_unrec})
        funnel.append(_funnel_row(step, desc + ("" if (applied or not present) else " (NOT applied)"), df))
        if unrecognized_stop:
            audits["filter_field_coverage_audit"] = pd.DataFrame(field_audit)
            audits["funnel"] = pd.DataFrame(funnel)
            return {"fund_month": df.iloc[0:0],
                    "fatal_error": f"{field}_present_but_unrecognized", **audits}

    fa = pd.DataFrame(field_audit)
    audits["filter_field_coverage_audit"] = fa
    fai = fa.set_index("field")
    audits["paper_faithful_fields"] = bool(
        fai.loc["currency", "filter_applied"] and fai.loc["reporting_frequency", "filter_applied"])
    audits["net_of_fees_applied"] = bool(fai.loc["net_of_fees_flag", "filter_applied"])

    # 07 Live + Graveyard (no drop; record composition + coverage)
    src = df.get("source_status", pd.Series(dtype=str)).astype(str).str.lower()
    audits["source_counts"] = src.value_counts(dropna=False).rename_axis("source_status").reset_index(name="rows")
    sset = set(src.dropna())
    audits["source_coverage_audit"] = pd.DataFrame([{
        "has_live": any("live" in s for s in sset),
        "has_graveyard": any(("grave" in s or "dead" in s or "defunct" in s) for s in sset),
        "paper_requires_both": True,
        "note": "if not both, result is NOT paper-faithful",
    }])
    funnel.append(_funnel_row("07", "Live + Graveyard kept", df))

    # 08 map styles to canonical 11
    variant = cfg["styles"]["style_mapping_variant"]
    df["style"] = map_styles_series(df["investment_style_raw"], variant)
    audits["style_mapping_audit"] = style_mapping_audit(df["investment_style_raw"], variant)
    unmapped = df[df["style"].isna()]
    audits["unmapped_styles"] = (unmapped["investment_style_raw"].value_counts()
                                 .rename_axis("raw_style").reset_index(name="rows"))
    audits["unmapped_share"] = len(unmapped) / max(len(df), 1)
    df = df[df["style"].notna()]
    funnel.append(_funnel_row("08", f"mapped to 11 styles ({variant})", df))

    # 09 dedup: drop EXACT dup fund-month-return; non-exact conflicts STOP (no keep-first)
    dup_key = ["fund_id", "month"]
    exact = df.duplicated(subset=dup_key + ["ret_raw"], keep="first")
    df = df[~exact].copy()
    conflict = df[df.duplicated(subset=dup_key, keep=False)].sort_values(dup_key)
    audits["duplicate_fund_month_conflicts"] = conflict[dup_key + ["ret_raw", "source_status"]]
    behavior = cfg.get("deduplication", {}).get("conflict_behavior", "stop")
    if len(conflict) > 0 and behavior == "stop":
        funnel.append(_funnel_row("09", "DUP CONFLICT -> STOP", df))
        audits["funnel"] = pd.DataFrame(funnel)
        return {"fund_month": df.iloc[0:0], "fatal_error": "duplicate_fund_month_conflicts", **audits}
    df = df.drop_duplicates(subset=dup_key, keep="first")
    funnel.append(_funnel_row("09", "drop exact dup fund-months", df))

    # 10 normalize return scale
    ret_dec, scale_label = normalize_return_scale(df["ret_raw"])
    df["ret_decimal"] = ret_dec
    audits["return_scale_audit"] = pd.DataFrame([{
        "scale_decision": scale_label,
        "abs_median": float(pd.to_numeric(df["ret_raw"], errors="coerce").abs().median()),
        "abs_q90": float(pd.to_numeric(df["ret_raw"], errors="coerce").abs().quantile(0.90)),
    }])
    # 10b scale-by-source audit (catch live/graveyard percent-vs-decimal mismatch)
    by_src = []
    for src, g in df.groupby("source_status"):
        gv = pd.to_numeric(g["ret_raw"], errors="coerce")
        med, q90 = float(gv.abs().median()), float(gv.abs().quantile(0.90))
        by_src.append({"source_status": src, "abs_median": round(med, 4), "abs_q90": round(q90, 4),
                       "suggested_scale": "percent_to_decimal" if (med > 0.2 and q90 > 1.0) else "already_decimal"})
    by_src_df = pd.DataFrame(by_src)
    audits["return_scale_by_source_audit"] = by_src_df
    audits["scale_inconsistent_across_sources"] = bool(by_src_df["suggested_scale"].nunique() > 1)
    if (audits["scale_inconsistent_across_sources"]
            and cfg.get("returns", {}).get("scale_inconsistency_behavior", "stop") == "stop"):
        funnel.append(_funnel_row("10b", "SCALE INCONSISTENT ACROSS SOURCES -> STOP", df))
        audits["funnel"] = pd.DataFrame(funnel)
        return {"fund_month": df.iloc[0:0],
                "fatal_error": "return_scale_inconsistent_across_sources", **audits}
    funnel.append(_funnel_row("10", f"return scale ({scale_label})", df))

    # 10c drop evident data-entry errors (|monthly return| > ceiling). Upper tail only in
    # practice (min is -100% = total loss). null ceiling = keep-all (paper-faithful).
    ceiling = cfg.get("returns", {}).get("data_error_ceiling_decimal", None)
    if ceiling is not None:
        err = df["ret_decimal"].abs() > float(ceiling)
        audits["data_error_filter_audit"] = pd.DataFrame([{
            "ceiling_decimal": float(ceiling), "rows_dropped": int(err.sum()),
            "note": "evident data-entry errors (e.g. >100%/month); Sadka notes excluding "
                    "extremes does not change results"}])
        df = df[~err]
        funnel.append(_funnel_row("10c", f"drop |ret_decimal|>{ceiling} (data errors)", df))

    # 11 merge RF (+ hard stop if any RF missing)
    df = df.merge(ff_factors[["month", "RF"]], on="month", how="left")
    rf_missing = int(df["RF"].isna().sum())
    if rf_missing > 0:
        audits["rf_merge_audit"] = pd.DataFrame([{
            "rows_missing_rf": rf_missing,
            "months_missing": ", ".join(sorted(df.loc[df["RF"].isna(), "month"].dt.strftime("%Y-%m").unique())[:24])}])
        funnel.append(_funnel_row("11", "RF MISSING -> STOP", df))
        audits["funnel"] = pd.DataFrame(funnel)
        return {"fund_month": df.iloc[0:0], "fatal_error": "missing_rf_after_merge", **audits}
    funnel.append(_funnel_row("11", "merge RF", df))

    # 12 excess-return modes + comparison
    df["ret_excess_subtract_ff_rf"] = df["ret_decimal"] - df["RF"]
    df["ret_excess_as_reported"] = df["ret_decimal"]
    main_mode = cfg["returns"]["main_excess_return_mode"]
    df["ret_excess"] = (df["ret_excess_subtract_ff_rf"] if main_mode == "subtract_ff_rf"
                        else df["ret_excess_as_reported"])
    audits["return_excess_mode_comparison"] = pd.DataFrame([
        {"mode": "subtract_ff_rf", "mean_return": float(df["ret_excess_subtract_ff_rf"].mean()),
         "std_return": float(df["ret_excess_subtract_ff_rf"].std()),
         "n_obs": int(df["ret_excess_subtract_ff_rf"].notna().sum())},
        {"mode": "as_reported", "mean_return": float(df["ret_excess_as_reported"].mean()),
         "std_return": float(df["ret_excess_as_reported"].std()),
         "n_obs": int(df["ret_excess_as_reported"].notna().sum())},
    ])
    funnel.append(_funnel_row("12", f"ret_excess (main={main_mode})", df))

    cols = ["fund_id", "month", "style", "investment_style_raw", "source_status",
            "ret_decimal", "RF", "ret_excess", "ret_excess_subtract_ff_rf", "ret_excess_as_reported"]
    fund_month = df[cols].reset_index(drop=True)

    audits["funnel"] = pd.DataFrame(funnel)
    audits["styles_present"] = sorted(set(fund_month["style"]) & set(CANONICAL_11))
    return {"fund_month": fund_month, **audits}

