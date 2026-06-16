"""
AI-powered news analysis for acquisition screening.
Uses GPT-4o-mini to classify, score sentiment and business impact per article,
then returns overall news_score, growth_signal and risk_signal.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from openai import OpenAI
from app.config import settings

logger = logging.getLogger(__name__)
client = OpenAI(api_key=settings.OPENAI_API_KEY)


_PROMPT = """\
You are an M&A analyst screening company news for acquisition relevance.
Analyze the articles below and return JSON only.

For each article score:
- sentiment: -1.0 (very negative) to +1.0 (very positive)
- business_impact: -1.0 (very damaging) to +1.0 (very beneficial for acquirer)
- confidence: 0.0 to 1.0 (how certain you are given the title/description)
- signals: list of concrete factual takeaways (max 3, be specific, no hype)
- risk_flags: list of specific risks raised (empty list if none)

Then produce overall scores:
- overall_news_score: 0-10 weighted average of business_impact
- growth_signal: 0-10 (10 = clear strong growth trajectory)
- risk_signal: 0-10 (10 = serious red flags present)
- summary: 2-3 sentence narrative for an acquirer

Return this exact JSON structure:
{
  "articles": [
    {
      "title": "...",
      "category": "...",
      "sentiment": 0.8,
      "business_impact": 0.9,
      "confidence": 0.85,
      "signals": ["..."],
      "risk_flags": []
    }
  ],
  "overall_news_score": 7.8,
  "growth_signal": 8.5,
  "risk_signal": 2.0,
  "summary": "..."
}

Articles to analyze:
"""


def analyze_news(articles: list[dict], company_name: str) -> Optional[dict]:
    if not articles:
        return None

    # Feed top 10 to keep prompt tight
    top = articles[:10]
    article_block = "\n\n".join(
        f"[{i+1}] {a.get('category','').upper()} | {a.get('published_at','')}\n"
        f"Title: {a.get('title','')}\n"
        f"Description: {a.get('description','') or '(no description)'}\n"
        f"Source: {a.get('source','')}"
        for i, a in enumerate(top)
    )

    prompt = _PROMPT + article_block

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.1,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.choices[0].message.content
        result = json.loads(raw)

        # Merge AI article scores back into our article dicts by position
        ai_arts = result.get("articles", [])
        for i, a in enumerate(top):
            if i < len(ai_arts):
                a["sentiment"]       = ai_arts[i].get("sentiment")
                a["business_impact"] = ai_arts[i].get("business_impact")
                a["confidence"]      = ai_arts[i].get("confidence")
                a["signals"]         = ai_arts[i].get("signals", [])
                a["risk_flags"]      = ai_arts[i].get("risk_flags", [])

        return {
            "overall_news_score": result.get("overall_news_score"),
            "growth_signal":      result.get("growth_signal"),
            "risk_signal":        result.get("risk_signal"),
            "summary":            result.get("summary"),
        }

    except Exception as e:
        logger.warning(f"News AI analysis failed: {e}")
        return None
