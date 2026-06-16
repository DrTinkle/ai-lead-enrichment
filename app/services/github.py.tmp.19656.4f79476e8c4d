"""
GitHub signal collector — free GitHub API.

Rate limits:
  - Unauthenticated: 60 req/hour
  - With GITHUB_TOKEN: 5,000 req/hour

Generate a free token at: https://github.com/settings/tokens
No scopes needed — public data only.
Env var: GITHUB_TOKEN (optional but recommended)

Signals collected:
  - Org existence + member count
  - Public repo count
  - Total stars (engineering credibility proxy)
  - Recent commit activity (last 90 days across top repos)
  - Top languages
  - Open source presence
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests

from app.config import settings

logger = logging.getLogger(__name__)
TIMEOUT = 10
_BASE = "https://api.github.com"


def _headers() -> dict:
    h = {
        "Accept":     "application/vnd.github+json",
        "User-Agent": "lead-enrichment-bot/0.1",
    }
    if settings.GITHUB_TOKEN:
        h["Authorization"] = f"Bearer {settings.GITHUB_TOKEN}"
    return h


def _get(path: str, params: dict | None = None) -> Optional[dict | list]:
    try:
        resp = requests.get(
            f"{_BASE}{path}",
            headers=_headers(),
            params=params or {},
            timeout=TIMEOUT,
        )
    except requests.RequestException as e:
        logger.warning(f"GitHub API error: {e}")
        return None

    if resp.status_code == 404:
        return None
    if resp.status_code == 403:
        logger.warning("GitHub rate limit hit — add GITHUB_TOKEN to increase limit")
        return None
    if resp.status_code != 200:
        logger.warning(f"GitHub returned {resp.status_code} for {path}")
        return None

    return resp.json()


def _find_org(company_name: str, domain: str) -> Optional[str]:
    """
    Try to find a GitHub org for the company.
    Strategy: search by company name, then try domain slug.
    """
    # try domain-derived slug first (e.g. stripe.com → stripe)
    slug = domain.split(".")[0].lower()
    org = _get(f"/orgs/{slug}")
    if org:
        return slug

    # search by company name
    results = _get("/search/users", params={
        "q":      f"{company_name} type:org",
        "per_page": 3,
    })
    if not results or not results.get("items"):
        return None

    # return the first org match
    for item in results["items"]:
        if item.get("type") == "Organization":
            return item["login"]

    return None


def _recent_commit_count(org_login: str, repos: list[dict], days: int = 90) -> int:
    """Count commits across top 5 repos in the last N days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    cutoff_str = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")

    total = 0
    for repo in sorted(repos, key=lambda r: r.get("stargazers_count", 0), reverse=True)[:5]:
        commits = _get(
            f"/repos/{org_login}/{repo['name']}/commits",
            params={"since": cutoff_str, "per_page": 100},
        )
        if isinstance(commits, list):
            total += len(commits)

    return total


def fetch_github(company_name: str, domain: str) -> Optional[dict]:
    org_login = _find_org(company_name, domain)
    if not org_login:
        logger.info(f"GitHub: no org found for {company_name} / {domain}")
        return None

    org = _get(f"/orgs/{org_login}")
    if not org:
        return None

    # fetch top repos by stars
    repos = _get(f"/orgs/{org_login}/repos", params={
        "sort": "stars", "per_page": 20, "type": "public",
    })
    repos = repos if isinstance(repos, list) else []

    total_stars = sum(r.get("stargazers_count", 0) for r in repos)
    total_forks = sum(r.get("forks_count", 0) for r in repos)

    # top languages
    lang_counts: dict[str, int] = {}
    for r in repos:
        lang = r.get("language")
        if lang:
            lang_counts[lang] = lang_counts.get(lang, 0) + 1
    top_langs = [l for l, _ in sorted(lang_counts.items(), key=lambda x: -x[1])][:4]

    # recent commits
    recent_commits = _recent_commit_count(org_login, repos)

    member_count = org.get("public_members_url")  # can't get exact count without auth
    public_repos = org.get("public_repos", len(repos))

    # signal classification
    if recent_commits >= 100 and total_stars >= 500:
        eng_signal = "strong"
    elif recent_commits >= 20 or total_stars >= 100:
        eng_signal = "moderate"
    elif public_repos > 0:
        eng_signal = "light"
    else:
        eng_signal = "none"

    logger.info(f"GitHub: {org_login} — {public_repos} repos, {total_stars} stars, {recent_commits} recent commits")

    return {
        "org_login":       org_login,
        "org_name":        org.get("name") or org_login,
        "public_repos":    public_repos,
        "total_stars":     total_stars,
        "total_forks":     total_forks,
        "top_languages":   top_langs,
        "recent_commits":  recent_commits,
        "eng_signal":      eng_signal,
        "github_url":      f"https://github.com/{org_login}",
        "blog":            org.get("blog"),
        "location":        org.get("location"),
    }
