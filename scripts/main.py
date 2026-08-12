"""
Daily entrypoint. Run by GitHub Actions on a schedule.
"""
import json
import os

from fetch_jobs import fetch_all_jobs
from score_jobs import score_all_jobs
from notify_telegram import send_telegram_digest

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(BASE_DIR, "data")
RESUME_SKILLS_PATH = os.path.join(DATA_DIR, "resume_skills.json")
RESUME_TXT_PATH = os.path.join(DATA_DIR, "resume.txt")
SEEN_JOBS_PATH = os.path.join(DATA_DIR, "seen_jobs.json")

MAX_JOBS_TO_SCORE_PER_RUN = int(os.environ.get("MAX_JOBS_TO_SCORE_PER_RUN", "40"))


def load_seen_ids() -> set:
    if not os.path.exists(SEEN_JOBS_PATH):
        return set()
    try:
        with open(SEEN_JOBS_PATH, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        print(f"WARNING: data/seen_jobs.json is corrupted ({e}). Treating as empty -- "
              "fix by editing the file directly on GitHub's web editor and typing "
              "a clean [] (not via a local shell redirect).")
        return set()


def save_seen_ids(seen_ids: set):
    with open(SEEN_JOBS_PATH, "w", encoding="utf-8") as f:
        json.dump(sorted(seen_ids), f, indent=2)


def check_resume_staleness():
    if not os.path.exists(RESUME_TXT_PATH):
        return
    resume_mtime = os.path.getmtime(RESUME_TXT_PATH)
    skills_mtime = os.path.getmtime(RESUME_SKILLS_PATH)
    if resume_mtime > skills_mtime:
        warning = (
            "resume.txt is newer than resume_skills.json. Today's matches are "
            "scored against a STALE skill list. Re-run scripts/extract_resume_skills.py."
        )
        print(warning)
        send_telegram_digest([{"title": warning, "company": "", "match_pct": 0,
                                "bucket": "apply_now", "url": "", "missing_skills": []}])


def main():
    if not os.path.exists(RESUME_SKILLS_PATH):
        print("ERROR: data/resume_skills.json not found. Run scripts/extract_resume_skills.py first.")
        return

    check_resume_staleness()

    with open(RESUME_SKILLS_PATH, "r", encoding="utf-8") as f:
        resume_data = json.load(f)
    search_query = resume_data.get("suggested_query")
    if search_query:
        print(f"Using resume-derived search query: \"{search_query}\"")
    else:
        print("No suggested_query in resume_skills.json -- falling back to env/default.")

    seen_ids = load_seen_ids()
    all_jobs = fetch_all_jobs(query=search_query)

    if os.environ.get("FIRECRAWL_API_KEY"):
        from fetch_firecrawl import search_web_for_jobs, scrape_target_companies
        try:
            all_jobs += search_web_for_jobs(search_query or "AI ML Engineer")
        except Exception as e:
            print(f"Firecrawl web search failed: {e}")
        try:
            all_jobs += scrape_target_companies(seen_ids)
        except Exception as e:
            print(f"Firecrawl company scrape failed: {e}")
    else:
        print("FIRECRAWL_API_KEY not set -- skipping Firecrawl sources.")

    new_jobs = [j for j in all_jobs if j["id"] not in seen_ids]
    print(f"{len(new_jobs)} new jobs out of {len(all_jobs)} fetched")

    new_jobs = new_jobs[:MAX_JOBS_TO_SCORE_PER_RUN]

    if new_jobs:
        scored = score_all_jobs(new_jobs, RESUME_SKILLS_PATH)
        relevant = [j for j in scored if j["bucket"] in ("apply_now", "gap_closable")]
        relevant.sort(key=lambda j: j["match_pct"], reverse=True)

        fallback_count = sum(1 for j in scored if j.get("extraction_method") == "taxonomy_fallback")
        if scored and fallback_count / len(scored) > 0.5:
            warning = (
                f"Groq unavailable for {fallback_count}/{len(scored)} jobs today -- "
                "scored via the keyword fallback instead."
            )
            print(warning)
            send_telegram_digest([{"title": warning, "company": "", "match_pct": 0,
                                    "bucket": "apply_now", "url": "", "missing_skills": []}])

        send_telegram_digest(relevant)
    else:
        print("No new jobs to score.")

    seen_ids.update(j["id"] for j in new_jobs)
    save_seen_ids(seen_ids)


if __name__ == "__main__":
    main()
