from routing.query_complexity import estimate_complexity

# Ordered from lowest to highest complexity threshold.
# Each tier maps a minimum score to the provider name that should handle it.
# To add a new tier/provider later: just insert a new (threshold, provider_name) entry.
ROUTING_TABLE: list[tuple[float, str]] = [
    (0.0, "ollama"),   # default / simple tier
    (0.4, "groq"),     # complex tier
]


def select_provider(prompt: str) -> str:
    score = estimate_complexity(prompt)

    selected = ROUTING_TABLE[0][1] 
    for threshold, provider_name in ROUTING_TABLE:
        if score >= threshold:
            selected = provider_name

    return selected