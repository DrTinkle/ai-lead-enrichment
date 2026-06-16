"""
News pipeline — multi-source fetch, relevance filtering, deduplication,
category classification, and AI sentiment analysis.

Strategy:
  1. NewsAPI primary (cleaner articles, better entity matching via quoted query)
  2. GDELT fallback (free forever, broader coverage, noisier)
  3. Both sources cached per company per calendar day to avoid rate limits
  4. Single broad query — category classification done locally by AI, not via separate queries
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone, date
from pathlib import Path
from typing import Optional

import requests

from app.config import settings

logger = logging.getLogger(__name__)
TIMEOUT = 12

_NEWSAPI_URL = "https://newsapi.org/v2/everything"
_GDELT_URL   = "https://api.gdeltproject.org/api/v2/doc/doc"
_GDELT_UA    = "Mozilla/5.0 (compatible; lead-enrichment/0.1)"

# Daily cache stored alongside the main .cache directory
_NEWS_CACHE_DIR = Path(__file__).parent.parent.parent / ".cache" / "news"

_TRUSTED_SOURCES = {
    "techcrunch.com","reuters.com","bloomberg.com","wsj.com","ft.com",
    "forbes.com","wired.com","theverge.com","arstechnica.com","venturebeat.com",
    "businessinsider.com","cnbc.com","axios.com","sifted.eu","eu-startups.com",
}

_CATEGORIES = {
    "funding":        ["raised","funding","series a","series b","series c","seed round",
                       "investment","vc","venture","capital","valuation"],
    "acquisition":    ["acquired","acquisition","merger","bought","takeover","deal","purchase"],
    "partnership":    ["partnership","partner","collaboration","integrat","alliance","joint venture"],
    "product_launch": ["launch","launched","announces","new product","released","unveils","debuts"],
    "hiring":         ["hiring","expan","new office","headcount","workforce grows"],
    "layoffs":        ["layoff","laid off","job cuts","restructur","downsiz","redundanc"],
    "lawsuit":        ["lawsuit","sued","litigation","legal action","settl","penalty","fine","regulatory"],
    "breach":         ["breach","hack","cyberattack","data leak","security incident","ransomware"],
    "executive":      ["ceo","cto","cfo","appoints","steps down","resigns","new chief","leadership"],
}


# ── Daily news cache ──────────────────────────────────────────────────────────

def _cache_key(company_name: str) -> str:
    safe = re.sub(r'[^a-z0-9]', '_', company_name.lower())
    return f"{safe}_{date.today().isoformat()}"


def _news_cache_load(company_name: str) -> Optional[list[dict]]:
    _NEWS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _NEWS_CACHE_DIR / f"{_cache_key(company_name)}.json"
    if path.exists():
        try:
            data = json.loads(path.read_text())
            logger.warning(f"News: daily cache hit for {company_name!r}")
            return data
        except Exception:
            pass
    return None


def _news_cache_save(company_name: str, articles: list[dict]) -> None:
    _NEWS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _NEWS_CACHE_DIR / f"{_cache_key(company_name)}.json"
    try:
        path.write_text(json.dumps(articles))
    except Exception as e:
        logger.warning(f"News cache write failed: {e}")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _age_days(date_str: str) -> Optional[int]:
    if not date_str:
        return None
    try:
        s = date_str.replace("-", "")[:8]
        dt = datetime.strptime(s, "%Y%m%d").replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).days
    except Exception:
        return None


def _relevance_score(article: dict, company_name: str, domain: str) -> int:
    title = (article.get("title") or "").lower()
    desc  = (article.get("description") or "").lower()
    url   = (article.get("url") or "").lower()
    src   = (article.get("source") or "").lower()
    name  = company_name.lower()
    root  = domain.split(".")[0].lower()
    score = 0

    if name in title:                     score += 40
    elif root in title and len(root) > 3: score += 25
    if name in desc or root in desc:      score += 25
    if domain.lower() in url:             score += 20
    elif root in url and len(root) > 3:   score += 10
    if any(s in src for s in _TRUSTED_SOURCES): score += 10

    age = _age_days(article.get("published_at", ""))
    if age is not None:
        score += 10 if age <= 30 else 5 if age <= 180 else 0

    if not any(c.isascii() and c.isalpha() for c in title):
        score -= 30

    return score


def _deduplicate(articles: list[dict]) -> list[dict]:
    seen, out = set(), []
    for a in articles:
        key = re.sub(r'\W+', '', (a.get("title") or "").lower())[:80]
        if key and key not in seen:
            seen.add(key)
            out.append(a)
    return out


def _classify(article: dict) -> str:
    text = ((article.get("title") or "") + " " + (article.get("description") or "")).lower()
    for cat, kws in _CATEGORIES.items():
        if any(kw in text for kw in kws):
            return cat
    return "general_mention"


# ── NewsAPI ───────────────────────────────────────────────────────────────────

def _fetch_newsapi(company_name: str, domain: str) -> list[dict]:
    if not settings.NEWS_API_KEY:
        return []

    from datetime import timedelta
    from_date = (datetime.now(timezone.utc) - timedelta(days=28)).strftime("%Y-%m-%d")

    params = {
        "q":        (f'"{company_name}" AND '
                     f'(funding OR raised OR acquisition OR layoffs OR '
                     f'partnership OR launch OR expansion OR lawsuit OR breach)'),
        "searchIn": "title,description",
        "language": "en",
        "sortBy":   "relevancy",
        "pageSize": 20,
        "from":     from_date,
        "apiKey":   settings.NEWS_API_KEY,
    }
    try:
        resp = requests.get(_NEWSAPI_URL, params=params, timeout=TIMEOUT)
    except requests.RequestException as e:
        logger.warning(f"NewsAPI request failed: {e}")
        return []

    if resp.status_code != 200:
        logger.warning(f"NewsAPI returned {resp.status_code}: {resp.text[:200]}")
        return []

    return [
        {
            "title":        a.get("title"),
            "source":       (a.get("source") or {}).get("name") or "",
            "published_at": (a.get("publishedAt") or "")[:10],
            "url":          a.get("url"),
            "description":  a.get("description"),
            "news_source":  "NewsAPI",
        }
        for a in resp.json().get("articles", [])
        if a.get("title")
    ]


# ── GDELT ─────────────────────────────────────────────────────────────────────

def _fetch_gdelt(company_name: str, domain: str) -> list[dict]:
    # Single broad query — AI classifies categories post-retrieval
    query = f'"{company_name}" sourcelang:english'
    params = {
        "query":      query,
        "mode":       "artlist",
        "maxrecords": 25,
        "format":     "json",
        "sort":       "DateDesc",
    }

    for attempt in range(5):
        try:
            resp = requests.get(_GDELT_URL, params=params,
                                headers={"User-Agent": _GDELT_UA}, timeout=TIMEOUT)
        except requests.RequestException as e:
            logger.warning(f"GDELT request error: {e}")
            return []

        if resp.status_code == 200:
            break

        if resp.status_code == 429:
            wait = 2 ** attempt   # 1, 2, 4, 8, 16 seconds
            logger.warning(f"GDELT 429 — exponential backoff {wait}s (attempt {attempt+1}/5)")
            time.sleep(wait)
            continue

        logger.warning(f"GDELT returned {resp.status_code}")
        return []
    else:
        logger.warning("GDELT unavailable after 5 attempts — giving up")
        return []

    ct = resp.headers.get("Content-Type", "")
    if "json" not in ct and not resp.text.strip().startswith("{"):
        logger.warning("GDELT returned non-JSON body")
        return []

    try:
        raw = resp.json().get("articles") or []
    except Exception as e:
        logger.warning(f"GDELT JSON parse failed: {e}")
        return []

    return [
        {
            "title":        a.get("title"),
            "source":       a.get("domain"),
            "published_at": (a.get("seendate") or "")[:8],
            "url":          a.get("url"),
            "description":  None,
            "news_source":  "GDELT",
        }
        for a in raw if a.get("title")
    ]


# ── Public entry point ────────────────────────────────────────────────────────

def fetch_news(company_name: str, domain: str) -> Optional[dict]:
    # 1. Check daily news cache first
    cached_articles = _news_cache_load(company_name)
    if cached_articles is not None:
        articles = cached_articles
        source_used = "cache"
    else:
        # 2. NewsAPI primary — cleaner, better entity matching via quoted query
        newsapi_raw = _fetch_newsapi(company_name, domain)

        # 3. GDELT fallback — only if NewsAPI returned fewer than 5 articles
        # Set GDELT_ENABLED=false in .env to disable entirely if rate-limited
        gdelt_raw = []
        gdelt_enabled = (getattr(settings, "GDELT_ENABLED", "true") or "true").lower() != "false"
        if gdelt_enabled and len(newsapi_raw) < 5:
            gdelt_raw = _fetch_gdelt(company_name, domain)
        elif not gdelt_enabled:
            logger.warning("GDELT disabled via GDELT_ENABLED=false")
        else:
            logger.warning(f"News: NewsAPI returned {len(newsapi_raw)} articles — skipping GDELT")

        combined = newsapi_raw + gdelt_raw
        if not combined:
            logger.warning(f"No news articles found for {company_name!r} ({domain})")
            return None

        # 4. Score relevance, filter, deduplicate
        scored = sorted(
            [(a, _relevance_score(a, company_name, domain)) for a in combined],
            key=lambda x: -x[1],
        )
        relevant = [a for a, s in scored if s >= 40]
        if not relevant:
            best = scored[0][1] if scored else 0
            logger.warning(
                f"No articles passed relevance threshold for {company_name!r} "
                f"(best score={best}, total fetched={len(combined)})"
            )
            return None

        articles = _deduplicate(relevant)[:20]
        source_used = "NewsAPI+GDELT" if (newsapi_raw and gdelt_raw) else \
                      "NewsAPI" if newsapi_raw else "GDELT"

        # 5. Cache for today
        _news_cache_save(company_name, articles)

    # Classify categories
    for a in articles:
        a["category"] = _classify(a)

    # AI analysis
    from app.services.news_analysis import analyze_news
    analysis = analyze_news(articles, company_name)

    return {
        "articles": articles,
        "total":    len(articles),
        "source":   source_used,
        "analysis": analysis,
    }
