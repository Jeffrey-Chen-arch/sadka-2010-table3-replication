# Discrepancy log (paper vs replication)

Populated by Steps 02/05/06. One row per material discrepancy.

| Table/cell | Paper value | Replicated | Diff | Most likely cause | Status |
|---|---|---|---|---|---|
| _(to be filled)_ | | | | | |

## Table 2 printed p-values (NOT an OCR error)
The **published** Table 2 prints several p-values that are internally inconsistent with the
reported Pearson correlations and the 180-month sample size — e.g.
`PTFSFX×DCREDIT corr=0.29, printed p=[0.42]`, `PTFSCOM×DTERM corr=-0.08, printed p=[0.01]`,
`PTFSCOM×DCREDIT corr=0.19, printed p=[0.66]`. The PDF image itself shows these values, so
this is a typesetting/entry anomaly in the original article, **not** our OCR error.

Handling: we preserve the printed values in `pvalue_target_printed` for transparency, but
Table 2 diagnostics **score only the correlations**. Formula-implied p-values are recomputed
in Step 02 from `corr_target` and n=180 into `pvalue_formula_n180`. Binding correlation
anchors: `Liquidity×DCREDIT=-0.34`, `Liquidity×MKT-RF=0.13`, `DCREDIT×MKT-RF=-0.38`,
`DCREDIT×DTERM=-0.48`.
