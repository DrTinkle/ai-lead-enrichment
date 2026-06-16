"""
Job postings collector — hiring signal pipeline.

Priority order:
  1. Known ATS API         (Lever, Greenhouse) — structured, highest confidence
  2. Company listing page  — direct scrape of /jobs/search etc.
  3. Landing page crawl    — follow links from /jobs or /careers
  4. Embedded JSON         — __NEXT_DATA__, script tags
  5. Adzuna (last resort)  — filtered by strict entity match only
"""
from __future__ import annotations

import json
import logging
import re
from collections import Counter
from difflib import SequenceMatcher
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from app.config import settings

logger  = logging.getLogger(__name__)
TIMEOUT = 12
UA      = "Mozilla/5.0 (compatible; lead-enrichment-bot/0.1)"
HEADERS = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}

# ── URL candidates ─────────────────────────────────────────────────────────────

CANDIDATE_PATHS = [
    "/jobs/search",
    "/careers/search",
    "/careers/open-roles",
    "/jobs/open-roles",
    "/jobs/positions",
    "/careers/positions",
    "/jobs",
    "/careers",
    "/join-us",
    "/company/careers",
    "/about/careers",
    "/work-with-us",
    "/openings",
    "/positions",
]

# ── Page-type classifier ───────────────────────────────────────────────────────

LISTING_KEYWORDS = [
    "open roles", "search jobs", "apply", "department", "location",
    "engineering", "sales", "product", "remote", "full-time", "part-time",
    "job opening", "job listing", "view all jobs", "all open positions",
    "filter", "sort by",
]

LANDING_KEYWORDS = [
    "life at", "benefits", "culture", "values", "join us", "our teams",
    "why work", "perks", "mission", "what we offer",
]

JOB_LINK_HINTS = [
    "search", "openings", "open-roles", "positions", "listings",
    ".jobs/", "jobs.", "/jobs",
    "boards.greenhouse.io", "jobs.lever.co", "workdayjobs.com",
    "ashbyhq.com", "smartrecruiters.com", "jobvite.com",
]


def _classify_page(html: str) -> str:
    text = html.lower()
    listing_score = sum(1 for kw in LISTING_KEYWORDS if kw in text)
    landing_score  = sum(1 for kw in LANDING_KEYWORDS  if kw in text)
    if listing_score >= 3:
        return "job_listing_page"
    if landing_score >= 2:
        return "careers_landing_page"
    return "unknown"


# ── ATS detection ──────────────────────────────────────────────────────────────

ATS_PATTERNS = {
    "greenhouse":     ["boards.greenhouse.io", "greenhouse.io/embed"],
    "lever":          ["jobs.lever.co", "api.lever.co"],
    "workday":        ["workdayjobs.com", "myworkdayjobs.com"],
    "ashby":          ["jobs.ashbyhq.com", "ashbyhq.com"],
    "smartrecruiters":["smartrecruiters.com"],
    "jobvite":        ["jobvite.com"],
    "rippling":       ["rippling.com"],
    "bamboohr":       ["bamboohr.com"],
}


def _detect_ats(html: str, links: list[str]) -> Optional[str]:
    combined = html.lower() + " " + " ".join(links).lower()
    for ats_name, patterns in ATS_PATTERNS.items():
        if any(p in combined for p in patterns):
            return ats_name
    return None


def _extract_ats_slug(html: str, links: list[str], ats: str) -> Optional[str]:
    """Extract company slug from ATS URLs found in page."""
    patterns = ATS_PATTERNS.get(ats, [])
    for link in links:
        for p in patterns:
            if p in link.lower():
                # e.g. https://boards.greenhouse.io/stripe -> "stripe"
                # e.g. https://jobs.lever.co/stripe -> "stripe"
                path = urlparse(link).path.strip("/").split("/")[0]
                if path:
                    return path
    return None


# ── ATS APIs ───────────────────────────────────────────────────────────────────

def _fetch_greenhouse(slug: str) -> Optional[list[dict]]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code != 200:
            return None
        data = r.json()
        jobs = data.get("jobs", [])
        return [
            {
                "title":    j.get("title", ""),
                "location": (j.get("location") or {}).get("name", ""),
                "url":      j.get("absolute_url", ""),
                "source":   "greenhouse_api",
            }
            for j in jobs
        ]
    except Exception as e:
        logger.warning(f"Greenhouse API failed for {slug!r}: {e}")
        return None


