import pandas as pd
import numpy as np
import streamlit as st
from sqlalchemy import create_engine

# NewsAPI key =  28f45fd9da0a455980036c2c6e5b4a1b

DB_PATH = "sqlite:///screener.db"
engine = create_engine(DB_PATH, future=True)

HORIZONS = {
    "1w": 5,
    "1m": 21,
    "3m": 63,
    "6m": 126,
    "1y": 252,
}

def zscore(s: pd.Series) -> pd.Series:
    s = s.astype(float)
    std = s.std(ddof=0)
    if std == 0 or np.isnan(std):
        return s * 0.0
    return (s - s.mean()) / std

def compute_metrics(prices: pd.DataFrame, benchmark: pd.Series) -> pd.Series:
    df = prices.join(benchmark.rename("bm_close"), how="inner").sort_index()

    df["ret_1d"] = df["close"].pct_change()

    for k, n in HORIZONS.items():
        df[f"ret_{k}"] = df["close"].pct_change(n)
        df[f"bm_ret_{k}"] = df["bm_close"].pct_change(n)
        df[f"rs_{k}"] = df[f"ret_{k}"] - df[f"bm_ret_{k}"]

    df["ma20"] = df["close"].rolling(20).mean()
    df["ma60"] = df["close"].rolling(60).mean()
    df["trend_flag"] = (df["ma20"] > df["ma60"]).astype(int)

    df["vol_1m"] = df["ret_1d"].rolling(21).std() * np.sqrt(252)

    win = 126
    def mdd(x):
        x = np.asarray(x, dtype=float)
        peak = np.maximum.accumulate(x)
        dd = (x / peak) - 1.0
        return dd.min()
    df["mdd_6m"] = df["close"].rolling(win).apply(mdd, raw=False)

    latest = df.dropna().iloc[-1]
    return latest

@st.cache_data(ttl=300)
def load_master() -> pd.DataFrame:
    return pd.read_sql("SELECT * FROM series_master ORDER BY series_id", engine)

@st.cache_data(ttl=300)
def load_prices() -> pd.DataFrame:
    df = pd.read_sql("""
        SELECT sp.series_id, sm.name, sm.asset_class, sm.region, sp.date, sp.close
        FROM series_prices sp
        JOIN series_master sm ON sm.series_id = sp.series_id
    """, engine)
    df["date"] = pd.to_datetime(df["date"])
    df = df.dropna(subset=["close"])
    return df


@st.cache_data(ttl=300)
def load_ai_scores_latest():
    try:
        return pd.read_sql("""
            SELECT series_id, ai_score, n_articles
            FROM ai_scores
            WHERE date = (SELECT MAX(date) FROM ai_scores)
        """, engine)
    except Exception:
        return pd.DataFrame(columns=["series_id", "ai_score", "n_articles"])


@st.cache_data(ttl=300)
def load_ai_explanations_latest(series_id: str):
    try:
        sql = """
            SELECT title, topic, contribution, reason, published_at, article_url
            FROM ai_score_explanations
            WHERE date = (SELECT MAX(date) FROM ai_score_explanations)
              AND series_id = :sid
            ORDER BY contribution DESC
            LIMIT 10;
        """
        return pd.read_sql(sql, engine, params={"sid": series_id})
    except Exception:
        return pd.DataFrame(columns=["title", "topic", "contribution", "reason", "published_at", "article_url"])

def build_ranking(prices: pd.DataFrame) -> pd.DataFrame:
    bm = prices[prices["series_id"] == "US_SPY"].copy()
    if bm.empty:
        raise RuntimeError("US_SPY 데이터가 없습니다. fetch_stooq.py로 SPY를 먼저 적재하세요.")
    bm = bm.set_index("date")["close"].sort_index()

    rows = []
    for sid, g in prices[prices["series_id"] != "US_SPY"].groupby("series_id"):
        g = g.set_index("date")[["close"]].sort_index()
        latest = compute_metrics(g, bm)

        rows.append({
            "series_id": sid,
            "name": prices.loc[prices["series_id"] == sid, "name"].iloc[0],
            "asset_class": prices.loc[prices["series_id"] == sid, "asset_class"].iloc[0],
            "region": prices.loc[prices["series_id"] == sid, "region"].iloc[0],
            **{f"ret_{k}": float(latest[f"ret_{k}"]) for k in HORIZONS.keys()},
            **{f"rs_{k}": float(latest[f"rs_{k}"]) for k in HORIZONS.keys()},
            "trend_flag": int(latest["trend_flag"]),
            "vol_1m": float(latest["vol_1m"]),
            "mdd_6m": float(latest["mdd_6m"]),
        })

    out = pd.DataFrame(rows).dropna()

    out["base_score"] = (
        25 * zscore(out["ret_1m"]) +
        35 * zscore(out["ret_3m"]) +
        25 * zscore(out["rs_3m"]) +
        10 * out["trend_flag"] -
        15 * zscore(out["vol_1m"]) -
        20 * zscore(out["mdd_6m"])
    )

    out["regime"] = np.where(
        (out["trend_flag"] == 1) & (out["ret_1m"] > 0), "UP",
        np.where((out["trend_flag"] == 0) & (out["ret_1m"] < 0), "DOWN", "SIDE")
    )

    # sort by base_score by default and return; UI will compute final_score and assign rank
    out = out.sort_values("base_score", ascending=False).reset_index(drop=True)

    # merge latest ai scores (if table exists/has data)
    try:
        ai = load_ai_scores_latest()
        out = out.merge(ai, on="series_id", how="left")
    except Exception:
        out["ai_score"] = 0.0
        out["n_articles"] = 0

    out["ai_score"] = out.get("ai_score", 0.0).fillna(0.0)
    out["n_articles"] = out.get("n_articles", 0).fillna(0).astype(int)

    return out

