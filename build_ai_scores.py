import os
import math
import datetime
import sqlite3
import requests

DB = "screener.db"
NEWSAPI_KEY = os.environ.get("NEWSAPI_KEY")

# series_id -> News query (MVP)
SERIES_QUERIES = {
    "US_XLE": "oil OR crude OR OPEC OR refinery",
    "COM_USO": "WTI OR crude oil OR Brent OR OPEC",
    "COM_GLD": "gold OR inflation OR real yields OR Fed",
    "US_XLK": "semiconductor OR AI chips OR Nvidia OR Big Tech",
    "COM_DBC": "commodity prices OR commodities index",
    # 필요하면 추가
    # "US_XLF": "banks OR financials OR credit spreads OR Fed",
}

def ensure_tables(conn: sqlite3.Connection):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS ai_scores (
      date TEXT NOT NULL,
      series_id TEXT NOT NULL,
      ai_score REAL NOT NULL,
      n_articles INTEGER NOT NULL DEFAULT 0,
      PRIMARY KEY(date, series_id)
    );
    CREATE INDEX IF NOT EXISTS idx_ai_scores_date ON ai_scores(date);

    CREATE TABLE IF NOT EXISTS ai_score_explanations (
      date TEXT NOT NULL,
      series_id TEXT NOT NULL,
      article_url TEXT NOT NULL,
      title TEXT,
      published_at TEXT,
      topic TEXT,
      sentiment INTEGER,
      impact INTEGER,
      confidence REAL,
      novelty REAL,
      decay REAL,
      contribution REAL,
      reason TEXT,
      PRIMARY KEY(date, series_id, article_url)
    );
    CREATE INDEX IF NOT EXISTS idx_ai_exp_date ON ai_score_explanations(date);
    CREATE INDEX IF NOT EXISTS idx_ai_exp_series ON ai_score_explanations(series_id);
    """)

def decay(days: int, half_life_days: int = 7) -> float:
    """Exponential decay with a half-life."""
    lam = math.log(2) / half_life_days
    return math.exp(-lam * days)

def simple_sentiment(title: str, desc: str) -> int:
    """
    MVP sentiment heuristic: -2..+2
    (나중에 LLM 기반 구조화 추출로 교체할 부분)
    """
    text = ((title or "") + " " + (desc or "")).lower()

    pos = ["surge", "rise", "rally", "beat", "record", "strong", "gain", "easing", "cut", "boost"]
    neg = ["plunge", "fall", "miss", "crisis", "sanction", "war", "delay", "slump", "weak", "downgrade"]

    score = sum(1 for w in pos if w in text) - sum(1 for w in neg if w in text)
    if score >= 2:
        return 2
    if score == 1:
        return 1
    if score == 0:
        return 0
    if score == -1:
        return -1
    return -2

def fetch_news(query: str, days_back: int = 3, page_size: int = 30):
    if not NEWSAPI_KEY:
        raise RuntimeError("NEWSAPI_KEY env var not set. Example: export NEWSAPI_KEY='...'")

    now = datetime.datetime.utcnow()
    start = now - datetime.timedelta(days=days_back)

    url = "https://newsapi.org/v2/everything"
    params = {
        "q": query,
        "from": start.strftime("%Y-%m-%d"),
        "to": now.strftime("%Y-%m-%d"),
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": page_size,
        "apiKey": NEWSAPI_KEY,
    }
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    if data.get("status") != "ok":
        raise RuntimeError(f"NewsAPI error: {data}")
    return data.get("articles", [])

def upsert_explanation(conn, row):
    conn.execute("""
    INSERT OR REPLACE INTO ai_score_explanations
    (date, series_id, article_url, title, published_at, topic,
     sentiment, impact, confidence, novelty, decay, contribution, reason)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, row)

def upsert_ai_score(conn, date, series_id, ai_score, n_articles):
    conn.execute("""
    INSERT OR REPLACE INTO ai_scores(date, series_id, ai_score, n_articles)
    VALUES (?, ?, ?, ?)
    """, (date, series_id, ai_score, n_articles))

def main():
    today = datetime.date.today().isoformat()
    conn = sqlite3.connect(DB)
    ensure_tables(conn)

    # clip limit: 뉴스가 base_score를 뒤집지 않게
    K = 12.0

    # 동일 URL 중복 방지용(하루 실행 내)
    seen = set()

    for series_id, q in SERIES_QUERIES.items():
        print(f"\n[{series_id}] query = {q}")
        try:
            articles = fetch_news(q, days_back=3, page_size=30)
        except Exception as e:
            print(f"  ERROR fetch_news: {e}")
            continue

        total = 0.0
        n = 0

        for a in articles:
            url = a.get("url")
            if not url or url in seen:
                continue
            seen.add(url)

            title = a.get("title") or ""
            desc = a.get("description") or ""
            published = a.get("publishedAt") or ""
            topic = "auto"  # MVP: 고정(나중에 LLM이 topic 분류)

            # ---- MVP: 룰 기반 피처 (LLM로 교체 예정) ----
            sentiment = simple_sentiment(title, desc)   # -2..+2
            impact = 1                                  # 0..3 (MVP 고정)
            confidence = 0.7                            # 0..1 (MVP 고정)
            novelty = 0.8                               # 0..1 (MVP 고정)

            # publishedAt -> days
            days = 0
            try:
                pub_dt = datetime.datetime.fromisoformat(published.replace("Z", "+00:00"))
                days = (datetime.datetime.now(datetime.timezone.utc) - pub_dt).days
            except:
                pass

            d = decay(days, half_life_days=7)

            contribution = sentiment * impact * confidence * novelty * d
            if contribution == 0:
                continue

            reason = f"sent={sentiment}, impact={impact}, conf={confidence}, nov={novelty}, decay={d:.2f}"

            upsert_explanation(conn, (
                today, series_id, url, title, published, topic,
                sentiment, impact, confidence, novelty, d, contribution,
                reason
            ))

            total += contribution
            n += 1

        ai_score = max(-K, min(K, total))
        upsert_ai_score(conn, today, series_id, ai_score, n)
        conn.commit()

        print(f"  ai_score={ai_score:.3f}  n_articles={n}")

    conn.close()
    print("\nDone.")

if __name__ == "__main__":
    main()
