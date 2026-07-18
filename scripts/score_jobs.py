"""
For each job: try Groq's free LLM API to extract required skills (better nuance
than keyword matching). If Groq fails for any reason -- rate limit, timeout,
deprecated model, malformed response -- fall back automatically to the free
taxonomy matcher. Either way, compute an explicit skill-overlap percentage
against your resume_skills.json. This is a real, explainable ratio: (skills you
have) / (skills the job asks for) -- not an embedding similarity score.
"""
import json
import os
import re
import time

from skill_matcher import extract_skills_from_text, load_taxonomy
from llm_skill_extractor import extract_job_skills_llm

APPLY_NOW_THRESHOLD = 80
GAP_CLOSABLE_THRESHOLD = 35
# Groq's free tier caps requests-per-minute. A fixed delay between sequential
# calls keeps a 30-40 job batch well under that cap instead of firing all
# requests back-to-back and tripping 429s on nearly every call.
GROQ_CALL_DELAY_SECONDS = float(os.environ.get("GROQ_CALL_DELAY_SECONDS", "2.5"))

# Skill matching has no concept of seniority -- a posting wanting 5 years'
# experience scores identically to an entry-level one if the keywords match.
# This catches explicit "N years experience" phrasing and rejects postings
# above the threshold BEFORE spending a Groq call on them (saves API usage
# too). Real limitation: regex can false-positive on years mentioned in
# unrelated context (e.g. "we've been in business for 10 years") and can miss
# experience requirements phrased without a number ("senior", "extensive
# background"). Treat this as a rough pre-filter, not a guarantee.
MAX_YEARS_EXPERIENCE = int(os.environ.get("MAX_YEARS_EXPERIENCE", "1"))

_YEARS_PATTERNS = [
    re.compile(r"(\d+)\s*\+\s*years?\s+(?:of\s+)?experience", re.IGNORECASE),
    re.compile(r"minimum\s+(?:of\s+)?(\d+)\s+years?", re.IGNORECASE),
    re.compile(r"at\s+least\s+(\d+)\s+years?", re.IGNORECASE),
    re.compile(r"(\d+)\s*[-to]+\s*\d+\s*years?\s+(?:of\s+)?experience", re.IGNORECASE),
    re.compile(r"(\d+)\+?\s*years?\s+(?:of\s+)?(?:relevant\s+|professional\s+)?experience", re.IGNORECASE),
]
_FRESHER_MARKERS = re.compile(
    r"\b(fresher|entry[\s-]level|entry[\s-]level|0[\s-]?1\s*years?|no\s+experience\s+required|"
    r"recent\s+graduate|new\s+grad)\b", re.IGNORECASE
)


def min_years_required(description: str) -> int:
    """Returns the lowest explicit year-count found, or 0 if none / fresher-marked."""
    if _FRESHER_MARKERS.search(description):
        return 0
    found = []
    for pattern in _YEARS_PATTERNS:
        for match in pattern.finditer(description):
            found.append(int(match.group(1)))
    return min(found) if found else 0


def load_resume_skills(path: str) -> set:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return set(data.get("all_skills_flat", []))


def extract_job_required_skills(job_text: str, taxonomy: dict) -> tuple:
    """Returns (skills_list, method_used)."""
    try:
        skills = extract_job_skills_llm(job_text)
        if skills:
            return skills, "groq_llm"
    except Exception as e:
        print(f"Groq extraction failed for this job ({e}), falling back to taxonomy.")

    skills = extract_skills_from_text(job_text, taxonomy)
    return skills, "taxonomy_fallback"


def score_job(job: dict, resume_skill_set: set, taxonomy: dict) -> dict:
    min_years = min_years_required(job.get("description", ""))
    if min_years > MAX_YEARS_EXPERIENCE:
        job["match_pct"] = 0
        job["missing_skills"] = []
        job["matched_skills"] = []
        job["bucket"] = "skip"
        job["skip_reason"] = f"requires {min_years}+ years experience"
        job["extraction_method"] = "experience_filter"
        return job

    required, method = extract_job_required_skills(job.get("description", ""), taxonomy)
    job["extraction_method"] = method

    if not required:
        job["match_pct"] = 0
        job["missing_skills"] = []
        job["matched_skills"] = []
        job["bucket"] = "skip"
        return job

    required_set = set(required)
    matched = sorted(required_set & resume_skill_set)
    missing = sorted(required_set - resume_skill_set)

    pct = round(100 * len(matched) / len(required_set))
    job["match_pct"] = pct
    job["matched_skills"] = matched
    job["missing_skills"] = missing

    if pct >= APPLY_NOW_THRESHOLD:
        job["bucket"] = "apply_now"
    elif pct >= GAP_CLOSABLE_THRESHOLD:
        job["bucket"] = "gap_closable"
    else:
        job["bucket"] = "skip"

    return job


def score_all_jobs(jobs: list, resume_skills_path: str) -> list:
    resume_skill_set = load_resume_skills(resume_skills_path)
    taxonomy = load_taxonomy()
    scored = []
    for i, job in enumerate(jobs):
        scored.append(score_job(job, resume_skill_set, taxonomy))
        if i < len(jobs) - 1:
            time.sleep(GROQ_CALL_DELAY_SECONDS)

    fallback_count = sum(1 for j in scored if j.get("extraction_method") == "taxonomy_fallback")
    if fallback_count:
        print(f"{fallback_count}/{len(scored)} jobs scored via taxonomy fallback "
              f"(Groq unavailable for those calls).")

    # Always print a visibility summary -- silence when nothing clears the
    # threshold otherwise looks identical to a broken pipeline. This shows
    # exactly how close the closest misses were.
    apply_now = sum(1 for j in scored if j["bucket"] == "apply_now")
    gap_closable = sum(1 for j in scored if j["bucket"] == "gap_closable")
    exp_filtered = sum(1 for j in scored if j.get("extraction_method") == "experience_filter")
    skipped_other = sum(1 for j in scored if j["bucket"] == "skip") - exp_filtered
    print(f"Scoring summary: {apply_now} apply_now, {gap_closable} gap_closable, "
          f"{exp_filtered} filtered for experience (>{MAX_YEARS_EXPERIENCE}y required), "
          f"{skipped_other} skipped for low skill match (out of {len(scored)}).")

    top5 = sorted(scored, key=lambda j: j["match_pct"], reverse=True)[:5]
    print("Top 5 by match %, regardless of bucket:")
    for j in top5:
        print(f"  {j['match_pct']}% -- {j['title']} @ {j['company']} "
              f"(missing: {', '.join(j['missing_skills'][:5]) or 'none'})")

    return scored
