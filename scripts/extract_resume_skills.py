"""
Run this ONCE locally (not part of the daily GitHub Action) whenever your resume changes.

Hybrid extraction: tries Groq's free LLM API first (better nuance, catches skills
phrased in ways a keyword taxonomy misses). If Groq is unavailable, rate-limited,
or its model gets deprecated, falls back automatically to the free taxonomy
matcher in skill_matcher.py -- so this never hard-fails, it just degrades.

Also derives a suggested job-search query from the resume itself (e.g. "Computer
Vision Engineer" or "Public Policy Analyst"), so the daily job doesn't need a
hardcoded query baked into the workflow -- swap resumes, get a matching query
automatically. No taxonomy fallback exists for this specific step since it's not
a skill-matching problem; if Groq is down, this falls back to a generic query
built from your top detected skills, which is a rough guess -- override it
manually in the workflow's JOB_SEARCH_QUERY if it looks wrong.

Usage:
    export GROQ_API_KEY=gsk_...   # optional -- omit to use taxonomy-only + rough query guess
    python scripts/extract_resume_skills.py path/to/resume.txt
"""
import json
import os
import shutil
import sys

from skill_matcher import extract_skills_from_text, load_taxonomy
from llm_skill_extractor import extract_resume_skills_llm, suggest_job_query_llm


def get_skills(resume_text: str) -> tuple:
    """Returns (skills_list, method_used)."""
    try:
        skills = extract_resume_skills_llm(resume_text)
        if skills:
            return sorted(set(skills)), "groq_llm"
    except Exception as e:
        print(f"Groq skill extraction failed ({e}), falling back to taxonomy matching.")

    taxonomy = load_taxonomy()
    skills = extract_skills_from_text(resume_text, taxonomy)
    return sorted(set(skills)), "taxonomy_fallback"


def get_suggested_query(resume_text: str, fallback_skills: list) -> tuple:
    """Returns (query_string, method_used)."""
    try:
        query = suggest_job_query_llm(resume_text)
        return query, "groq_llm"
    except Exception as e:
        print(f"Groq query suggestion failed ({e}), falling back to a rough guess "
              "from top detected skills -- review this before trusting it.")
        # Rough fallback: join the first few non-generic-sounding skills.
        # Not reliable, just better than a hardcoded query that ignores the
        # resume entirely.
        guess = " ".join(fallback_skills[:3]) if fallback_skills else "Entry Level"
        return guess, "fallback_guess"


def main():
    if len(sys.argv) != 2:
        print("Usage: python scripts/extract_resume_skills.py path/to/resume.txt")
        sys.exit(1)

    resume_path = sys.argv[1]
    with open(resume_path, "r", encoding="utf-8") as f:
        resume_text = f.read()

    skills, skills_method = get_skills(resume_text)
    query, query_method = get_suggested_query(resume_text, skills)

    skills_out = {
        "all_skills_flat": skills,
        "extraction_method": skills_method,
        "suggested_query": query,
        "suggested_query_method": query_method,
    }

    data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
    resume_copy_path = os.path.join(data_dir, "resume.txt")
    out_path = os.path.join(data_dir, "resume_skills.json")

    shutil.copyfile(resume_path, resume_copy_path)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(skills_out, f, indent=2)

    print(f"Wrote {resume_copy_path}")
    print(f"Wrote {out_path}")
    print(f"Skill extraction method: {skills_method}")
    print(f"Suggested search query: \"{query}\" (method: {query_method})")
    print(json.dumps(skills_out, indent=2))

    if skills_method == "taxonomy_fallback":
        print("\nUsed the keyword fallback for skills, not Groq. Check GROQ_API_KEY "
              "is set and valid if you wanted LLM-quality extraction.")
    if query_method == "fallback_guess":
        print("\nThe suggested query is a rough guess, not Groq-generated. Consider "
              "setting JOB_SEARCH_QUERY manually in the workflow if this looks off.")

    print("\nReview this list and the suggested query before committing. If a "
          "skill's missing, fix the taxonomy (data/skills_taxonomy.json) or check "
          "your Groq setup, then re-run.")


if __name__ == "__main__":
    main()
