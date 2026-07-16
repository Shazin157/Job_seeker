"""
Run this ONCE locally (not part of the daily GitHub Action) whenever your resume changes.

Hybrid extraction: tries Groq's free LLM API first (better nuance, catches skills
phrased in ways a keyword taxonomy misses). If Groq is unavailable, rate-limited,
or its model gets deprecated, falls back automatically to the free taxonomy
matcher in skill_matcher.py -- so this never hard-fails, it just degrades.

Usage:
    export GROQ_API_KEY=gsk_...   # optional -- omit to use taxonomy-only
    python scripts/extract_resume_skills.py path/to/resume.txt
"""
import json
import os
import shutil
import sys

from skill_matcher import extract_skills_from_text, load_taxonomy
from llm_skill_extractor import extract_resume_skills_llm


def get_skills(resume_text: str) -> tuple:
    """Returns (skills_list, method_used)."""
    try:
        skills = extract_resume_skills_llm(resume_text)
        if skills:
            return sorted(set(skills)), "groq_llm"
    except Exception as e:
        print(f"Groq extraction failed ({e}), falling back to taxonomy matching.")

    taxonomy = load_taxonomy()
    skills = extract_skills_from_text(resume_text, taxonomy)
    return sorted(set(skills)), "taxonomy_fallback"


def main():
    if len(sys.argv) != 2:
        print("Usage: python scripts/extract_resume_skills.py path/to/resume.txt")
        sys.exit(1)

    resume_path = sys.argv[1]
    with open(resume_path, "r", encoding="utf-8") as f:
        resume_text = f.read()

    skills, method = get_skills(resume_text)
    skills_out = {"all_skills_flat": skills, "extraction_method": method}

    data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
    resume_copy_path = os.path.join(data_dir, "resume.txt")
    out_path = os.path.join(data_dir, "resume_skills.json")

    shutil.copyfile(resume_path, resume_copy_path)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(skills_out, f, indent=2)

    print(f"Wrote {resume_copy_path}")
    print(f"Wrote {out_path}")
    print(f"Extraction method used: {method}")
    print(json.dumps(skills_out, indent=2))

    if method == "taxonomy_fallback":
        print("\nUsed the keyword fallback, not Groq. Check GROQ_API_KEY is set and "
              "valid if you wanted LLM-quality extraction.")
    print("\nReview this list. If something's missing, either fix the taxonomy "
          "(data/skills_taxonomy.json) or check your Groq setup, then re-run.")


if __name__ == "__main__":
    main()
