# TASS extract needed for Steps 03–05 (Table 3)

The replication needs the **Lipper TASS** (Thomson Reuters / LSEG) hedge-fund universe
on WRDS, **Live + Graveyard**, monthly. Place exports as CSV/parquet in
`manual_exports/`. The pipeline auto-detects column names via
`config/tass_column_aliases.yaml`, so exact field names need not match — but the
**content** below must be present.

## Export policy — do NOT pre-filter at WRDS
Keep the full audit trail. Export **all available** currencies, frequencies, and status
flags; the pipeline applies USD / monthly / net-of-fees / Live+Graveyard and records the
drop at each step in `tass_filter_funnel.csv`. Only pre-filter if needed to keep file size
manageable; if so, export (1) the full 1994–2008 returns table, (2) the full fund-info
table, (3) Live and Graveyard source indicators — and nothing narrower.

## A. Monthly returns (one row per fund-month)
Required fields (any alias):
- `fund_id`  — TASS/Lipper fund identifier
- `date`     — month (any parseable date; will be snapped to month-end)
- `return`   — **monthly rate of return (ROR), as reported** (net-of-fees / USD are applied
  downstream — include all share classes/currencies if feasible)

Save Live and Graveyard separately (or add a status column), e.g.:
- `manual_exports/returns_live.csv`
- `manual_exports/returns_graveyard.csv`

## B. Fund information (one row per fund)
- `fund_id`
- `investment_style` / category / strategy  (TASS primary category)
- `currency` (need USD)
- `reporting_frequency` (need Monthly)
- `net_of_fees` flag (if available)
- `live_graveyard_status` (Live vs Graveyard)
- inception / end date (optional, for diagnostics)

Save as:
- `manual_exports/fund_info_live.csv`
- `manual_exports/fund_info_graveyard.csv`

## Filters the pipeline applies (do NOT pre-filter beyond what is necessary)
1994-01 .. 2008-12; monthly reporting; USD; net of fees; Live + Graveyard;
**keep** the 2006–2008 extreme returns (do not winsorize/drop). Sadka Table 1 Overall
target = **12,929 funds**; Fund of Funds target = **4,268**.

## Template WRDS query (PostgreSQL; adjust schema/table names to your subscription)
WRDS currently exposes TASS under an LSEG product; the schema is often `tr_tass`
(older installs: `tass`). Do **not** assume table names — run
`scripts/00_inventory_project.py` first, which lists libraries/tables/columns.

```sql
-- RETURNS (run once for live, once for graveyard, or use the combined table)
SELECT fundno AS fund_id, date, ror AS return
FROM   tr_tass.<returns_table>
WHERE  date BETWEEN '1994-01-01' AND '2008-12-31';

-- FUND INFO
SELECT fundno AS fund_id, fund_name, primary_category AS investment_style,
       currency, frequency AS reporting_frequency, status AS live_graveyard_status
FROM   tr_tass.<fund_info_table>;
```

Once exports are in `manual_exports/`, run:
```
python scripts/03_prepare_tass.py --config config/spec_table3_main.yaml
```
which writes the standardized panel and `outputs/tables/tass_filter_funnel.csv`.