def _fetch_lever(slug: str) -> Optional[list[dict]]:
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code != 200:
            return None
        jobs = r.json()
        if not isinstance(jobs, list):
            return None
        return [
            {
                "title":    j.get("text", ""),
                "location": (j.get("categories") or {}).get("location", ""),
                "url":      j.get("hostedUrl", ""),
                "source":   "lever_api",
            }
            for j in jobs
        ]
    except Exception as e:
        logger.warning(f"Lever API failed for {slug!r}: {e}")
        return None


# ── Embedded JSON extraction ───────────────────────────────────────────────────

def _extract_embedded_jobs(html: str) -> list[dict]:
    """Try to pull job listings from __NEXT_DATA__ or other script-embedded JSON."""
    jobs = []
    soup = BeautifulSoup(html, "lxml")

    # __NEXT_DATA__ (Next.js)
    next_tag = soup.find("script", id="__NEXT_DATA__")
    if next_tag:
        try:
            data = json.loads(next_tag.string or "")
            raw = json.dumps(data)
            # Look for arrays that look like job listings
            titles = re.findall(r'"title"\s*:\s*"([^"]{5,80})"', raw)
            urls   = re.findall(r'"(?:url|absoluteUrl|applyUrl|hostedUrl)"\s*:\s*"(https?://[^"]+)"', raw)
            locs   = re.findall(r'"(?:location|city|office)"\s*:\s*"([^"]{2,60})"', raw)
            for i, title in enumerate(titles[:50]):
                jobs.append({
                    "title":    title,
                    "location": locs[i] if i < len(locs) else "",
                    "url":      urls[i] if i < len(urls) else "",
                    "source":   "embedded_json",
                })
        except Exception:
            pass

    # Generic application/ld+json
    if not jobs:
        for tag in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(tag.string or "")
                if isinstance(data, list):
                    data = data[0]
                if data.get("@type") in ("JobPosting", "ItemList"):
                    items = data.get("itemListElement", [data])
                    for item in items[:50]:
                        j = item.get("item", item)
                        jobs.append({
                            "title":    j.get("title", j.get("name", "")),
                            "location": str((j.get("jobLocation") or {}).get("address", "")),
                            "url":      j.get("url", ""),
                            "source":   "jsonld",
                        })
            except Exception:
                pass

    return [j for j in jobs if j.get("title")]


# ── Generic page scraper ───────────────────────────────────────────────────────

TITLE_KW = re.compile(
    r"\b(engineer|developer|manager|analyst|designer|director|lead|"
    r"scientist|product|sales|support|growth|operations|recruiter|"
    r"architect|devops|counsel|finance|marketing|data|security|"
    r"counsel|legal|researcher|strategist)\b",
    re.IGNORECASE,
)

MANUAL_LABOR_FLAGS = [
    "asphalt", "highway", "cdl", "forklift", "welding", "laborer",
    "pavement", "sealcoat", "paving", "road crew", "striping crew",
    "line marking", "concrete", "excavat",
]

JOB_SELECTORS = [
    "[class*='job-listing']", "[class*='job-card']", "[class*='position']",
    "[class*='opening']",     "[class*='role']",     "[class*='vacancy']",
    "li[class*='job']",       "article[class*='job']","[data-job]",
    "tr[class*='job']",
]


def _scrape_listing_page(html: str, base_url: str) -> list[dict]:
    """Extract job entries from a confirmed listing page."""
    soup = BeautifulSoup(html, "lxml")
    jobs = []

    # Try structured selectors first
    for selector in JOB_SELECTORS:
        try:
            items = soup.select(selector)
            if len(items) >= 3:
                for el in items[:60]:
                    link = el.find("a")
                    title = (link or el).get_text(" ", strip=True)[:100]
                    url   = urljoin(base_url, link["href"]) if link and link.get("href") else ""
                    loc_el = el.find(class_=re.compile(r"location|city|office", re.I))
                    loc    = loc_el.get_text(strip=True)[:60] if loc_el else ""
                    if title and len(title.split()) >= 2 and TITLE_KW.search(title):
                        jobs.append({"title": title, "location": loc, "url": url, "source": "careers_page"})
                if jobs:
                    return jobs
        except Exception:
            continue

    # Fallback: scan headings + li + anchor text
    # Require at least 2 words to exclude single nav items like "Product" or "Sales"
    seen: set = set()
    for el in soup.find_all(["h2", "h3", "h4", "li", "a"], limit=300):
        text = el.get_text(" ", strip=True)
        words = text.split()
        if len(words) < 2:
            continue
        if 8 < len(text) < 100 and TITLE_KW.search(text):
            norm = text.lower()
            if norm not in seen:
                seen.add(norm)
                href = el.get("href", "") if el.name == "a" else ""
                jobs.append({
                    "title":    text,
                    "location": "",
                    "url":      urljoin(base_url, href) if href else "",
                    "source":   "careers_page",
                })
        if len(jobs) >= 30:
            break

    return jobs


