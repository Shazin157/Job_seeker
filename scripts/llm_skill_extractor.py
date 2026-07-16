"""
Free LLM skill extraction via Groq (OpenAI-compatible API, no cost at this volume).

Real risk this is designed around: free-tier model catalogs get deprecated or
rate-limited without warning. Every function here is wrapped so a failure
(timeout, 429, deleted model, malformed JSON) raises a clear exception rather
than failing silently -- callers (extract_resume_skills.py, score_jobs.py) catch
that and fall back to the free taxonomy matcher in skill_matcher.py, so a Groq
outage degrades match quality instead of breaking the pipeline.
"""
import json
import os
import time
import requests

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
# If this model gets deprecated, update it here -- check console.groq.com/docs/models
GROQ_MODEL = "llama-3.3-70b-versatile"

RESUME_PROMPT = """Extract a structured skill inventory from this resume for automated
job-matching. Return ONLY a JSON object, no markdown fences, no preamble:

{{"all_skills_flat": ["..."]}}

Include languages, frameworks, model architectures, tools, and domain concepts
(e.g. "Computer Vision", "Anomaly Detection"). Deduplicate. Do not invent skills
not present or clearly implied. Use consistent casing (e.g. "PyTorch").

Resume text:
---
{resume_text}
---
"""

JOB_PROMPT = """Extract the technical skills required for this job posting.
Return ONLY a JSON object, no markdown fences, no preamble:

{{"required_skills": ["..."]}}

Include tools, languages, frameworks, model types, and domain concepts. Keep
each entry short (1-3 words). Do not invent skills not mentioned or clearly
implied.

Job posting:
---
{job_text}
---
"""


def _call_groq(prompt: str, max_tokens: int = 512) -> str:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY not set")

    for attempt in range(2):
        resp = requests.post(
            GROQ_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": GROQ_MODEL,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=30,
        )
        if resp.status_code == 429 and attempt == 0:
            # Free-tier RPM cap hit -- back off once using the server's own
            # Retry-After hint (falls back to 5s if it doesn't provide one),
            # then try exactly one more time before letting the caller fall
            # back to the taxonomy matcher.
            wait_s = int(resp.headers.get("Retry-After", 5))
            time.sleep(min(wait_s, 15))
            continue
        resp.raise_for_status()
        data = resp.json()
        text = data["choices"][0]["message"]["content"]
        return text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    resp.raise_for_status()  # surfaces the 429 as an exception if both attempts failed
    raise RuntimeError("Groq call failed after retry")


def extract_resume_skills_llm(resume_text: str) -> list:
    """Returns a flat list of skills. Raises on any failure -- caller must catch."""
    text = _call_groq(RESUME_PROMPT.format(resume_text=resume_text[:8000]))
    parsed = json.loads(text)
    skills = parsed.get("all_skills_flat", [])
    if not isinstance(skills, list):
        raise ValueError("Groq response did not contain a valid skill list")
    return skills


def extract_job_skills_llm(job_text: str) -> list:
    """Returns a flat list of required skills. Raises on any failure -- caller must catch."""
    text = _call_groq(JOB_PROMPT.format(job_text=job_text[:6000]))
    parsed = json.loads(text)
    skills = parsed.get("required_skills", [])
    if not isinstance(skills, list):
        raise ValueError("Groq response did not contain a valid skill list")
    return skills
