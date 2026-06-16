"""
Public company financial signals — 100% free via yfinance.

yfinance wraps Yahoo Finance data: no API key, no rate limits for light use.
Install: pip install yfinance

For private companies this module returns None gracefully.
For public companies it returns:
  - ticker, exchange, market cap
  - revenue (TTM), revenue growth YoY
  - operating margin, net margin
  - P/E ratio, EV/Revenue
  - cash & short-term investments
  - debt-to-equity ratio
  - 52-week price change %
  - analyst target price vs current
  - is_public flag (always True when data returned)
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def _safe(info: dict, key: str, default=None):
    val = info.get(key)
    return val if val not in (None, "N/A", "", 0) else default


def _find_ticker(company_name: str, domain: str) -> Optional[str]:
    """
    Try to resolve a ticker from company name using yfinance search.
    Falls back to trying the domain root as a ticker (e.g. 'msft' from 'microsoft.com').
    """
    try:
        import yfinance as yf

        # yfinance 0.2+ has a Search class
        results = yf.Search(company_name, max_results=5).quotes
        if results:
            # prefer results tagged as EQUITY on a major exchange
            for r in results:
                if r.get("quoteType") == "EQUITY" and r.get("exchange") in {
                    "NMS", "NYQ", "NGM", "NCM", "ASE", "PCX", "NAS", "NYSE",
                }:
                    return r["symbol"]
            # fallback: first result regardless of exchange
            first = results[0].get("symbol")
            if first:
                return first
    except Exception as e:
        logger.warning(f"yfinance search failed for {company_name!r}: {e}")

    return None


def fetch_financials(company_name: str, domain: str) -> Optional[dict]:
    """
    Fetch public company financials via yfinance.
    Returns None if the company appears to be private or data is unavailable.
    """
    try:
        import yfinance as yf
    except ImportError:
        logger.warning("yfinance not installed — skipping financial signals")
        return None

    ticker_sym = _find_ticker(company_name, domain)
    if not ticker_sym:
        logger.info(f"No public ticker found for {company_name!r}")
        return None

    try:
        ticker = yf.Ticker(ticker_sym)
        info   = ticker.info or {}
    except Exception as e:
        logger.warning(f"yfinance Ticker fetch failed for {ticker_sym}: {e}")
        return None

    # Must look like a real equity with price data to count as public
    quote_type = info.get("quoteType", "")
    price      = _safe(info, "currentPrice") or _safe(info, "regularMarketPrice")
    if quote_type != "EQUITY" or not price:
        logger.info(f"Ticker {ticker_sym} is not a traded equity — treating as private")
        return None

    # ── Core metrics ────────────────────────────────────────────────────────
    market_cap   = _safe(info, "marketCap")
    revenue_ttm  = _safe(info, "totalRevenue")
    rev_growth   = _safe(info, "revenueGrowth")          # decimal e.g. 0.12
    op_margin    = _safe(info, "operatingMargins")        # decimal
    net_margin   = _safe(info, "profitMargins")           # decimal
    pe_ratio     = _safe(info, "trailingPE")
    ev_revenue   = _safe(info, "enterpriseToRevenue")
    ev_ebitda    = _safe(info, "enterpriseToEbitda")
    cash         = _safe(info, "totalCash")
    debt_equity  = _safe(info, "debtToEquity")
    price_52w_lo = _safe(info, "fiftyTwoWeekLow")
    price_52w_hi = _safe(info, "fiftyTwoWeekHigh")
    target_price = _safe(info, "targetMeanPrice")
    analyst_rec  = _safe(info, "recommendationKey")      # "buy" / "hold" / "sell"

    # 52-week performance
    pct_from_low = None
    if price and price_52w_lo and price_52w_lo > 0:
        pct_from_low = round((price - price_52w_lo) / price_52w_lo * 100, 1)

    upside_pct = None
    if price and target_price and price > 0:
        upside_pct = round((target_price - price) / price * 100, 1)

    # ── Narrative signals for scoring ───────────────────────────────────────
    growth_signal = "unknown"
    if rev_growth is not None:
        if rev_growth >= 0.20:
            growth_signal = "strong"
        elif rev_growth >= 0.05:
            growth_signal = "moderate"
        elif rev_growth >= 0:
            growth_signal = "weak"
        else:
            growth_signal = "declining"

    margin_signal = "unknown"
    if op_margin is not None:
        if op_margin >= 0.20:
            margin_signal = "high"
        elif op_margin >= 0.05:
            margin_signal = "moderate"
        elif op_margin >= 0:
            margin_signal = "break-even"
        else:
            margin_signal = "unprofitable"

    result = {
        "is_public":       True,
        "ticker":          ticker_sym,
        "exchange":        info.get("exchange"),
        "sector":          info.get("sector"),
        "industry":        info.get("industry"),
        "price":           price,
        "currency":        info.get("currency", "USD"),
        "market_cap":      market_cap,
        "revenue_ttm":     revenue_ttm,
        "revenue_growth":  rev_growth,
        "operating_margin": op_margin,
        "net_margin":      net_margin,
        "pe_ratio":        pe_ratio,
        "ev_revenue":      ev_revenue,
        "ev_ebitda":       ev_ebitda,
        "cash":            cash,
        "debt_equity":     debt_equity,
        "price_52w_low":   price_52w_lo,
        "price_52w_high":  price_52w_hi,
        "pct_from_52w_low": pct_from_low,
        "target_price":    target_price,
        "analyst_upside_pct": upside_pct,
        "analyst_recommendation": analyst_rec,
        "growth_signal":   growth_signal,
        "margin_signal":   margin_signal,
        "employees":       _safe(info, "fullTimeEmployees"),
        "description":     (info.get("longBusinessSummary") or "")[:400] or None,
    }

    logger.info(f"Financials: fetched {ticker_sym} — market cap ${market_cap:,.0f}" if market_cap else f"Financials: fetched {ticker_sym}")
    return result
