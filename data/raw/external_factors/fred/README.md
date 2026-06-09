# FRED yields for DTERM / DCREDIT

`DTERM`  = monthly change in the 10-year Treasury constant-maturity yield.
`DCREDIT` = monthly change in (Moody's Baa yield − 10-year Treasury CMT yield).

Step 02 builds these from FRED. If this environment cannot reach FRED, **download the
series manually** from https://fred.stlouisfed.org and drop the CSVs here.

## Accepted files
**Preferred (daily; month-end is used):**
```
DGS10.csv   columns: observation_date, DGS10      (10-yr CMT, daily, percent)
DBAA.csv    columns: observation_date, DBAA       (Moody's Baa, daily, percent)
```
**Fallback (monthly average):**
```
GS10.csv    columns: observation_date, GS10       (10-yr CMT, monthly avg, percent)
BAA.csv     columns: observation_date, BAA        (Moody's Baa, monthly avg, percent)
```
(FRED's current CSV header is `observation_date`; older `DATE` is also accepted.)

## Construction
```
DTERM_t   = TenYr_eom_t  - TenYr_eom_{t-1}
CREDIT_t  = Baa_eom_t    - TenYr_eom_t
DCREDIT_t = CREDIT_t     - CREDIT_{t-1}
units: percentage points
```

## BLOCKED rule (mandatory)
If neither the preferred nor the fallback yields can be obtained, **Step 02 must stop with
a `BLOCKED` status** and must **not** produce a final `table2_factor_correlations_diff.csv`
or claim "Table 2 replicated." A partial factor audit (MKT/SMB/PTFS/Liquidity only) may be
written, clearly labelled partial.
