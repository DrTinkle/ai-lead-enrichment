import json
import logging
import re

from app.models.company import Company
from app.models.enrichment_result import EnrichmentResult
from app.services.data_sources import fetch_company_from_abstractapi, fetch_company_site_signal
from app.services.news import fetch_news
from app.services.funding import fetch_funding
from app.services.jobs import fetch_job_postings
from app.services.techstack import fetch_techstack
from app.services.github import fetch_github
from app.services.llm import analyze_company
from app.services.cache import load_from_cache, save_to_cache
from app.utils.cleaners import normalize_domain, normalize_industry

logger = logging.getLogger(__name__)


def _extract_name_from_title(title, domain):
    if not title:
        return None
    name = re.split(r'\s*[|\-]\s*', title)[0].strip()
    name = re.sub(r'[TM(R)(C)]', '', name).strip()
    if len(name) < 2 or name.lower() in {domain.lower(), domain.split('.')[0].lower()}:
        return None
    return name


def build_company_object(domain, api_data, site_signal):
    name = domain
    industry = None
    size_estimate = None
    location = None

    if api_data:
        name          = api_data.get("name") or name
        industry      = normalize_industry(api_data.get("industry"))
        size_estimate = api_data.get("employees_range")
        location      = api_data.get("country")

    raw_summary    = ""
    homepage_html  = ""
    homepage_title = None

    if site_signal:
        chunks = []
        for p in site_signal.get("pages", []):
            chunks.append(
                f"[{p.get('label')}]\nTitle: {p.get('title')}\n"
                f"Description: {p.get('meta_description')}\nText: {p.get('text')}\n"
            )
            if p.get("label") == "homepage":
                homepage_html  = p.get("raw_html", "")
                homepage_title = p.get("title")
        raw_summary = "\n\n".join(chunks).strip()

    if name == domain or not name:
        extracted = _extract_name_from_title(homepage_title, domain)
        if extracted:
            name = extracted
            logger.info(f"Company name from page title: {name!r}")

    return (
        Company(name=name, website=domain, industry=industry,
                size_estimate=size_estimate, location=location,
                raw_summary=raw_summary or "No website data available."),
        homepage_html,
    )


def parse_llm_result(ai_raw):
    cleaned = ai_raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1]
    cleaned = cleaned.strip()
    ai_data    = json.loads(cleaned)
    enrichment = EnrichmentResult(**ai_data)
    return enrichment.model_dump()


def enrich_company(input_value):
    domain = normalize_domain(input_value)
    cached = load_from_cache(domain)
    if cached:
        logger.info(f"Cache hit for {domain}")
        return cached

    logger.info(f"Cache miss for {domain} -- running full pipeline")

    api_data      = fetch_company_from_abstractapi(domain)
    name          = domain
    industry      = None
    size_estimate = None
    location      = None

    if api_data:
        name          = api_data.get("name") or name
        industry      = normalize_industry(api_data.get("industry"))
        size_estimate = api_data.get("employees_range")
        location      = api_data.get("country")

    site_signal    = fetch_company_site_signal(domain)
    raw_summary    = ""
    homepage_html  = ""
    homepage_title = None

    if site_signal:
        chunks = []
        for p in site_signal.get("pages", []):
            chunks.append(
                f"[{p.get('label')}]\nTitle: {p.get('title')}\n"
                f"Description: {p.get('meta_description')}\nText: {p.get('text')}\n"
            )
            if p.get("label") == "homepage":
                homepage_html  = p.get("raw_html", "")
                homepage_title = p.get("title")
        raw_summary = "\n\n".join(chunks).strip()

    if not raw_summary:
        raw_summary = "No website data available."

    if name == domain or not name:
        extracted = _extract_name_from_title(homepage_title, domain)
        if extracted:
            name = extracted

    company = Company(
        name=name, website=domain, industry=industry,
        size_estimate=size_estimate, location=location,
        raw_summary=raw_summary,
    )

    news      = fetch_news(company.name, domain)
    funding   = fetch_funding(company_name=company.name, domain=domain,
                              news_articles=(news or {}).get("articles", []))
    jobs      = fetch_job_postings(company.name, domain)
    techstack = fetch_techstack(domain, existing_html=homepage_html or None)
    github    = fetch_github(company.name, domain)

    ai_raw    = analyze_company(company_data=company.model_dump(),
                                funding=funding, jobs=jobs, news=news,
                                techstack=techstack, github=github)
    analysis  = parse_llm_result(ai_raw)

    result = {"company": company.model_dump(), "analysis": analysis,
              "funding": funding, "jobs": jobs, "news": news,
              "techstack": techstack, "github": github}
    save_to_cache(domain, result)
    return result
