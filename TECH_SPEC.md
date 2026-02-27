# Screener2 Technical Specification

## 📁 프로젝트 개요

이 저장소(`02.screener2`)는 **미국 섹터·원자재 ETF 스크리너**를 구현한 소형 파이썬 애플리케이션입니다. 단일 디렉터리 안에 스크립트들이 모여 있으며, 데이터 저장은 SQLite를 사용합니다.

---

## 🗄 데이터베이스 설계

### 파일

- **`screener.db`** – 작업 디렉터리에 생성되는 SQLite 데이터베이스.

### 테이블 구조 (구현: `init_db.py`)

| 테이블명 | 용도 |
|----------|------|
| `series_master` | 종목 메타데이터<br> (`series_id`, `name`, `asset_class`, `region`, `stooq_symbol`) |
| `series_prices` | 일별 가격 기록<br> (`series_id`, `date`, `open`, `high`, `low`, `close`, `volume`) |
| `ai_scores` | (선택) AI가 계산한 날짜별 점수 & 기사 수 |
| `ai_score_explanations` | (선택) 점수 계산에 사용된 기사별 상세 정보 |

### 인덱스

- `idx_prices_date` on `series_prices(date)`
- `idx_ai_scores_date` on `ai_scores(date)`
- `idx_ai_exp_date`, `idx_ai_exp_series` on `ai_score_explanations`

> 💡 `CREATE TABLE IF NOT EXISTS`를 사용하여 재실행 시에도 안전합니다.

---

## ⚙️ 기능별 스크립트

| 파일 | 역할 |
|------|------|
| `init_db.py` | DB 파일 생성 및 스키마 초기화 |
| `fetch_stooq.py` | Stooq API 또는 CSV를 통해 가격 데이터를 다운로드 → `series_prices`에 삽입 |
| `seed_series.py` | `series_master`에 초기 종목 목록 적재 (주로 수동 또는 하드코딩) |
| `run_daily.py` | *Daily update orchestrator* (가격 + AI 점수 갱신) |
| `build_ai_scores.py` | (옵션) 뉴스 API 등을 사용해 각 종목에 대한 AI 점수를 계산하고 저장 |
| `rank_sectors.py` | CLI용 랭킹 생성 스크립트 ─ 콘솔 출력 |
| `generate_analysis_pdf.py` | 분석 결과를 PDF로 렌더링 |
| `app.py` | Streamlit 웹 UI – DB에서 데이터 불러와 필터/정렬 가능한 스크리너 제공 |

---

## 🧠 핵심 알고리즘

1. **지표 계산** (`app.py::compute_metrics`)
   - 주어진 종목과 벤치마크(SPY)의 종가 시리즈를 병합
   - **수익률**: 1일, 1주, 1개/3/6/12개월
   - **RS (relative strength)**: 각 기간의 종목 수익률 – 벤치마크 수익률
   - 이동평균(20/60일) → **추세 플래그**
   - 월간 변동성(연율) 및 6개월 최대 낙폭
   - 결과는 각 종목에 대해 최신 시점의 값으로 요약

2. **랭킹 점수** (`app.py::build_ranking`)
   - `HORIZONS`(기간 사전)에 따라 지표 계산
   - Z‑score 기반 표준화 후 가중합:

     ```
     base_score =
           25*z(ret_1m)
         + 35*z(ret_3m)
         + 25*z(rs_3m)
         + 10*trend_flag
         - 15*z(vol_1m)
         - 20*z(mdd_6m)
     ```

   - **Regime**: up/side/down 분류
   - AI 점수가 있으면 병합, `final_score = base_score + α * ai_score`
   - 정렬/필터링은 UI에서 처리

3. **AI 점수 생성** (`build_ai_scores.py`, 내용 미공개)
   - 뉴스 기사 텍스트 분석 → `ai_score`, `contribution`, `reason` 등 저장
   - 스크립트 유무에 따라 `run_daily`에서 선택적 실행

---

## 🗂 사용 흐름

