from app.utils.helpers import clamp_score

def apply_acquisition_scoring(
    company: dict,
    analysis: dict,
    preferred_sectors=None,
    preferred_regions=None,
    preferred_maturity=None,
    weight_ai=0.6,
    weight_rules=0.4
):
    # fallback safety
    preferred_sectors = preferred_sectors or []
    preferred_regions = preferred_regions or []
    preferred_maturity = preferred_maturity or []

    adjustments = []

    # --- AI score ---
    ai_score = analysis.get("acquisition_fit_score", 0)

    # --- Rule score calculation ---
    rule_score = 0

    sector = analysis.get("sector_classification")
    location = company.get("location")
    maturity = analysis.get("maturity_stage")
    risks = analysis.get("risk_flags", [])

    # sector match
    if sector in preferred_sectors:
        rule_score += 3
        adjustments.append("Sector match +3")
    else:
        adjustments.append("Sector mismatch +0")

    # region match
    if location in preferred_regions:
        rule_score += 2
        adjustments.append("Region match +2")
    else:
        adjustments.append("Region mismatch +0")

    # maturity match
    if maturity in preferred_maturity:
        rule_score += 2
        adjustments.append("Maturity match +2")
    else:
        adjustments.append("Maturity mismatch +0")

    # risk penalty
    risk_penalty = min(len(risks), 3)
    if risk_penalty:
        rule_score -= risk_penalty
        adjustments.append(f"Risk penalty -{risk_penalty}")

    # normalize rule score to 0-10 range
    rule_score = max(0, min(rule_score, 10))

    # --- weighted blend ---
    final_score = round(
        (ai_score * weight_ai) + (rule_score * weight_rules),
        2
    )

    return {
        "ai_score": ai_score,
        "rule_score": rule_score,
        "final_score": final_score,
        "weight_ai": weight_ai,
        "weight_rules": weight_rules,
        "adjustments": adjustments,
    }