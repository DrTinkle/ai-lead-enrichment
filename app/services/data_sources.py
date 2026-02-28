import re
from typing import Optional
from urllib.parse import urlparse, urljoin

import requests
from bs4 import BeautifulSoup

from app.config import settings

from app.utils.cleaners import clean_text

TIMEOUT = 10
USER_AGENT = "lead-enrichment-bot/0.1"


# normalize input into base domain
def _normalize_domain(input_value: str) -> Optional[str]:
    raw = input_value.strip()

    if not raw:
        return None

    # add https if missing
    if not raw.startswith(("http://", "https://")):
        raw = f"https://{raw}"

    parsed = urlparse(raw)

    if not parsed.netloc:
        return None

    return parsed.netloc


# fetch structured company data from AbstractAPI
def fetch_company_from_abstractapi(domain: str) -> Optional[dict]:
    if not settings.ABSTRACT_API_KEY:
        return None

    url = "https://companyenrichment.abstractapi.com/v1/"

    params = {
        "api_key": settings.ABSTRACT_API_KEY,
        "domain": domain
    }

    try:
        # call enrichment API
        response = requests.get(url, params=params, timeout=TIMEOUT)
    except requests.RequestException:
        return None

    # ignore quota exceeded or invalid key
    if response.status_code != 200:
        return None

    data = response.json()

    # make sure we actually got useful data
    if not data or "name" not in data:
        return None

    return data


# fetch raw HTML
def _fetch_html(url: str) -> Optional[str]:
    headers = {"User-Agent": USER_AGENT}

    try:
        # request page
        response = requests.get(url, headers=headers, timeout=TIMEOUT)
    except requests.RequestException:
        return None

    if response.status_code != 200:
        return None

    # only process html
    content_type = (response.headers.get("Content-Type") or "").lower()
    if "text/html" not in content_type:
        return None

    return response.text


# extract meaningful text from html
def _extract_text(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")

    # remove noisy tags
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    title = soup.title.string.strip() if soup.title and soup.title.string else None

    meta_desc = None
    desc_tag = soup.find("meta", attrs={"name": "description"})
    if desc_tag and desc_tag.get("content"):
        meta_desc = desc_tag["content"].strip()

    # get visible text
    text = soup.get_text(separator=" ")
    text = clean_text(text)

    return {
        "title": title,
        "meta_description": meta_desc,
        "text": text[:6000]  # keep it small for LLM later
    }


# try homepage + common about pages
def fetch_company_site_signal(input_value: str) -> Optional[dict]:
    domain = _normalize_domain(input_value)

    if not domain:
        return None

    base_url = f"https://{domain}"

    pages = []

    # homepage first
    homepage_html = _fetch_html(base_url)
    if homepage_html:
        pages.append(("homepage", homepage_html))

    # try common company pages
    paths = [
        "/about",
        "/about-us",
        "/company",
        "/who-we-are",
        "/careers",
        "/contact",
    ]

    for path in paths:
        url = urljoin(base_url, path)
        html = _fetch_html(url)
        if html:
            pages.append((path.strip("/"), html))

    if not pages:
        return None

    extracted_pages = []

    for label, html in pages[:4]:
        parts = _extract_text(html)

        extracted_pages.append(
            {
                "label": label,
                "title": parts["title"],
                "meta_description": parts["meta_description"],
                "text": parts["text"]
            }
        )

    return {
        "domain": domain,
        "pages": extracted_pages
    }