import json
import logging

from app.models.company import Company
from app.models.enrichment_result import EnrichmentResult
from app.services.data_sources import (
    fetch_company_from_abstractapi,
    fetch_company_site_signal,
)
from app.services.llm import analyze_company
from app.services.cache import load_from_cache, save_to_cache
from app.utils.cleaners import normalize_domain, normalize_industry

logger = logging.getLogger(__name__)


def enrich_company(input_value: str):
    # normalize input into clean domain
    domain = normalize_domain(input_value)

    # check cache first to avoid API + LLM calls
    cached = load_from_cache(domain)
    if cached:
        logger.info(f"Cache hit for {domain}")
        return cached

    logger.info(f"Cache miss for {domain}, fetching fresh data")

    # try structured enrichment first (free tier)
    api_data = fetch_company_from_abstractapi(domain)

    # always scrape website for raw signal
    site_signal = fetch_company_site_signal(domain)

    name = domain
    industry = None
    size_estimate = None
    location = None

    if api_data:
        # map structured fields if available
        name = api_data.get("name") or name
        industry = api_data.get("industry")
        industry = normalize_industry(industry)
        size_estimate = api_data.get("employees_range")
        location = api_data.get("country")

    raw_summary = ""

    if site_signal:
        pages = site_signal.get("pages", [])
        chunks = []

        # build compact signal payload for LLM
        for p in pages:
            chunks.append(
                f"[{p.get('label')}]\n"
                f"Title: {p.get('title')}\n"
                f"Description: {p.get('meta_description')}\n"
                f"Text: {p.get('text')}\n"
            )

        raw_summary = "\n\n".join(chunks).strip()

    if not raw_summary:
        raw_summary = "No website data available."

    # build company object
    company = Company(
        name=name,
        website=domain,
        industry=industry,
        size_estimate=size_estimate,
        location=location,
        raw_summary=raw_summary,
    )

    analysis = None

    # send structured data to LLM for analysis
    try:
        ai_raw = analyze_company(company.model_dump())

        # remove markdown code fences if present
        cleaned = ai_raw.strip()

        if cleaned.startswith("```"):
            cleaned = cleaned.split("```")[1]

        cleaned = cleaned.strip()

        ai_data = json.loads(cleaned)
        enrichment = EnrichmentResult(**ai_data)
        analysis = enrichment.model_dump()

    except Exception as e:
        logger.error(f"LLM parsing failed for {domain}: {e}")

    result = {
        "company": company.model_dump(),
        "analysis": analysis,
    }

    # only cache successful analysis results
    if analysis:
        save_to_cache(domain, result)
        logger.info(f"Saved result to cache for {domain}")

    return result