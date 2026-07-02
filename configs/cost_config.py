# Rough Groq pricing reference — update to match your actual model's published rate
COST_PER_MILLION_INPUT_TOKENS = 0.05
COST_PER_MILLION_OUTPUT_TOKENS = 0.08


def estimate_cost(prompt_tokens: int, completion_tokens: int) -> float:
    return (
        (prompt_tokens / 1_000_000) * COST_PER_MILLION_INPUT_TOKENS
        + (completion_tokens / 1_000_000) * COST_PER_MILLION_OUTPUT_TOKENS
    )