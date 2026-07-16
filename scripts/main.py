"""
Daily entrypoint. Run by GitHub Actions on a schedule.

Flow:
1. Load resume_skills.json (static, only regenerated manually).
2. Load seen_jobs.json (dedup state from previous runs).
3. Fetch fresh jobs from Adzuna + JSearch.
4. Filter out jobs already seen.
5. Score new jobs against resume skills.
6. Send Telegram digest for anything scoring >= 50%.
7. Update seen_jobs.json (the workflow commits this back to the repo).
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

# Cap how many new jobs get sent through the (paid) skill-extraction step per run,
# to keep API costs predictable even if a search term returns a huge batch.
MAX_JOBS_TO_SCORE_PER_RUN = int(os.environ.get("MAX_JOBS_TO_SCORE_PER_RUN", "40"))


def load_seen_ids() -> set:
    if not os.path.exists(SEEN_JOBS_PATH):
        return set()
    try:
        with open(SEEN_JOBS_PATH, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        print(f"WARNING: data/seen_jobs.json is corrupted ({e}). Treating as empty -- "
              "you may get duplicate notifications for jobs seen before this point. "
              "Fix by editing the file directly on GitHub's web editor and typing "
              "a clean [] (not via a local shell redirect, which can write the wrong encoding).")
        return set()


def save_seen_ids(seen_ids: set):
    with open(SEEN_JOBS_PATH, "w", encoding="utf-8") as f:
        json.dump(sorted(seen_ids), f, indent=2)


def check_resume_staleness():
    """
    Warn (loudly, via Telegram too) if resume.txt has been edited more recently
    than resume_skills.json was regenerated -- meaning the skill list scoring
    every job today no longer reflects the resume you'd actually submit.
    """
    if not os.path.exists(RESUME_TXT_PATH):
        # Older setup without the tracked resume.txt copy -- nothing to compare against.
        return
    resume_mtime = os.path.getmtime(RESUME_TXT_PATH)
    skills_mtime = os.path.getmtime(RESUME_SKILLS_PATH)
    if resume_mtime > skills_mtime:
        warning = (
            "⚠️ resume.txt is newer than resume_skills.json. "
            "Today's matches are scored against a STALE skill list. "
            "Re-run scripts/extract_resume_skills.py and commit the update."
        )
        print(warning)
        send_telegram_digest([{"title": warning, "company": "", "match_pct": 0,
                                "bucket": "apply_now", "url": "", "missing_skills": []}])


def main():
    if not os.path.exists(RESUME_SKILLS_PATH):
        print("ERROR: data/resume_skills.json not found. Run scripts/extract_resume_skills.py "
              "locally first and commit the result.")
        return

    check_resume_staleness()

    seen_ids = load_seen_ids()
    all_jobs = fetch_all_jobs()

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
                f"⚠️ Groq unavailable for {fallback_count}/{len(scored)} jobs today -- "
                "scored via the keyword fallback instead. Check GROQ_API_KEY / Groq status "
                "if this keeps happening."
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
