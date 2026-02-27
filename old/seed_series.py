from sqlalchemy import create_engine, text

engine = create_engine("sqlite:///screener.db", future=True)

SERIES = [
  # Benchmark
  ("US_SPY", "S&P 500 (SPY)", "BENCHMARK", "US", "spy.us"),

  # US Equity Sectors (Select Sector SPDR)
  ("US_XLK", "Technology (XLK)", "EQUITY_SECTOR", "US", "xlk.us"),
  ("US_XLF", "Financials (XLF)", "EQUITY_SECTOR", "US", "xlf.us"),
  ("US_XLE", "Energy (XLE)", "EQUITY_SECTOR", "US", "xle.us"),
  ("US_XLV", "Health Care (XLV)", "EQUITY_SECTOR", "US", "xlv.us"),
  ("US_XLI", "Industrials (XLI)", "EQUITY_SECTOR", "US", "xli.us"),
  ("US_XLY", "Consumer Discretionary (XLY)", "EQUITY_SECTOR", "US", "xly.us"),
  ("US_XLP", "Consumer Staples (XLP)", "EQUITY_SECTOR", "US", "xlp.us"),
  ("US_XLU", "Utilities (XLU)", "EQUITY_SECTOR", "US", "xlu.us"),
  ("US_XLB", "Materials (XLB)", "EQUITY_SECTOR", "US", "xlb.us"),
  ("US_XLRE", "Real Estate (XLRE)", "EQUITY_SECTOR", "US", "xlre.us"),
  ("US_XLC", "Communication (XLC)", "EQUITY_SECTOR", "US", "xlc.us"),

  # Commodities (ETF proxies)
  ("COM_GLD", "Gold (GLD)", "COMMODITY", "US", "gld.us"),
  ("COM_DBC", "Broad Commodities (DBC)", "COMMODITY", "US", "dbc.us"),
  ("COM_USO", "Crude Oil (USO)", "COMMODITY", "US", "uso.us"),
]

UPSERT = """
INSERT INTO series_master(series_id, name, asset_class, region, stooq_symbol)
VALUES (:series_id, :name, :asset_class, :region, :stooq_symbol)
ON CONFLICT(series_id) DO UPDATE SET
  name=excluded.name,
  asset_class=excluded.asset_class,
  region=excluded.region,
  stooq_symbol=excluded.stooq_symbol;
"""

with engine.begin() as conn:
    for series_id, name, asset_class, region, stooq_symbol in SERIES:
        conn.execute(text(UPSERT), {
            "series_id": series_id,
            "name": name,
            "asset_class": asset_class,
            "region": region,
            "stooq_symbol": stooq_symbol
        })

print("Seeded series_master.")