def fmt_pct(x):
    return f"{x*100:.2f}%"

st.set_page_config(page_title="TrueStone Screener", layout="wide")

st.title("TrueStone Screener")
st.caption("US 섹터 ETF + 원자재 ETF + SPY 벤치마크 기반. SQLite(screener.db)에서 읽어옵니다.")


# Sidebar filters
st.sidebar.header("Filters")
asset_filter = st.sidebar.multiselect(
    "asset_class",
    ["EQUITY_SECTOR", "COMMODITY"],
    default=["EQUITY_SECTOR", "COMMODITY"]
)
regime_filter = st.sidebar.multiselect(
    "regime",
    ["UP", "SIDE", "DOWN"],
    default=["UP", "SIDE", "DOWN"]
)
top_n = st.sidebar.slider("Show Top N", min_value=5, max_value=30, value=10, step=1)
alpha = st.sidebar.slider("AI weight (alpha)", min_value=0.0, max_value=1.0, value=0.3, step=0.05)
sort_by = st.sidebar.selectbox("Sort by", ["final_score", "base_score", "ai_score"], index=0)

prices = load_prices()
# show latest available data date
if not prices.empty and "date" in prices.columns:
    latest_date = prices["date"].max()
    try:
        latest_str = pd.to_datetime(latest_date).strftime("%Y-%m-%d")
    except Exception:
        latest_str = str(latest_date)
    st.markdown(f"**Data last updated:** {latest_str}")
ranking = build_ranking(prices)

# compute final_score in UI and sort/re-rank according to sort_by
if "ai_score" not in ranking.columns:
    ranking["ai_score"] = 0.0
if "n_articles" not in ranking.columns:
    ranking["n_articles"] = 0

ranking["final_score"] = ranking["base_score"] + alpha * ranking["ai_score"]

if sort_by not in ranking.columns:
    sort_by = "final_score"
ranking = ranking.sort_values(sort_by, ascending=False).reset_index(drop=True)
ranking["rank"] = range(1, len(ranking) + 1)

filtered = ranking[
    ranking["asset_class"].isin(asset_filter) &
    ranking["regime"].isin(regime_filter)
].copy()

# Summary table
show_cols = [
    "rank", "name", "asset_class", "regime",
    "ret_1w", "ret_1m", "ret_3m", "ret_6m", "ret_1y",
    "rs_1m", "rs_3m",
    "trend_flag", "vol_1m", "mdd_6m", "base_score", "ai_score", "final_score", "n_articles"
]

display = filtered[show_cols].head(top_n).copy()

# Formatting
for c in ["ret_1w","ret_1m","ret_3m","ret_6m","ret_1y","rs_1m","rs_3m","mdd_6m"]:
    display[c] = display[c].apply(fmt_pct)
display["vol_1m"] = display["vol_1m"].apply(lambda x: f"{x:.2f}")
for c in ["base_score", "ai_score", "final_score"]:
    if c in display.columns:
        display[c] = display[c].apply(lambda x: f"{x:.2f}")
if "n_articles" in display.columns:
    display["n_articles"] = display["n_articles"].astype(int)

st.subheader(f"Top {top_n} (by score)")
st.dataframe(display, use_container_width=True, hide_index=True)

st.divider()

# Detail view
st.subheader("Detail")
names = filtered["name"].tolist()
default_idx = 0 if names else None
pick = st.selectbox("Select a series", names, index=default_idx if default_idx is not None else 0)

if pick:
    sid = filtered.loc[filtered["name"] == pick, "series_id"].iloc[0]
    s = prices[prices["series_id"] == sid][["date","close"]].sort_values("date")
    s = s.set_index("date")

    st.write(f"**{pick}** (`{sid}`)")
    st.line_chart(s["close"])

    # MA overlay (separate chart, fast MVP)
    s2 = s.copy()
    s2["ma20"] = s2["close"].rolling(20).mean()
    s2["ma60"] = s2["close"].rolling(60).mean()
    st.caption("MA20 / MA60")
    st.line_chart(s2[["ma20","ma60"]])

    row = filtered[filtered["series_id"] == sid].iloc[0]
    st.markdown(
        f"""
- **Regime**: {row['regime']}
- **1M Return**: {fmt_pct(row['ret_1m'])}  /  **3M Return**: {fmt_pct(row['ret_3m'])}
- **RS(3M vs SPY)**: {fmt_pct(row['rs_3m'])}
- **Vol(1M, annualized)**: {row['vol_1m']:.2f}
- **MDD(6M)**: {fmt_pct(row['mdd_6m'])}
- **Base Score**: {row.get('base_score', 0.0):.2f}
- **AI Score**: {row.get('ai_score', 0.0):.2f}  /  **Articles**: {int(row.get('n_articles', 0))}
- **Final Score (α={alpha})**: {row.get('final_score', 0.0):.2f}
"""
    )

    # Show top explanations (if any)
    exp = load_ai_explanations_latest(sid)
    if not exp.empty:
        st.subheader("AI Score Evidence (Top articles)")
        # convert URLs to clickable links that open in a new tab
        exp2 = exp.copy()
        def make_link(row):
            url = row.get("article_url", "")
            title = row.get("title", url)
            return f'<a href="{url}" target="_blank">{title}</a>'
        exp2["article"] = exp2.apply(make_link, axis=1)
        # show selected columns, render as HTML
        st.markdown(exp2[["article","topic","contribution","reason"]].to_html(escape=False, index=False), unsafe_allow_html=True)
