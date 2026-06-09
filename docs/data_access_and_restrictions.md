# Data access and redistribution restrictions

| Dataset | Provider | Redistributable? | Handling |
|---|---|---|---|
| Sadka liquidity factors (xlsx) | WRDS / R. Sadka | **No** (assume restricted) | gitignored; not committed |
| TASS fund-level returns & info | WRDS / LSEG (Lipper TASS) | **No** | gitignored; never committed |
| Standardized / processed TASS | derived from TASS | **No** | gitignored |
| Fama-French 3 factors | Ken French data library | Public | not committed (re-downloadable) |
| Hsieh trend-following factors | David Hsieh data library | Academic use | not committed (re-downloadable) |
| FRED DGS10/DBAA/GS10/BAA | FRED | Public | not committed |
| Sadka Table 1/2/3 target values | published paper | Published numbers | **committed** (benchmarks) |

Committable outputs are **aggregate only** (style-portfolio-level regressions, factor
correlations, comparison tables). No fund-level row ever leaves `data/`/`outputs/restricted/`.
See `.gitignore` and `docs/github_release_checklist.md`.
