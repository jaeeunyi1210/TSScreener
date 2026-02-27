from sqlalchemy import create_engine, text

engine = create_engine("sqlite:///screener.db", future=True)

DDL = """
CREATE TABLE IF NOT EXISTS series_master (
  series_id TEXT PRIMARY KEY,      -- 예: US_XLK, COM_GLD, US_SPY
  name      TEXT NOT NULL,
  asset_class TEXT NOT NULL,        -- EQUITY_SECTOR | COMMODITY | BENCHMARK
  region    TEXT NOT NULL,          -- US (MVP는 US로 시작)
  stooq_symbol TEXT NOT NULL        -- 예: xlk.us, gld.us
);

CREATE TABLE IF NOT EXISTS series_prices (
  series_id TEXT NOT NULL,
  date      TEXT NOT NULL,          -- YYYY-MM-DD
  open      REAL,
  high      REAL,
  low       REAL,
  close     REAL,
  volume    INTEGER,
  PRIMARY KEY (series_id, date)
);

CREATE INDEX IF NOT EXISTS idx_prices_date ON series_prices(date);

-- AI scores table: date별로 series에 대한 AI 점수와 기사 수를 저장
CREATE TABLE IF NOT EXISTS ai_scores (
  date TEXT NOT NULL,
  series_id TEXT NOT NULL,
  ai_score REAL,
  n_articles INTEGER,
  PRIMARY KEY (date, series_id)
);
CREATE INDEX IF NOT EXISTS idx_ai_scores_date ON ai_scores(date);

CREATE TABLE IF NOT EXISTS ai_scores (
  date TEXT NOT NULL,              -- YYYY-MM-DD (집계 기준일)
  series_id TEXT NOT NULL,         -- US_XLK, COM_GLD 등
  ai_score REAL NOT NULL,
  n_articles INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (date, series_id)
);

CREATE INDEX IF NOT EXISTS idx_ai_scores_date ON ai_scores(date);

-- AI score explanations: per-article explanation records for AI scoring
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

"""

with engine.begin() as conn:
    for stmt in DDL.strip().split(";"):
        s = stmt.strip()
        if s:
            conn.execute(text(s))

print("DB initialized: screener.db")
