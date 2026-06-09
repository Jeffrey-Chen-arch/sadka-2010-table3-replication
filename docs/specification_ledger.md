# Specification ledger — Sadka (2010 JFE) Table 3

Single source of truth for every Table-3 setting. Each row is the paper's instruction
and the implementation choice. "P." = page of the JFE article.

## Identity
- Table 3: time-series regressions of hedge-fund returns on different factors (P.60).
- 11 investment-style portfolios; two regressions each; full sample.

## Sample
| Item | Setting | Source |
|---|---|---|
| Database | TASS (Lipper), Live + Graveyard | P.55–56 |
| Period | 1994-01 .. 2008-12 = 180 months | P.56, Table 3 header |
| Funds | monthly reporting, net of all fees, USD | P.56 |
| Dependent var | excess of risk-free rate | P.56 |
| Extreme returns | full sample kept (2006–2008 not dropped) | P.56 |
| Overall N target | 12,929 funds | Table 1 Panel C |

## 11 styles (equal-weighted monthly portfolios)
Convertible Arbitrage, Dedicated Short Bias, Emerging Markets, Equity Market Neutral,
Event Driven, Fixed Income Arbitrage, Fund of Funds, Global Macro, Long/Short Equity,
Managed Futures, Multi-Strategy. Fund of Funds kept as a separate style (P.56 fn.2).

## Liquidity factor
- Sadka (2006) **permanent-variable** price-impact component, updated to 2008 (P.56–58).
- Paper construction: AR(3) residual over 1994-2008, then **negative sign** so positive =
  liquidity improvement (P.58).
- Main spec: WRDS `Variable-Permanent` column used **as-is** (treated as final factor),
  validated by Fig.1 crisis signs and Table 2 correlations. Empirical support: raw lag-1
  autocorr = 0.169 (1994-2008) / 0.012 (full) → low persistence, consistent with an
  innovation series. AR(3)/flip/z-score are diagnostics only.
- Crisis months must be negative: 1998-09, 2001-01, 2007-08, 2008-09.

## Fung-Hsieh seven factors
| Factor | Definition | Source |
|---|---|---|
| MKT-RF | market excess return | Ken French |
| SMB | size factor | Ken French |
| DTERM | monthly change in 10-yr Treasury CMT yield | FRED DGS10/GS10 (Hsieh definition) |
| DCREDIT | monthly change in (Moody's Baa − 10-yr CMT) | FRED DBAA/BAA & DGS10/GS10 |
| PTFSBD | bond trend-following | Hsieh |
| PTFSFX | currency trend-following | Hsieh |
| PTFSCOM | commodity trend-following | Hsieh |
Table 3 uses the **non-tradable** DTERM/DCREDIT (not Table-4 tradable bond proxies).

## Regressions
- Model 1: R = a + b·(MKT-RF) + b·Liquidity.
- Model 2: + SMB + DTERM + DCREDIT + PTFSBD + PTFSFX + PTFSCOM.
- Full-sample OLS; t-stats in brackets = non-robust OLS (main); HAC = sensitivity.
- Report intercept, all slopes, R² and adjusted R².

## Units
returns decimal; French ÷100 → decimal; DTERM/DCREDIT percentage points; PTFS auto; Liq as-is.

## Forbidden in Table 3 (Table-4 rules)
24-month rolling beta; 18-month min history; decile sort; Jan-1996 start; value-weighting.

## Pass criteria (plan §27)
8/11 styles Liquidity positive & significant (both models); Dedicated Short Bias model2
Liquidity negative & insignificant (−0.1554 [−0.51]); Global Macro & Managed Futures weaker.