1. **셋업**
   ```bash
   python init_db.py          # DB 스키마 생성
   python seed_series.py      # 종목 목록 채우기
   ```

2. **데이터 적재/갱신**
   ```bash
   python run_daily.py        # 가격+AI 점수 업데이트
   ```
   - 크론잡·GitHub Actions 등에서 자동화 가능

3. **탐색/분석**
   - **웹**: `streamlit run app.py` → 브라우저에서 스크리너 사용  
   - **CLI**: `python rank_sectors.py`로 텍스트 결과 확인  
   - **DB 브라우저**: `sqlite3` 또는 VS Code 확장으로 데이터 직접 보기

4. **레포트**
   - `generate_analysis_pdf.py`로 PDF 생성

---

## ✅ 요약

이 프로젝트는 **SQLite 기반의 단순한 계량 퀀트 도구**입니다. 데이터베이스 스키마는 간결하며, 가격과 (옵션) AI 점수를 적재한 뒤 통계적/기술적 지표를 계산하여 **Streamlit 인터페이스**를 통해 ETF를 스크리닝합니다. 알고리즘은 전통적 퍼포먼스 지표와 이동평균, 변동성, 최대 낙폭에 z‑score 가중합을 결합한 형태로, 쉽게 확장하거나 다른 자산 클래스로도 응용할 수 있습니다.

---

## 🚀 Streamlit Cloud 배포

1. **GitHub 저장소 준비**
   * 프로젝트를 GitHub에 커밋/푸시한다.
   * `requirements.txt`를 생성한다 (`pip freeze > requirements.txt`).
   * `screener.db` 파일도 리포지토리에 커밋하거나, 외부 저장소에서 접근하도록 경로를 설정한다.

2. **Streamlit Cloud에 앱 추가**
   * https://streamlit.io/cloud 에서 계정 생성(또는 로그인).
   * **New app** 버튼 클릭 → 리포지토리와 브랜치 선택 → `app.py` 파일 지정.
   * 필요하면 `DB_PATH`나 API 키를 **Secrets**에 환경변수로 등록.
   * 배포가 완료되면 URL이 제공되고 접속하면 앱이 실행된다.

3. **DB 갱신**
   * Streamlit Cloud 서버는 사용자가 코드를 직접 실행할 수 없으므로 데이터 갱신은 외부에서 처리해야 한다.
   * 가장 간편한 조합: **Streamlit Cloud + GitHub Actions**
     1. GitHub Actions 워크플로를 작성하여 `run_daily.py`를 매일 실행
     2. `screener.db`를 커밋/푸시하면 Cloud가 읽어들이는 파일이 최신화됨
     3. 워크플로 예시는 아래에 추가되어 있음
   * 다른 대안
     - 외부 서버나 개인 PC에서 cron으로 실행 후 DB를 GitHub에 업로드
     - 클라우드 스토리지(S3/Cloud Storage 등)에 DB를 둔 뒤 외부 스케줄러로 갱신

---

### 📅 GitHub Actions 예시

`.github/workflows/update-db.yml` 파일:

```yaml
name: daily-update

on:
  schedule:
    - cron: '0 2 * * *'      # 매일 UTC 02:00

jobs:
  update:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install deps
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
      - name: Run daily script
        run: |
          python run_daily.py
      - name: Commit updated DB
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "actions@github.com"
          git add screener.db
          git commit -m "Daily DB update" || echo "no changes"
          git push
```

이렇게 설정하면 GitHub상에서 **매일 `run_daily.py`가 호출되고, 결과 DB가 다시 커밋되므로**
Streamlit Cloud가 최신 데이터를 서비스할 수 있습니다.

---

4. **무료 플랜**
   * 공개 GitHub repo만 가능(비공개는 유료). 
   * 무료 계층은 월별 계산 시간/메모리/동시 사용자 수 제한이 있으므로
     가볍게 테스트용으로 적합.

> 🔧 사용자와 데이터가 많아지면 Heroku, Docker 등 다른 옵션을 고려해야 합니다.
