def clamp_score(score: int, min_value: int = 0, max_value: int = 10) -> int:
    return max(min_value, min(max_value, score))