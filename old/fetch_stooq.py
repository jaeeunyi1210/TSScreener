import pandas as pd
import requests
from io import StringIO
from sqlalchemy import create_engine, text

engine = create_engine("sqlite:///screener.db", future=True)

def fetch_stooq_csv(stooq_symbol: str) -> pd.DataFrame:
    url = f"https://stooq.com/q/d/l/?s={stooq_symbol}&i=d"
    r = requests.get(url, timeout=30)
    r.raise_for_status()

    df = pd.read_csv(StringIO(r.text))
    df = df.rename(columns={
        "Date": "date",
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "volume",
    })

    if "date" not in df.columns or "close" not in df.columns:
        raise ValueError(f"Unexpected CSV format for {stooq_symbol}")

    df["date"] = df["date"].astype(str)
    return df

def upsert_prices(series_id: str, df: pd.DataFrame) -> int:
    df = df.copy()
    df["series_id"] = series_id
    df = df[["series_id", "date", "open", "high", "low", "close", "volume"]]
    df = df.dropna(subset=["date", "close"])
    df.to_sql("series_prices", engine, if_exists="append", index=False)
    return len(df)

def get_last_date(series_id: str):
    q = "SELECT MAX(date) AS last_date FROM series_prices WHERE series_id = :sid"
    last = pd.read_sql(q, engine, params={"sid": series_id})
    val = last.iloc[0]["last_date"]
    return None if pd.isna(val) else str(val)

def main():
    series = pd.read_sql("SELECT series_id, stooq_symbol FROM series_master", engine)
    total = 0

    for _, row in series.iterrows():
        sid, sym = row["series_id"], row["stooq_symbol"]
        print(f"Fetching {sid} ({sym}) ...")

        try:
            df = fetch_stooq_csv(sym)
        except Exception as e:
            print(f"  ERROR fetch: {e}")
            continue

        last_date = get_last_date(sid)
        if last_date:
            df = df[df["date"] > last_date]

        if df.empty:
            print("  up-to-date")
            continue

        try:
            n = upsert_prices(sid, df)
            total += n
            print(f"  inserted {n} rows (since {last_date})")
        except Exception as e:
            # 혹시라도 중복/락 등으로 실패 시 로그만 남기고 다음 시리즈로
            print(f"  ERROR insert: {e}")

    print(f"Done. inserted total rows: {total}")

if __name__ == "__main__":
    main()
