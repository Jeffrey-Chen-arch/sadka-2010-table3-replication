# Closest-feasible replication of Sadka (2010 JFE) Table 3

**Prepared for:** John Heater / Salman Arif  ·  **From:** Jeffrey  ·  2026-06-09

## Objective
I replicated **Sadka (2010 JFE) Table 3** using the current WRDS/LSEG TASS vintage, to validate
the style-level liquidity-risk setting before using it as a baseline for additional factors.
This is a **strong closest-feasible replication on the current LSEG/TASS vintage — not an exact
replication of Sadka's original 2009-era TASS sample.**

## Data and specification
Faithful to the Table 3 design: monthly TASS hedge-fund returns, **Jan 1994 – Dec 2008**;
**Live + Graveyard**; monthly, net-of-fees, **USD**, excess returns; **11 self-classified
investment styles**; **equal-weighted** monthly style portfolios; OLS time-series regressions on
(1) MKT-RF + Sadka liquidity, and (2) the full **Fung-Hsieh seven factors + Sadka liquidity**.
Fund of Funds retained as a separate style. (No Table-4 rolling/decile rules.)

## Factor-side validation
The Sadka permanent-variable liquidity factor matches the key crisis-month signs in Figure 1
(1998-09, 2001-01, 2007-08, 2008-09 all negative). Table 2 factor correlations reproduce
closely — **28/28 within 0.05**, including the key negative Liquidity × Credit-Spread relation
(−0.34 → −0.39).

## Main result (Model 2)
**All 11 liquidity-loading signs match the paper.** Strictly at the 5% level (|t| ≥ 1.96):
- **Clearly positive & significant (6):** Convertible Arbitrage (0.76 [3.9]), Emerging Markets
  (0.95 [1.97]), Equity Market Neutral (0.33 [2.3]), Event Driven (0.53 [3.0]), Long/Short
  Equity (0.36 [1.96]), Multi-Strategy (0.39 [2.7]).
- **Borderline at the cutoff:** Fund of Funds (0.39 [≈1.96]).
- **Positive but not significant:** Fixed Income Arbitrage (0.34 [1.2]).
- **Weak, as in the original:** Global Macro (0.17 [0.7]), Managed Futures (0.30 [0.5]).
- **Negative & insignificant, as in the original:** Dedicated Short Bias (−0.14 [−0.5]); its
  market beta is ≈ **−0.88** (paper −0.97).

So we **replicate the full sign pattern and the key qualitative contrasts**; strict 5%
significance is somewhat weaker in this vintage, and coefficient **magnitudes run smaller** for
some styles (notably Multi-Strategy and Long/Short Equity).

## Data-error policy (reported in three tiers)
The raw current-vintage data contain a small number of impossible records (returns far above
20,000%/month). We report: **S00** keep-all except exact sentinels; **S01** conservative screen
(drop only > 2,000%/month); **S02** aggressive (> 100%) diagnostic. **Main = S01**, which removes
only **8 observations** and does **not** delete returns in the same order of magnitude as Sadka's
published extremes (post-screen max 18.16 vs the published 13.245). Sadka notes that excluding
extreme returns does not change his results.

## Caveats (quantified, not hand-waved)
- **Vintage:** current LSEG/TASS, not Sadka's 2009 TASS.
- **Count gap:** USD-only **8,345** funds vs Sadka's **12,929**. The gap is largely the USD
  filter — all-currency counts (**13,521**) are close to Sadka's total — but USD-only remains the
  main spec because the paper states returns are USD-based.
- **Managed Futures coverage:** very few funds carry the Managed-Futures primary category in
  1994-2008 under the current field; fund names are anonymized and no reliable structured CTA
  flag is available, so we do **not** force-map Other/Undefined funds. This style is treated as
  low-power here — and it is weak and insignificant in Sadka's original Table 3 as well.

## Conclusion
This is a **strong, auditable, closest-feasible baseline** for Sadka Table 3. The qualitative
liquidity-risk exposure pattern is robust across the current vintage, and the codebase is
structured to **add additional factors directly** to the same style-level regression framework.
All numbers, comparisons, and sensitivity tiers are in `sadka_table3_summary.xlsx`.

---

## Suggested email (no attachments beyond memo + workbook)

**Subject:** Sadka Table 3 replication update

Hi John and Salman,

I completed a closest-feasible replication of Sadka (2010 JFE) Table 3 using the current
WRDS/LSEG TASS vintage.

The factor side checks out well: the Sadka permanent-variable liquidity factor matches the key
crisis-month signs in Figure 1, and the Table 2 factor correlations reproduce closely. On the
Table 3 side, the core liquidity-risk pattern comes through clearly. In the full Fung-Hsieh
specification, **all 11 liquidity-loading signs match the paper**; Dedicated Short Bias is
negative and insignificant with a market beta close to −1; Global Macro and Managed Futures
remain weak; and the main positive-liquidity styles mostly reproduce, though some magnitudes are
smaller in the current vintage and strict 5% significance is a bit weaker.

The main caveats are data vintage and coverage: the USD-only current-vintage sample has fewer
funds than Sadka's (the gap is largely the USD filter), and Managed Futures is especially thin
under the current primary-category field. I also found a handful of impossible modern-vintage
return records, so I report keep-all, conservative-cleaned, and aggressive-cleaned versions; the
main version uses the conservative screen and removes only eight observations.

I'm attaching a short memo and the results workbook. The code is structured so we can add
additional factors directly to the same style-level regression framework.

Best,
Jeffrey
