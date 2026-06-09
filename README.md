# Sadka (2010, JFE) Table III — closest-feasible replication

A clean, auditable replication of **Table III** of Ronnie Sadka, *"Liquidity risk and the
cross-section of hedge-fund returns,"* **JFE 98 (2010)** — the time-series regressions of 11
equal-weighted hedge-fund **style** portfolios on the Fung–Hsieh seven factors and the Sadka
liquidity factor (Jan 1994 – Dec 2008).

> **Framing (honest):** this is a **strong closest-feasible replication on the current WRDS/LSEG
> TASS vintage**, *not* an exact reproduction of Sadka's 2009-era TASS sample. The sign pattern
> and the qualitative red lines reproduce; magnitudes and sample counts differ, and every
> difference is quantified (see `docs/memo_sadka_table3.tex` and `outputs/`).

## Headline result (Model 2 liquidity loading)
- **All 11 liquidity signs match** the paper; six styles are clearly positive & significant.
- **Dedicated Short Bias** liquidity is negative & insignificant (−0.14 [−0.5]); its market beta
  is −0.88 (paper −0.97). Global Macro / Managed Futures are weak — as in the paper.
- Convertible Arbitrage 0.76 [3.9] (paper 0.78 [4.2]); Event Driven 0.53 [3.0] (paper 0.53).

Full side-by-side comparison: `outputs/tables/table3_original_vs_replication.csv` and
`outputs/workbooks/sadka_table3_summary.xlsx`.

## Code (10 files)
```
run_replication.py     one-command pipeline (steps 00-09)
wrds_pull.py           WRDS/LSEG TASS extraction (credentials read from env, never stored)
sadka/
  core.py              config, paths, table IO, run provenance, stats utils
  liquidity.py         Sadka liquidity factor (Step 01)
  factors.py           Fama-French / Hsieh / FRED factors + panel + Table II (Step 02)
  tass.py              TASS ingest/clean (audited funnel) + 11-style mapping (Step 03)
  analysis.py          style portfolios, Table III OLS, comparison, spec grid, Table I, Fig 2
  reporting.py         Excel workbook + memo (Step 08)
tests/test_replication.py
```
Other folders: `config/` (specs + style map + ambiguity grid), `data/benchmarks/` (Sadka's
published Table I/II/III targets), `docs/` (memo + decision log + ledgers), `outputs/`
(committed aggregate results, figures, workbook, memo).

## Run it
```
pip install -r requirements.txt && pip install -e .
python -m pytest -q -m "not integration"     # unit tests, no raw data needed
python run_replication.py --through 09        # full pipeline (needs raw inputs, see below)
```
A full run needs (all gitignored / not redistributed): the WRDS Sadka liquidity xlsx, Ken French
+ Hsieh + FRED factor files, and the TASS export in `data/raw/tass/manual_exports/`. Without
them, data-dependent steps print a clear **BLOCKED** message (no traceback).

## Key caveats (quantified)
- **Data-error screen:** the modern vintage has impossible records (a +31,208%/month return). The
  main spec drops only `|return| > 2000%/mo` (8 obs); paper-faithful keep-all and an aggressive
  screen are reported alongside (`outputs/tables/data_error_sensitivity_summary.csv`).
- **Sample counts:** USD-only Overall N = 8,345 vs Sadka's 12,929 (mostly the USD filter;
  all-currency ≈ 13,521). **Managed Futures** is thin in this vintage (~17 funds vs 964; fund
  names are anonymized, so CTAs are not reclassified).

No fund-level data, raw TASS data, or credentials are committed.