def _count_from_page(html: str) -> int:
    """Heuristic job count from static HTML."""
    soup = BeautifulSoup(html, "lxml")
    for selector in JOB_SELECTORS:
        try:
            items = soup.select(selector)
            if len(items) > 0:
                return len(items)
        except Exception:
            continue
    # Keyword heuristic fallback
    kw = re.compile(
        r"\b(engineer|developer|manager|analyst|designer|scientist|"
        r"director|lead|specialist|coordinator|recruiter|product|sales)\b",
        re.IGNORECASE,
    )
    candidates = soup.find_all(["li", "tr", "div", "article"])
    return min(sum(1 for el in candidates if kw.search(el.get_text(" ", strip=True)[:80])), 200)


# ── Main careers page pipeline ─────────────────────────────────────────────────

def _fetch_page(url: str) -> Optional[requests.Response]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        if r.status_code == 200 and "text/html" in r.headers.get("Content-Type", ""):
            return r
    except requests.RequestException:
        pass
    return None


def _scrape_company_careers(domain: str) -> Optional[dict]:
    """
    Full pipeline:
      1. Try each candidate path
      2. Classify page type
      3. If landing page, crawl links for a listing page
      4. Detect ATS → call ATS API
      5. Try embedded JSON
      6. Fall back to HTML scraping
    """
    base = f"https://{domain}"
    found_pages: list[tuple[str, str, str]] = []  # (final_url, html, page_type)

    # Build URL candidates: subdomains first, then path-based
    stem = domain.split(".")[0]  # "wolt" from "wolt.com"
    tld  = ".".join(domain.split(".")[1:])  # "com" from "wolt.com"
    subdomain_candidates = [
        f"https://careers.{domain}",
        f"https://careers.{domain}/en/jobs",
        f"https://jobs.{domain}",
        f"https://{stem}.jobs",
        f"https://{stem}.jobs/en/jobs",
    ]
    path_candidates = [urljoin(base, path) for path in CANDIDATE_PATHS]
    all_candidates  = subdomain_candidates + path_candidates

    # Step 1 + 2: fetch candidates, classify; use resp.url (post-redirect)
    for url in all_candidates:
        resp = _fetch_page(url)
        if not resp:
            continue
        final_url = resp.url  # capture actual URL after any redirect
        html      = resp.text
        page_type = _classify_page(html)
        found_pages.append((final_url, html, page_type))
        if page_type == "job_listing_page":
            break  # found it

    if not found_pages:
        return None

    # Step 3: if only landing pages found, crawl their links
    listing_pages = [(u, h, t) for u, h, t in found_pages if t == "job_listing_page"]
    landing_pages = [(u, h, t) for u, h, t in found_pages if t == "careers_landing_page"]

    if not listing_pages and landing_pages:
        land_url, land_html, _ = landing_pages[0]
        soup = BeautifulSoup(land_html, "lxml")
        company_stem = domain.split(".")[0].lower()  # "dropbox" from "dropbox.com"
        for a in soup.find_all("a", href=True):
            raw_href = a["href"]
            href_lower = raw_href.lower()
            if not any(hint in href_lower for hint in JOB_LINK_HINTS):
                continue
            full = urljoin(land_url, raw_href)
            parsed = urlparse(full)
            # Allow same domain OR external job domains (e.g. dropbox.jobs, jobs.dropbox.com)
            same_domain    = parsed.netloc == domain
            ext_job_domain = (
                parsed.netloc.endswith(".jobs") or
                parsed.netloc.startswith("jobs.") or
                company_stem in parsed.netloc
            )
            if same_domain or ext_job_domain:
                resp = _fetch_page(full)
                if resp and _classify_page(resp.text) == "job_listing_page":
                    listing_pages.append((resp.url, resp.text, "job_listing_page"))
                    logger.warning(f"Jobs: followed link to listing page {resp.url}")
                    break
