"""
Sends a formatted digest of scored jobs to Telegram, grouped by match bucket.
"""
import os
import requests

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
MAX_MSG_LEN = 3800


def _format_job_line(job: dict) -> str:
    line = f"- {job['title']} - {job['company']} ({job['match_pct']}%)\n{job['url']}"
    if job.get("bucket") == "gap_closable" and job.get("missing_skills"):
        missing = ", ".join(job["missing_skills"][:8])
        line += f"\n  Missing: {missing}"
    return line


def build_digest(scored_jobs: list) -> list:
    apply_now = [j for j in scored_jobs if j["bucket"] == "apply_now"]
    gap_closable = [j for j in scored_jobs if j["bucket"] == "gap_closable"]

    sections = []
    if apply_now:
        sections.append("APPLY NOW (80%+ match)\n" + "\n\n".join(_format_job_line(j) for j in apply_now))
    if gap_closable:
        sections.append("GAP-CLOSABLE (35-79% match)\n" + "\n\n".join(_format_job_line(j) for j in gap_closable))

    if not sections:
        return ["No new matching jobs today."]

    full_text = "\n\n".join(sections)

    messages = []
    while len(full_text) > MAX_MSG_LEN:
        split_at = full_text.rfind("\n\n", 0, MAX_MSG_LEN)
        if split_at == -1:
            split_at = MAX_MSG_LEN
        messages.append(full_text[:split_at])
        full_text = full_text[split_at:]
    messages.append(full_text)
    return messages


def send_telegram_digest(scored_jobs: list):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("Telegram: skipping (TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID not set)")
        return

    messages = build_digest(scored_jobs)
    url = TELEGRAM_API.format(token=token)
    for msg in messages:
        resp = requests.post(url, json={"chat_id": chat_id, "text": msg, "disable_web_page_preview": True}, timeout=30)
        if not resp.ok:
            print(f"Telegram send failed: {resp.status_code} {resp.text}")
