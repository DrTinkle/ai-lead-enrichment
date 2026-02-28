import re


def normalize_domain(domain: str) -> str:
    # lowercase and remove trailing slash
    return domain.lower().strip("/")


def normalize_industry(industry: str | None) -> str | None:
    if not industry:
        return None

    industry = industry.lower()

    # simple mapping
    if "internet" in industry:
        return "Internet / Technology"
    if "financial" in industry or "fintech" in industry:
        return "FinTech"

    return industry.title()


def clean_text(text: str) -> str:
    # collapse whitespace
    text = re.sub(r"\s+", " ", text)
    return text.strip()