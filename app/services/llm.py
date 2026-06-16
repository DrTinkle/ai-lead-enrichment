import json
import logging
from typing import Optional
from openai import OpenAI
from app.config import settings

logger = logging.getLogger(__name__)
client = OpenAI(api_key=settings.OPENAI_API_KEY)


def _fmt_funding(funding):
    if not funding:
        return "Not available."
    lines = []
    if funding.get("total_funding_usd"):
        lines.append(f"Total raised: ${funding['total_funding_usd']:,.0f}")
    if funding.get("last_funding_type"):
        lines.append(f"Last round: {funding['last_funding_type']}")
    if funding.get("months_since_raise") is not None:
        lines.append(f"Months since last raise: {funding['months_since_raise']}")
    if funding.get("ipo_status"):
        lines.append(f"IPO status: {funding['ipo_status']}")
    return "\n".join(lines) if lines else "Not available."


def _fmt_jobs(jobs):
    if not jobs:
        return "Not available."
    lines = [f"Active postings: {jobs.get('posting_count', 0)}"]
    if jobs.get("top_functions"):
        lines.append(f"Top hiring areas: {', '.join(jobs['top_functions'])}")
    if jobs.get("top_locations"):
        lines.append(f"Hiring locations: {', '.join(jobs['top_locations'])}")
    return "\n".join(lines)


def _fmt_news(news):
    if not news or not news.get("articles"):
        return "Not available."
    return "\n".join(
        f"- [{a.get('published_at','')}] {a.get('title','')} ({a.get('source','')})"
        for a in news["articles"]
    )


def _fmt_techstack(tech):
    if not tech:
        return "Not available."
    lines = [f"Stack signal: {tech.get('stack_signal','unknown')} ({tech.get('total_detected',0)} technologies)"]
    if tech.get("modern_techs"):
        lines.append(f"Modern: {', '.join(tech['modern_techs'])}")
    if tech.get("legacy_techs"):
        lines.append(f"Legacy: {', '.join(tech['legacy_techs'])}")
    for cat, techs in list(tech.get("categories",{}).items())[:4]:
        lines.append(f"{cat}: {', '.join(techs)}")
    return "\n".join(lines)


def _fmt_github(github):
    if not github:
        return "Not available."
    lines = [
        f"Org: github.com/{github.get('org_login','')}",
        f"Public repos: {github.get('public_repos',0)}",
        f"Total stars: {github.get('total_stars',0)}",
        f"Recent commits (90d): {github.get('recent_commits',0)}",
        f"Engineering signal: {github.get('eng_signal','unknown')}",
    ]
    if github.get("top_languages"):
        lines.append(f"Top languages: {', '.join(github['top_languages'])}")
    return "\n".join(lines)


def _fmt_financials(fin):
    if not fin or not fin.get("is_public"):
        return "Private company -- no public financial data."
    lines = [
        f"Ticker: {fin.get('ticker')} ({fin.get('exchange')}) | Currency: {fin.get('currency','USD')}",
    ]
    if fin.get("market_cap"):
        lines.append(f"Market Cap: ${fin['market_cap']:,.0f}")
    if fin.get("revenue_ttm"):
        lines.append(f"Revenue (TTM): ${fin['revenue_ttm']:,.0f}")
    if fin.get("revenue_growth") is not None:
        lines.append(f"Revenue Growth YoY: {fin['revenue_growth']*100:.1f}%")
    if fin.get("operating_margin") is not None:
        lines.append(f"Operating Margin: {fin['operating_margin']*100:.1f}%")
    if fin.get("net_margin") is not None:
        lines.append(f"Net Margin: {fin['net_margin']*100:.1f}%")
    if fin.get("pe_ratio"):
        lines.append(f"P/E Ratio: {fin['pe_ratio']:.1f}x")
    if fin.get("ev_revenue"):
        lines.append(f"EV/Revenue: {fin['ev_revenue']:.1f}x")
    if fin.get("cash"):
        lines.append(f"Cash: ${fin['cash']:,.0f}")
    if fin.get("analyst_recommendation"):
        lines.append(f"Analyst Rating: {fin['analyst_recommendation'].upper()}")
    if fin.get("analyst_upside_pct") is not None:
        lines.append(f"Analyst Upside: {fin['analyst_upside_pct']:+.1f}%")
    return "\n".join(lines)


def analyze_company(company_data, funding=None, jobs=None, news=None,
                    techstack=None, github=None, financials=None):
    prompt = f"""You are a senior M&A analyst at a technology-focused investment firm.
Analyze the following company using all available signals and return JSON only.

=== COMPANY PROFILE ===
{json.dumps(company_data, indent=2)}

=== PUBLIC MARKET FINANCIALS ===
{_fmt_financials(financials)}

=== PRIVATE FUNDING & RAISES ===
{_fmt_funding(funding)}

=== HIRING SIGNALS ===
{_fmt_jobs(jobs)}

=== RECENT NEWS ===
{_fmt_news(news)}

=== TECH STACK ===
{_fmt_techstack(techstack)}

=== GITHUB / ENGINEERING ===
{_fmt_github(github)}

=== INSTRUCTIONS ===
Write a detailed acquisition intelligence report. Use ALL available signals.
Be specific -- cite actual data points. Never write generic filler.

Return a single JSON object with these exact keys:

- summary: 4-5 sentence executive summary. Mention sector, stage, key strengths, red flags.
- sector_classification: single sector label
- maturity_stage: one of Pre-Seed / Seed / Startup / Early Growth / Growth / Scale-Up / Mature / Public
- acquisition_fit_score: integer 0-10
- growth_signal: one of "strong" / "moderate" / "weak" / "declining"
- tech_assessment: one of "modern" / "mixed" / "legacy" / "unknown"
- risk_flags: list of up to 5 specific risks, each citing a data source.
- positive_signals: list of up to 5 specific positives, each citing evidence.
- funding_outlook: 2-3 sentence paragraph on funding situation.
- hiring_health: 2-3 sentence paragraph on hiring signals.
- tech_maturity: 2-3 sentence paragraph on tech stack and engineering depth.
- market_position: 2-3 sentence paragraph on market position.
- reasoning: 2-3 sentence explanation of the acquisition_fit_score.

Respond ONLY with valid JSON.
"""
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.2,
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content
