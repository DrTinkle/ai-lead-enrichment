"""
Tech stack detector — zero API cost.

Reads HTTP response headers and already-scraped HTML to identify
technologies. No third-party API required.

Detection sources:
  - HTTP response headers (Server, X-Powered-By, Set-Cookie hints)
  - <script src="..."> patterns
  - <link rel="..."> patterns
  - Meta generator tags
  - Known JS global variable patterns
  - Inline analytics/pixel snippets
"""
from __future__ import annotations

import logging
import re
from typing import Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from app.utils.cleaners import clean_text

logger = logging.getLogger(__name__)
TIMEOUT = 10
UA = "lead-enrichment-bot/0.1"

# ── Detection rules ───────────────────────────────────────────────────────────
# Each rule: (category, tech_name, pattern_type, pattern)
# pattern_type: "header_server" | "header_powered" | "script_src" |
#               "meta_generator" | "html_contains" | "cookie_name"

RULES: list[tuple[str, str, str, str]] = [
    # ── JS Frameworks ──
    ("JS Framework",   "React",          "script_src",      "react"),
    ("JS Framework",   "Vue.js",         "script_src",      "vue"),
    ("JS Framework",   "Angular",        "script_src",      "angular"),
    ("JS Framework",   "Next.js",        "html_contains",   "_next/static"),
    ("JS Framework",   "Nuxt.js",        "html_contains",   "__nuxt"),
    ("JS Framework",   "Svelte",         "html_contains",   "svelte"),
    ("JS Framework",   "Ember.js",       "script_src",      "ember"),
    ("JS Framework",   "jQuery",         "script_src",      "jquery"),
    ("JS Framework",   "Alpine.js",      "script_src",      "alpine"),
    ("JS Framework",   "HTMX",           "script_src",      "htmx"),
    # ── Web Servers ──
    ("Web Server",     "Nginx",          "header_server",   "nginx"),
    ("Web Server",     "Apache",         "header_server",   "apache"),
    ("Web Server",     "Cloudflare",     "header_server",   "cloudflare"),
    ("Web Server",     "IIS",            "header_server",   "microsoft-iis"),
    ("Web Server",     "Caddy",          "header_server",   "caddy"),
    ("Web Server",     "LiteSpeed",      "header_server",   "litespeed"),
    # ── Hosting / CDN ──
    ("CDN / Hosting",  "Cloudflare",     "html_contains",   "cdn.cloudflare"),
    ("CDN / Hosting",  "AWS CloudFront", "html_contains",   "cloudfront.net"),
    ("CDN / Hosting",  "Fastly",         "html_contains",   "fastly"),
    ("CDN / Hosting",  "Vercel",         "html_contains",   "vercel"),
    ("CDN / Hosting",  "Netlify",        "html_contains",   "netlify"),
    ("CDN / Hosting",  "GitHub Pages",   "html_contains",   "github.io"),
    # ── CMS ──
    ("CMS",            "WordPress",      "meta_generator",  "wordpress"),
    ("CMS",            "WordPress",      "html_contains",   "wp-content"),
    ("CMS",            "Drupal",         "meta_generator",  "drupal"),
    ("CMS",            "Joomla",         "meta_generator",  "joomla"),
    ("CMS",            "Webflow",        "html_contains",   "webflow"),
    ("CMS",            "Squarespace",    "html_contains",   "squarespace"),
    ("CMS",            "Wix",            "html_contains",   "wix.com"),
    ("CMS",            "Ghost",          "html_contains",   "ghost.io"),
    ("CMS",            "HubSpot CMS",    "html_contains",   "hs-scripts.com"),
    ("CMS",            "Contentful",     "html_contains",   "contentful"),
    # ── Analytics ──
    ("Analytics",      "Google Analytics","html_contains",  "google-analytics.com"),
    ("Analytics",      "Google Analytics","html_contains",  "gtag("),
    ("Analytics",      "Segment",        "html_contains",   "analytics.js"),
    ("Analytics",      "Segment",        "html_contains",   "segment.com"),
    ("Analytics",      "Mixpanel",       "html_contains",   "mixpanel"),
    ("Analytics",      "Amplitude",      "html_contains",   "amplitude"),
    ("Analytics",      "Heap",           "html_contains",   "heap"),
    ("Analytics",      "PostHog",        "html_contains",   "posthog"),
    ("Analytics",      "Plausible",      "script_src",      "plausible.io"),
    ("Analytics",      "Datadog RUM",    "html_contains",   "datadog-rum"),
    ("Analytics",      "Hotjar",         "html_contains",   "hotjar"),
    ("Analytics",      "FullStory",      "html_contains",   "fullstory"),
    # ── Payments ──
    ("Payments",       "Stripe",         "html_contains",   "js.stripe.com"),
    ("Payments",       "PayPal",         "html_contains",   "paypal.com/sdk"),
    ("Payments",       "Braintree",      "html_contains",   "braintree"),
    ("Payments",       "Square",         "html_contains",   "squareup.com"),
    ("Payments",       "Paddle",         "html_contains",   "paddle.com"),
    # ── CRM / Marketing ──
    ("CRM / Marketing","HubSpot",        "html_contains",   "hubspot"),
    ("CRM / Marketing","Salesforce",     "html_contains",   "salesforce"),
    ("CRM / Marketing","Intercom",       "html_contains",   "intercom"),
    ("CRM / Marketing","Drift",          "html_contains",   "drift.com"),
    ("CRM / Marketing","Zendesk",        "html_contains",   "zendesk"),
    ("CRM / Marketing","Marketo",        "html_contains",   "marketo"),
    ("CRM / Marketing","Pardot",         "html_contains",   "pardot"),
    ("CRM / Marketing","Klaviyo",        "html_contains",   "klaviyo"),
    ("CRM / Marketing","Customer.io",    "html_contains",   "customer.io"),
    # ── Tag Management ──
    ("Tag Management", "Google Tag Mgr", "html_contains",   "googletagmanager"),
    ("Tag Management", "Segment",        "html_contains",   "cdn.segment"),
    ("Tag Management", "Tealium",        "html_contains",   "tealium"),
    # ── Backend hints ──
    ("Backend",        "PHP",            "header_powered",  "php"),
    ("Backend",        "Python",         "header_powered",  "python"),
    ("Backend",        "Ruby on Rails",  "header_powered",  "rails"),
    ("Backend",        "ASP.NET",        "header_powered",  "asp.net"),
    ("Backend",        "Java",           "header_powered",  "java"),
    ("Backend",        "Node.js",        "header_powered",  "node"),
    # ── eCommerce ──
    ("eCommerce",      "Shopify",        "html_contains",   "myshopify.com"),
    ("eCommerce",      "Shopify",        "html_contains",   "shopify.com/s/"),
    ("eCommerce",      "WooCommerce",    "html_contains",   "woocommerce"),
    ("eCommerce",      "Magento",        "html_contains",   "mage/"),
    ("eCommerce",      "BigCommerce",    "html_contains",   "bigcommerce"),
    # ── Cloud / Infra ──
    ("Cloud / Infra",  "AWS",            "html_contains",   "amazonaws.com"),
    ("Cloud / Infra",  "GCP",            "html_contains",   "googleapis.com"),
    ("Cloud / Infra",  "Azure",          "html_contains",   "azurewebsites"),
    ("Cloud / Infra",  "Vercel",         "html_contains",   "_vercel"),
    ("Cloud / Infra",  "Supabase",       "html_contains",   "supabase"),
    ("Cloud / Infra",  "Firebase",       "html_contains",   "firebase"),
]

