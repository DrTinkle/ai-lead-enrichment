"""
Funding signal collector — 100% free, no API keys required.

Sources:
  1. SEC EDGAR full-text search for Form D filings (US private companies).
     Form D is legally required for any US securities offering — gives
     round size, date, and issuer name for the vast majority of funded startups.
     API: https://efts.sec.gov/LATEST/search-index (public, no key)

  2. News-based funding keyword extraction from article headlines
     (passed in from news.py results). Extracts round type and approximate
     amount from mentions like "raises $40M Series B".
"""
from __future__ import annotations

import logging
import re
from typing import Optional
from datetime import datetime

import requests

logger = logging.getLogger(__name__)
TIMEOUT = 10
UA = "lead-enrichment-bot/0.1 (research tool)"

# SEC EDGAR full-text search endpoint (public API, no key needed)
_EDGAR_SEARCH  = "https://efts.sec.gov/LATEST/search-index"
_EDGAR_SEARCH2 = "https://efts.sec.gov/LATEST/search-index?q={q}&forms=D&dateRange=custom&startdt=2015-01-01"
_EDGAR_FULLTEXT = "https://efts.sec.gov/LATEST/search-index"

# Regex to extract funding amounts from news text
_AMOUNT_RE = re.compile(
    r"\$\s*(\d+(?:\.\d+)?)\s*(million|billion|M|B)\b",
    re.IGNORECASE,
)
_ROUND_RE = re.compile(
    r"\b(pre[\-\s]?seed|seed|series\s+[a-e]|growth[\s]?equity|venture|ipo|spac)\b",
    re.IGNORECASE,
)
_FUNDING_KEYWORDS = [
    "raises", "raised", "funding", "investment", "series a", "series b",
    "series c", "series d", "seed round", "valuation", "venture", "backed",
    "capital", "growth round", "ipo", "acquired", "acquisition",
]


# ── SEC EDGAR ─────────────────────────────────────────────────────────────────

def _search_edgar_form_d(company_name: str) -> Optional[dict]:
    """
    Search EDGAR full-text search for Form D filings.
    Tries two endpoint styles — EDGAR's search API is occasionally flaky.
    """
    headers = {"User-Agent": UA}

    # Try 1: standard search-index with JSON params
    params = {
        "q":        f'"{company_name}"',
        "forms":    "D",
        "dateRange": "custom",
        "startdt":  "2015-01-01",
    }
    resp = None
    for attempt in range(2):
        try:
            resp = requests.get(_EDGAR_SEARCH, params=params, headers=headers, timeout=TIMEOUT)
            if resp.status_code == 200:
                break
            logger.warning(f"EDGAR attempt {attempt+1} returned {resp.status_code}")
            if attempt == 0:
                import time; time.sleep(2)
        except requests.RequestException as e:
            logger.warning(f"EDGAR request failed: {e}")
            return None

    if resp is None or resp.status_code != 200:
        logger.warning("EDGAR unavailable — skipping funding signal")
        return None

    data = resp.json()
    hits = data.get("hits", {}).get("hits", [])
    if not hits:
        return None

    # most recent filing first (EDGAR returns newest first by default)
    filing = hits[0].get("_source", {})
    filed_at = filing.get("file_date", "")
    entity   = filing.get("entity_name", "")

    months_ago = None
    if filed_at:
        try:
            d = datetime.strptime(filed_at[:10], "%Y-%m-%d")
            months_ago = (datetime.utcnow() - d).days // 30
        except ValueError:
            pass

    return {
        "source":       "SEC EDGAR Form D",
        "entity_name":  entity,
        "filed_at":     filed_at[:10] if filed_at else None,
        "months_since_raise": months_ago,
        "filing_url":   f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company="
                        f"{requests.utils.quote(company_name)}&type=D&dateb=&owner=include&count=10",
    }


# ── News keyword extraction ───────────────────────────────────────────────────

def _extract_from_news(articles: list[dict]) -> Optional[dict]:
    """
    Scan news headlines/descriptions for funding signals.
    Returns extracted round info or None if nothing found.
    """
    for article in articles:
        text = " ".join([
            article.get("title") or "",
            article.get("description") or "",
        ])
        text_lower = text.lower()

        if not any(kw in text_lower for kw in _FUNDING_KEYWORDS):
            continue

        # try to extract amount
        amount_usd = None
        m = _AMOUNT_RE.search(text)
        if m:
            val  = float(m.group(1))
            unit = m.group(2).lower()
            amount_usd = int(val * (1_000_000_000 if unit in ("billion", "b") else 1_000_000))

        # try to extract round type
        round_type = None
        r = _ROUND_RE.search(text)
        if r:
            round_type = r.group(0).title()

        if amount_usd or round_type:
            pub = article.get("published_at", "")
            months_ago = None
            if pub:
                try:
                    d = datetime.strptime(pub[:10], "%Y-%m-%d")
                    months_ago = (datetime.utcnow() - d).days // 30
                except ValueError:
                    pass

            return {
                "source":             "news_extraction",
                "total_funding_usd":  amount_usd,
                "last_funding_type":  round_type,
                "months_since_raise": months_ago,
                "headline":           article.get("title"),
            }

    return None


# ── Public entry point ────────────────────────────────────────────────────────

def fetch_funding(company_name: str, domain: str, news_articles: Optional[list] = None) -> Optional[dict]:
    """
    Try SEC EDGAR first, then fall back to news-based extraction.
    Both sources are free and require no API key.
    """
    result: dict = {}

    # 1. EDGAR (best for US companies)
    edgar = _search_edgar_form_d(company_name)
    if edgar:
        result.update(edgar)
        logger.info(f"Funding: EDGAR Form D found for {company_name}")

    # 2. News extraction (supplements or replaces EDGAR)
    if news_articles:
        news_funding = _extract_from_news(news_articles)
        if news_funding:
            # prefer news amount/round if EDGAR didn't supply them
            if not result.get("total_funding_usd") and news_funding.get("total_funding_usd"):
                result["total_funding_usd"] = news_funding["total_funding_usd"]
            if not result.get("last_funding_type") and news_funding.get("last_funding_type"):
                result["last_funding_type"] = news_funding["last_funding_type"]
            if not result.get("months_since_raise") and news_funding.get("months_since_raise"):
                result["months_since_raise"] = news_funding["months_since_raise"]
            result["news_headline"] = news_funding.get("headline")
            logger.info(f"Funding: news extraction supplement for {company_name}")

    return result if result else None
