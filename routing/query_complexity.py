import re

CODE_KEYWORDS = {"code", "function", "debug", "algorithm", "script", "implement", "refactor", "class", "api"}
REASONING_KEYWORDS = {"explain", "analyze", "compare", "why", "evaluate", "pros and cons", "trade-off", "design", "architecture"}
MULTI_PART_MARKERS = re.compile(r"\band\b|\balso\b|\bthen\b|;|\n\d+\.|\n-")


def estimate_complexity(prompt: str) -> float:
    words = prompt.lower().split()
    word_count = len(words)

    score = 0.0
    score += min(word_count / 100, 1.0) * 0.3
    if any(kw in prompt.lower() for kw in CODE_KEYWORDS):
        score += 0.35
    if any(kw in prompt.lower() for kw in REASONING_KEYWORDS):
        score += 0.35
    if MULTI_PART_MARKERS.search(prompt):
        score += 0.2

    return min(score, 1.0)