# Acquisition Intelligence Tool

A Streamlit-based company screening tool for evaluating acquisition targets. Enter a company domain, configure a thesis, and get a scored analysis drawn from live data across six signal sources.

**Live demo:** [https://ai-lead-enrichment.streamlit.app/](https://ai-lead-enrichment.streamlit.app/)

---

## What It Does

1. **Enriches** the company from public sources (website, jobs, news, GitHub, funding, financials)
2. **Analyzes** signals with GPT-4o to produce a narrative and structured flags
3. **Scores** the company 0–10 against a configurable acquisition thesis
4. **Surfaces** evidence - clickable news articles, job postings with URLs, tech stack, funding signals

---

## Signal Sources

| Source | What it captures |
|---|---|
| **Website scraping** | Company description, tech stack detected from HTML |
| **Adzuna + careers page** | Job volume, role types, hiring signals; entity-resolved per posting |
| **NewsAPI** | Recent news (28-day window), relevance-scored, AI-classified |
| **GDELT** | Broader news fallback (free, no key); disabled via `GDELT_ENABLED=false` |
| **GitHub API** | Repo count, stars, recent commit activity |
| **SEC EDGAR + scraping** | Funding signals, revenue indicators |

---

## Scoring Model

- **Base score**: 5.0 (neutral — missing data is not penalized)
- **Bucket scoring** with diminishing returns for jobs, news, GitHub activity
- **Confidence %**: signals found out of 6 possible sources
- **Sub-scores**: Growth, Quality, Risk (displayed as bars)
- **Thesis alignment**: sector, region, maturity stage, ARR range

Hiring signals are gated on job confidence (>=0.70 full weight, 0.40-0.70 half, <0.40 discarded).

---

## Running Locally

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

---

## Environment Variables

```
OPENAI_API_KEY=...          # Required
ABSTRACT_API_KEY=...        # Optional - company metadata
NEWS_API_KEY=...            # Optional - primary news source
ADZUNA_APP_ID=...           # Optional - job postings
ADZUNA_APP_KEY=...          # Optional - job postings
GITHUB_TOKEN=...            # Optional - higher GitHub rate limit
GDELT_ENABLED=false         # Set to disable GDELT if rate-limited
```

---

## Architecture

```
streamlit_app.py            # UI - tabs: Analysis, Evidence, Scoring
app/
  config.py                 # Settings loaded from .env
  models.py                 # Pydantic schemas
  services/
    enrichment.py           # Orchestrates all collectors
    scoring.py              # Deterministic scoring engine
    llm.py                  # GPT-4o narrative + structured analysis
    news.py                 # NewsAPI primary, GDELT fallback, daily cache
    news_analysis.py        # GPT-4o-mini per-article sentiment + signals
    jobs.py                 # Adzuna + careers page, entity resolution
    github.py               # GitHub API
    funding.py              # SEC EDGAR + funding signals
    financials.py           # Public company financial data
    techstack.py            # Tech stack detected from website HTML
    cache.py                # File-based daily cache
```

---

## News System

- **Primary**: NewsAPI with 28-day window, relevance-scored (name in title +40, description +25, trusted source +10, recency boost)
- **Fallback**: GDELT DOC 2.0 API, single query with exponential backoff, triggered only if NewsAPI returns fewer than 5 articles
- **AI analysis**: GPT-4o-mini classifies each article — sentiment, business impact, confidence, signal tags, risk flags
- **Cache**: results cached daily per company in `.cache/news/`

## Jobs System

- Adzuna exact-phrase search + careers page scraping
- Per-posting entity resolution score (name similarity, domain match, industry keywords, manual-labor flag detection)
- Postings scoring below 0.50 entity confidence are discarded with a warning log
- Industry profiles: fintech, SaaS, AI, cybersecurity, ecommerce, healthcare, edtech, proptech, and more
