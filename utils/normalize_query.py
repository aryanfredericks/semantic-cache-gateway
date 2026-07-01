import re


def normalize_prompt(text: str) -> str:
    # Collapse all whitespace (spaces, tabs, newlines) into single spaces
    text = re.sub(r"\s+", " ", text)
    # Strip leading/trailing whitespace
    text = text.strip()
    return text