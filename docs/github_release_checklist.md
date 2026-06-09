# GitHub release checklist

Before any push, run:
```
git status --ignored
git ls-files
```

Must NOT appear in `git ls-files`:
```
data/raw/tass/...
data/raw/liquidity/Sadka-LIQ-factors-1983-2012-WRDS.xlsx
data/interim/...
data/processed/...
outputs/restricted/...
.env
any WRDS credentials
any fund-level monthly returns
```

Safe to commit:
```
README.md  requirements.txt  pyproject.toml
config/  docs/  src/  scripts/  tests/
data/README.md  data/benchmarks/*.csv  data/schema/*.yaml
outputs/tables/table3_original_vs_replication.csv
outputs/tables/table3_liquidity_focus.csv
outputs/tables/spec_grid_best_10.csv
outputs/workbooks/sadka_table3_summary.xlsx
outputs/memos/sadka_table3_replication_memo_for_prof.md
outputs/figures/figure1_liquidity_innovations_replication.png
outputs/figures/figure2_style_return_vs_liquidity_beta.png
```
