# Sadka (2010 JFE) Table 3 replication — factor-side checkpoint (Steps 00–02)

**Scope:** factor side only. No TASS / hedge-fund data yet. This memo证明 the liquidity
factor and the Fung-Hsieh factor panel are constructed correctly *before* we touch TASS.

## 1. Liquidity factor (Step 01)
- Source: WRDS `Sadka-LIQ-factors-1983-2012-WRDS.xlsx`, column **Variable-Permanent**,
  used **as-is** (main spec). The WRDS file is already liquidity-oriented (crisis months
  negative); we do not re-AR(3), flip, or z-score in the main spec.
- Output `liquidity_main.parquet`: **180 months**, 1994-01 .. 2008-12, no missing.
- **Crisis-month signs (all negative, matching Fig.1):**
  1998-09 = −0.0161, 2001-01 = −0.0116, 2007-08 = −0.0123, 2008-09 = −0.0307.
- `figure1_liquidity_innovations_replication.png` visually matches the paper's Figure 1
  (deep troughs at 1998-09 and 2008-09; 2007–08 volatility spike; y-axis ≈ −0.03..+0.016).
- lag-1 autocorrelation 0.169 (low) → consistent with a near-innovation series, supporting
  the as-is choice.

## 2. Factor panel (Step 02)
- MKT-RF, SMB, RF: Ken French 3-factor (percent → decimal).
- PTFSBD/PTFSFX/PTFSCOM: David Hsieh trend-following factors (TF-Fac.xls).
- **DTERM/DCREDIT: `term_credit_source = fred_monthly_average`** (GS10 & BAA). The preferred
  daily month-end source (DGS10/DBAA) was unreachable from this environment (FRED daily
  endpoint timed out); monthly average is the pre-registered fallback. Correlations are
  scale-insensitive, **but not necessarily EOM-insensitive** (month-end vs monthly-average
  yields give slightly different change series). The monthly fallback nevertheless
  reproduces Table 2 closely, so it is acceptable for this factor-side checkpoint; **daily
  EOM DGS10/DBAA remains the preferred final check before Table 3**, and we will report
  whether coefficients change.
- `factors_main.parquet`: **8 Table-2/Table-3 factors** (MKT-RF, SMB, DTERM, DCREDIT,
  PTFSBD, PTFSFX, PTFSCOM, Liquidity) **plus RF** for excess-return construction; 180
  months, no missing.

## 3. Table 2 reproduction — PASS
- **28/28 pairwise correlations within 0.05 of the published targets; 28/28 sign matches.**
  Max abs diff = 0.0497.
- Binding anchors (target → replicated):
  - Liquidity×DCREDIT −0.34 → **−0.39**
  - Liquidity×MKT-RF 0.13 → **0.14**
  - Liquidity×SMB 0.07 → 0.08
  - Liquidity×PTFSBD −0.01 → −0.05
  - Liquidity×PTFSFX −0.10 → −0.13
  - Liquidity×PTFSCOM −0.08 → −0.09
  - DCREDIT×MKT-RF −0.38 → −0.36; DCREDIT×DTERM −0.48 → −0.48
- The single largest gap (Liquidity×DCREDIT, 0.05) is plausibly the monthly-vs-daily
  term/credit source; the AR(3) diagnostic gives −0.31 (closer). Both are within tolerance.

## 4. Liquidity-variant bake-off (`liquidity_variant_bakeoff.csv`)
| variant | crisis signs | corr(Liq,DCREDIT) | Table2 RMSE | verdict |
|---|---|---|---|---|
| **as_is** | pass | −0.39 | 0.028 | **MAIN (paper-faithful)** |
| flipped | FAIL | +0.39 | 0.326 | rejected (wrong crisis signs) |
| ar3_resid | pass | −0.31 | 0.018 | diagnostic; lowest RMSE but not clearly better |
| ar3_resid_neg | FAIL | +0.31 | 0.288 | rejected |

`as_is` passes all crisis-sign and Table 2 checks. `ar3_resid` is marginally closer
(ΔRMSE 0.01) but **not "clearly better" (<0.02 threshold)**, so per the plan as-is remains
the main spec; AR(3) is retained as a documented diagnostic.

## 5. Verdict
The factor side reproduces Figure 1 and Table 2. This de-risks the construction before the
key TASS / Table 3 stage. **Next gating input: the WRDS TASS export** (see
`data/raw/tass/README.md`).

## Provenance
Python 3.12.10, Windows-11. See `run_manifest_sanitized.json`,
`pip_freeze_step02_factors_sanitized.txt`. Liquidity file SHA-256 in
`liquidity_file_sha256.txt`. All local paths sanitized in committable copies.
