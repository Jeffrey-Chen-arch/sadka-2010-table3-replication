# Sadka (2010, JFE) Table III — replication, Table 1 reconciliation & sample extension

Code for Ronnie Sadka, *"Liquidity risk and the cross-section of hedge-fund returns,"* **JFE 98 (2010)**,
on the current WRDS/LSEG TASS vintage. Three things, one small codebase:

1. **Replication** of Table III — 11 equal-weighted hedge-fund **style** portfolios on the Fung–Hsieh 7
   factors + the Sadka liquidity factor (Jan 1994 – Dec 2008).
2. **Table 1 reconciliation** — why our 1994–2008 sample differs from Sadka Table 1 (counts + return
   distribution), USD vs all-currency, with a Long/Short Equity deep dive and Managed Futures caveat.
3. **Sample extension** — the style-return panel extended to **2019-09** (appendix to 2026), the exact
   Sadka-LIQ Table 3 extended as far as the liquidity factor allows, and a **PRVT-ready** panel.

> **Honest framing:** this is a *closest-feasible* replication on the current vintage, not an exact
> reproduction of Sadka's 2009-era TASS sample. Differences are quantified, not hidden.

## Headline findings
- **Replication:** all 11 Model-2 liquidity-loading signs match the paper; 6 styles positive & significant
  at 5% (e.g. Convertible Arbitrage 0.76 [3.9] vs paper 0.78 [4.2]).
- **Reconciliation:** Sadka's N is a unique-fund count. Our USD Overall N = **8,345** vs Sadka **12,929**;
  all-currency = **13,521**. But under Sadka's own method the *return distribution* matches **USD** (median
  0.0035 vs 0.0033), not all-currency. → the count gap is mostly a current LSEG `currencycode`/vintage
  issue; **USD stays the main return sample**. Long/Short Equity all-currency N = 3,483 (−2.5% vs 3,574),
  distribution body matches to ~4 decimals. Managed Futures is a vintage coverage gap (~50 funds vs 964).
- **Extension:** the WRDS re-pull reproduces the original 1994–2008 panel **exactly**. The raw Sadka LIQ
  factor ends **2012-12**, so the exact Sadka-LIQ regression is capped there. Extending Model 2 to 2012
  **attenuates** the liquidity loadings (Long/Short Equity LIQ +0.36 [t 1.96] → −0.03 [t −0.19]) — the
  Sadka liquidity effect is concentrated in the crisis-heavy 1994–2008 window.

## Code (10 files)
```
wrds_pull.py            WRDS/LSEG TASS extraction, 1994-onward (creds read from env, never stored)
run_replication.py      Table III replication pipeline, 1994-2008 (steps 00-09)
reconcile_extend.py     Table 1 reconciliation + sample extension + PRVT-ready (reconcile|extend|all)
sadka/
  core.py               config, paths, table IO, run provenance
  liquidity.py          Sadka liquidity factor
  factors.py            Fama-French / Hsieh / FRED factors + panel
  tass.py               TASS ingest/clean (audited funnel) + 11-style mapping
  analysis.py           style portfolios, Table III OLS, comparison
  reporting.py          Excel workbook + memo
```
Other folders: `config/` (specs + style map), `data/benchmarks/` (Sadka's published targets),
`data/raw/.../README.md` (where to put inputs), `docs/`, `outputs/` (generated).

## Run it
```bash
pip install -r requirements.txt && pip install -e .

# 1) one-time: pull TASS (needs a WRDS account)
#    PowerShell:  $env:WRDS_USER="you"; $env:WRDS_PASS="pw"; python wrds_pull.py
#    bash:        WRDS_USER=you WRDS_PASS=pw python wrds_pull.py

# 2) replication (1994-2008 Table III)
python run_replication.py --through 09

# 3) reconciliation + extension (writes outputs/reconciliation, outputs/extension, outputs/prvt_ready)
python reconcile_extend.py all
```
Besides the TASS pull, a full run needs three input sets (all gitignored, not redistributed — see
`data/raw/*/README.md`): the **Sadka liquidity xlsx** (WRDS), **Ken French + Hsieh + FRED** factor files.
Data-dependent steps print a clear message (no traceback) if an input is missing.

## PRVT-ready panel (for applying an external monthly factor)
`reconcile_extend.py extend` writes `outputs/prvt_ready/`: a long style-returns table `[month, style,
style_ret]` and a lowercase wide factor panel `[month, mktrf, smb, dterm, dcredit, ptfsbd, ptfsfx, ptfscom,
liq, rf]`, to 2019-09, plus a schema and a smoke test. `liq` is real through 2012-12 and **NaN afterwards
(not forward-filled)** — so an exact LIQ + external-factor test runs through 2012-12; 2013–2019 needs
either an updated liquidity factor or factor-free models.

No fund-level data, raw TASS, or credentials are committed.
