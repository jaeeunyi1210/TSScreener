import pandas as pd
import numpy as np
from sqlalchemy import create_engine

engine = create_engine("sqlite:///screener.db", future=True)

def compute_metrics(prices: pd.DataFrame, benchmark: pd.Series) -> pd.DataFrame:
    # prices: columns=[date, close] index=date
    # benchmark: close series indexed by date
    # 공통 날짜 정렬
    df = prices.join(benchmark.rename("bm_close"), how="inner")
    df = df.sort_index()

    # 일간 수익률
    df["ret_1d"] = df["close"].pct_change()
    df["bm_ret_1d"] = df["bm_close"].pct_change()

    # 1M(대략 21거래일) 수익률
    n = 21
    df["ret_1m"] = df["close"].pct_change(n)
    df["bm_ret_1m"] = df["bm_close"].pct_change(n)
    df["rs_1m"] = df["ret_1m"] - df["bm_ret_1m"]

    # 추세: MA20 - MA60 (단순)
    df["ma20"] = df["close"].rolling(20).mean()
    df["ma60"] = df["close"].rolling(60).mean()
    df["trend"] = df["ma20"] - df["ma60"]
    df["trend_flag"] = (df["trend"] > 0).astype(int)

    # 변동성(1M): 일간수익률 std * sqrt(252)
    df["vol_1m"] = df["ret_1d"].rolling(21).std() * np.sqrt(252)

    # 최신값만 반환
    latest = df.dropna().iloc[-1:]
    return latest[["ret_1m","rs_1m","trend_flag","vol_1m"]]

def zscore(s: pd.Series) -> pd.Series:
    if s.std(ddof=0) == 0:
        return s * 0
    return (s - s.mean()) / s.std(ddof=0)

def main():
    # 가격 데이터 가져오기
    prices = pd.read_sql("""
        SELECT sp.series_id, sm.name, sm.asset_class, sp.date, sp.close
        FROM series_prices sp
        JOIN series_master sm ON sm.series_id = sp.series_id
    """, engine)

    prices["date"] = pd.to_datetime(prices["date"])
    prices = prices.dropna(subset=["close"])

    # 벤치마크(SPY) 시계열
    bm = prices[prices["series_id"] == "US_SPY"].copy()
    bm = bm.set_index("date")["close"].sort_index()

    rows = []
    for sid, g in prices[prices["series_id"] != "US_SPY"].groupby("series_id"):
        g = g.set_index("date")[["close"]].sort_index()
        m = compute_metrics(g, bm)
        if m.empty:
            continue
        row = m.iloc[0].to_dict()
        meta = prices[prices["series_id"] == sid][["name","asset_class"]].iloc[0].to_dict()
        rows.append({"series_id": sid, **meta, **row})

    out = pd.DataFrame(rows).dropna()

    # 스코어(빠른 MVP): 모멘텀 + RS + 추세 - 변동성
    out["score"] = (
        40 * zscore(out["ret_1m"]) +
        30 * zscore(out["rs_1m"]) +
        10 * out["trend_flag"] -
        20 * zscore(out["vol_1m"])
    )

    out = out.sort_values("score", ascending=False)

    # 출력
    pd.set_option("display.width", 180)
    pd.set_option("display.max_rows", 50)

    print("\n=== TOP 10 (Sector+Commodities) by SCORE ===")
    print(out[["name","asset_class","ret_1m","rs_1m","trend_flag","vol_1m","score"]].head(10))

    print("\n=== BOTTOM 10 (Sector+Commodities) by SCORE ===")
    print(out[["name","asset_class","ret_1m","rs_1m","trend_flag","vol_1m","score"]].tail(10))

if __name__ == "__main__":
    main()
