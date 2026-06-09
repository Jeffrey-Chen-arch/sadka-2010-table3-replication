# data/

| Subfolder | Contents | Committed to git? |
|-----------|----------|-------------------|
| `raw/liquidity/` | Sadka WRDS liquidity Excel | **No** (restricted) |
| `raw/external_factors/fama_french/` | Ken French 3-factor file | No |
| `raw/external_factors/hsieh/` | David Hsieh trend-following factors (TF-Fac.xls) | No |
| `raw/external_factors/fred/` | DGS10/DBAA or GS10/BAA yields | No |
| `raw/tass/manual_exports/` | TASS fund returns + fund info (WRDS export) | **No** (restricted, fund-level) |
| `interim/` | standardized TASS parquet | No |
| `processed/` | liquidity_main, factors_main, style portfolios | No |
| `benchmarks/` | Sadka published Table 1/2/3 target values | **Yes** |
| `schema/` | expected column contracts | Yes |

Only `benchmarks/*.csv`, `schema/*.yaml`, and this README are committed. Everything else
under `data/` is gitignored (`data/raw/**`, `data/interim/**`, `data/processed/**`).