_MODERN = {
    "React", "Vue.js", "Angular", "Next.js", "Nuxt.js", "Svelte",
    "Alpine.js", "HTMX", "Segment", "PostHog", "Datadog RUM",
    "Stripe", "AWS", "GCP", "Vercel", "Netlify", "Supabase", "Firebase",
    "Amplitude", "Heap", "FullStory",
}
_LEGACY = {
    "jQuery", "WordPress", "Drupal", "Joomla", "Squarespace", "Wix",
    "PHP", "ASP.NET", "Java", "Ruby on Rails", "Magento", "IIS",
}


def detect_from_html(html: str, headers: dict) -> Optional[dict]:
    """Run detection rules against already-fetched HTML + response headers."""
    if not html:
        return None

    html_lower = html.lower()
    soup = BeautifulSoup(html, "lxml")

    server_hdr   = (headers.get("Server") or "").lower()
    powered_hdr  = (headers.get("X-Powered-By") or "").lower()
    cookie_hdrs  = (headers.get("Set-Cookie") or "").lower()
    meta_gen     = ""
    gen_tag = soup.find("meta", attrs={"name": re.compile("^generator$", re.I)})
    if gen_tag and gen_tag.get("content"):
        meta_gen = gen_tag["content"].lower()

    # collect script src values
    script_srcs = " ".join(
        (s.get("src") or "") for s in soup.find_all("script") if s.get("src")
    ).lower()

    detected: dict[str, str] = {}   # tech_name → category (deduplicate)

    for category, name, ptype, pattern in RULES:
        if name in detected:
            continue
        p = pattern.lower()
        if ptype == "header_server"   and p in server_hdr:   detected[name] = category
        elif ptype == "header_powered" and p in powered_hdr: detected[name] = category
        elif ptype == "script_src"    and p in script_srcs:  detected[name] = category
        elif ptype == "meta_generator" and p in meta_gen:    detected[name] = category
        elif ptype == "html_contains"  and p in html_lower:  detected[name] = category

    if not detected:
        return None

    # group by category
    categories: dict[str, list[str]] = {}
    for name, cat in detected.items():
        categories.setdefault(cat, []).append(name)

    modern_hits = [n for n in detected if n in _MODERN]
    legacy_hits = [n for n in detected if n in _LEGACY]

    if modern_hits and not legacy_hits:
        signal = "modern"
    elif legacy_hits and not modern_hits:
        signal = "legacy"
    elif modern_hits and legacy_hits:
        signal = "mixed"
    else:
        signal = "mixed"

    return {
        "categories":     categories,
        "stack_signal":   signal,
        "modern_techs":   modern_hits,
        "legacy_techs":   legacy_hits,
        "total_detected": len(detected),
        "source":         "html_self_detected",
    }


def fetch_techstack(domain: str, existing_html: Optional[str] = None) -> Optional[dict]:
    """
    Primary entry point.
    If existing_html is provided (from the site scraper), re-use it.
    Otherwise fetch the homepage fresh.
    """
    headers_seen: dict = {}

    if not existing_html:
        try:
            resp = requests.get(
                f"https://{domain}",
                headers={"User-Agent": UA},
                timeout=TIMEOUT,
                allow_redirects=True,
            )
            existing_html = resp.text
            headers_seen  = dict(resp.headers)
        except Exception as e:
            logger.warning(f"TechStack fetch failed for {domain}: {e}")
            return None

    return detect_from_html(existing_html, headers_seen)
