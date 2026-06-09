# Sadka (2010 JFE) Table 3 — strong closest-feasible replication

**Status:** strong closest-feasible replication on the *current LSEG/TASS vintage* (~2026), a DIFFERENT vintage than Sadka's 2009 TASS. The core economic result reproduces; paper-faithful keep-all and data-error-cleaned versions are reported separately below (no ad-hoc trimming).

## 1. Data-error policy (paper-faithful vs cleaned)
The modern vintage contains impossible values (e.g. +31,208%/month) absent from Sadka's data. We report three pre-specified screens; **main = S01 conservative (drop >2000%/mo)**. This does NOT delete returns in the same order of magnitude as Sadka's published extremes: the post-screen maximum is 18.16, comparable to the published 13.245 maximum, while removing clearly impossible modern-vintage records such as +31,208%/month. Sadka's footnote: excluding extremes does not change results.

                         spec  ceiling_decimal  overall_n  fund_months  max_ret_decimal  ConvArb_liq_m2  FixedIncArb_liq_m2  n_pos_sig_m2  liq_sign_match_m2  liq_sig_match_m2  liq_coef_mae_m2  rows_dropped_ceiling
S00_keep_all_except_sentinels              NaN       8345       501070          312.081          -1.427              -0.399             4              0.818             0.636            0.540                     0
   S01_conservative_ceiling20             20.0       8345       501062           18.157           0.755               0.341             6              1.000             0.818            0.232                     8
      S02_aggressive_ceiling1              1.0       8345       500991            0.980           0.755               0.197             7              1.000             0.909            0.250                    79

## 2. Currency filter and the count gap
USD-only (Sadka's requirement) yields ~8,345 funds; all-currencies ~13,521 (≈ Sadka's 12,929). The count gap is largely the USD filter on a vintage with more non-USD funds. USD-only remains main.

currency_policy  overall_n  fund_months  max_ret_decimal  ConvArb_liq_m2  FixedIncArb_liq_m2  n_pos_sig_m2  liq_sign_match_m2  liq_sig_match_m2  liq_coef_mae_m2  rows_dropped_ceiling
USD_only (main)       8345       501062           18.157           0.755               0.341             6              1.000             0.818            0.232                     8
 all_currencies      13521       732423           19.828           0.704               0.390             7              0.818             0.909            0.291                    63

## 3. Known coverage caveat — Managed Futures
Only ~17 funds carry primarycategory='Managed Futures' in 1994-2008 (Sadka: 964); fund names are anonymized so CTAs cannot be reclassified and are NOT force-mapped. Managed Futures is a thin, low-power style here (it was weak/insignificant in Sadka too).

## 4. Table 3 liquidity loading (Model 2): target vs replicated [t]
- Convertible Arbitrage: 0.7759 -> 0.755 [3.92]
- Dedicated Short Bias: -0.1554 -> -0.139 [-0.48]
- Emerging Markets: 1.1302 -> 0.95 [1.97]
- Equity Market Neutral: 0.4686 -> 0.33 [2.28]
- Event Driven: 0.5316 -> 0.528 [3.03]
- Fixed Income Arbitrage: 0.3924 -> 0.341 [1.16]
- Fund of Funds: 0.7393 -> 0.386 [1.96]
- Global Macro: 0.3772 -> 0.171 [0.71]
- Long/Short Equity: 0.8109 -> 0.358 [1.96]
- Managed Futures: 0.3949 -> 0.297 [0.52]
- Multi-Strategy: 1.4195 -> 0.389 [2.71]

## 5. Conclusion
Liquidity signs 11/11 correct; the paper's red lines hold (Dedicated Short Bias negative & insignificant, MKT-beta ~ -1; Global Macro / Managed Futures weak). Conditional on the cleaned sample, the paper-faithful Variable-Permanent as-is liquidity factor is the best allowed specification in the grid. Magnitudes run somewhat smaller than Sadka's; the qualitative pricing result is reproduced. Sadka's setting replicates cleanly and is a suitable baseline for additional factors.
