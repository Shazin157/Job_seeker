"""
Fully free skill extraction: matches text against a static, editable taxonomy
(data/skills_taxonomy.json) instead of calling any paid API.

Trade-off, stated plainly: this only detects skills phrased the way you defined
them in the taxonomy. It will miss novel wording it hasn't seen before, unlike an
LLM call. Fix by adding new synonyms to skills_taxonomy.json as you notice misses --
it's meant to be edited over time, not written once.
"""
import json
import os
import re

TAXONOMY_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "skills_taxonomy.json")


def load_taxonomy() -> dict:
    with open(os.path.abspath(TAXONOMY_PATH), "r", encoding="utf-8") as f:
        return json.load(f)


def extract_skills_from_text(text: str, taxonomy: dict = None) -> list:
    """Returns a list of canonical skill names found in the given text."""
    if taxonomy is None:
        taxonomy = load_taxonomy()

    text_lower = text.lower()
    found = []
    for canonical, synonyms in taxonomy.items():
        for synonym in synonyms:
            pattern = r"(?<![a-z0-9])" + re.escape(synonym.lower()) + r"(?![a-z0-9])"
            if re.search(pattern, text_lower):
                found.append(canonical)
                break
    return found
