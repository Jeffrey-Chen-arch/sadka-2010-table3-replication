"""Pull TASS returns + fund info into data/raw/tass/manual_exports/ (gitignored).

Reads WRDS_USER / WRDS_PASS from the environment (never printed or stored). Pulls 1994-01 onward (the
current LSEG vintage runs to ~2026); run_replication.py caps its own sample at 2008-12 and reconcile_extend.py
chooses its windows, so one pull serves both. Columns are aliased to the names the pipeline recognizes.

Run:
    # PowerShell:  $env:WRDS_USER="you"; $env:WRDS_PASS="pw"; python wrds_pull.py
    # bash:        WRDS_USER=you WRDS_PASS=pw python wrds_pull.py
"""
import os

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

from sadka.core import ensure_dir

user = os.environ["WRDS_USER"]
pw = os.environ["WRDS_PASS"]
url = URL.create("postgresql+psycopg2", username=user, password=pw,
                 host="wrds-pgdata.wharton.upenn.edu", port=9737, database="wrds")
engine = create_engine(url, connect_args={"sslmode": "require"}, pool_pre_ping=True)
out = ensure_dir("data/raw/tass/manual_exports")

# Returns 1994-01 onward, with Live/Graveyard status attached. Keep all currencies/funds; the
# pipeline funnel does the USD/monthly/net-of-fees/style filtering and audits each step.
ret_sql = """
SELECT pp.productreference AS fund_id, pp.date AS date, pp.rateofreturn AS ror, pp.nav AS nav,
       pd.live_graveyard AS status
FROM tr_tass.productperformance pp
LEFT JOIN tr_tass.productdetails pd USING (productreference)
WHERE pp.date >= '1994-01-01'
"""
print("pulling returns 1994-onward ...", flush=True)
ret = pd.read_sql(ret_sql, engine)
print(f"  returns rows: {len(ret)} | funds: {ret['fund_id'].nunique()} | max date: {pd.to_datetime(ret['date']).max().date()}", flush=True)
ret.to_parquet(out / "tr_tass_returns_1994_latest.parquet", index=False)

# Fund info (rich; keeps fee/classification fields). grossnett: 'N'(et)/NULL -> 'net'; else 'gross'.
info_sql = """
SELECT productreference AS fund_id, name AS name,
       primarycategory AS strategy, currencycode AS currency,
       trackingfrequency AS frequency,
       CASE WHEN grossnett = 'N' OR grossnett IS NULL THEN 'net' ELSE 'gross' END AS net_of_fees,
       managementfee AS management_fee, incentivefee AS incentive_fee,
       live_graveyard AS status, inceptiondate AS inception_date, performanceenddate AS end_date
FROM tr_tass.productdetails
"""
print("pulling fund info ...", flush=True)
info = pd.read_sql(info_sql, engine)
print("  fund-info rows:", len(info), flush=True)
info.to_parquet(out / "tr_tass_fundinfo_full.parquet", index=False)
print("DONE. wrote tr_tass_returns_1994_latest.parquet + tr_tass_fundinfo_full.parquet", flush=True)
