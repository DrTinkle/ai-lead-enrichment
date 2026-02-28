from openai import OpenAI
from app.config import settings

client = OpenAI(api_key=settings.OPENAI_API_KEY)


def analyze_company(company_data: dict) -> dict:
    prompt = f"""
You are an acquisition analyst.

Analyze the following company data and return JSON only.

Company data:
{company_data}

Return JSON with:
- summary (max 3 sentences)
- sector_classification (single label)
- maturity_stage (Startup / Growth / Mature / Enterprise)
- acquisition_fit_score (0-10 integer)
- risk_flags (max 3 short bullet points)
- reasoning (short explanation for score)

Respond ONLY with valid JSON.
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.2,
        response_format={"type": "json_object"},
        messages=[
            {"role": "user", "content": prompt}
        ],
    )

    return response.choices[0].message.content