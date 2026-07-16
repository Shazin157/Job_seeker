"""
Fetches job postings from Adzuna and JSearch (RapidAPI) and normalizes them into
a common schema: {id, title, company, description, url, source, location}.
"""
import os
import requests

SEARCH_QUERY = os.environ.get("JOB_SEARCH_QUERY", "AI ML Engineer")
SEARCH_LOCATION = os.environ.get("JOB_SEARCH_LOCATION", "India")


def fetch_adzuna(max_results=30):
    app_id = os.environ.get("ADZUNA_APP_ID")
    app_key = os.environ.get("ADZUNA_APP_KEY")
    if not app_id or not app_key:
        print("Adzuna: skipping (ADZUNA_APP_ID/ADZUNA_APP_KEY not set)")
        return []

    jobs = []
    url = "https://api.adzuna.com/v1/api/jobs/in/search/1"
    params = {
        "app_id": app_id,
        "app_key": app_key,
        "results_per_page": max_results,
        "what": SEARCH_QUERY,
        "content-type": "application/json",
    }
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        for r in data.get("results", []):
            jobs.append({
                "id": f"adzuna_{r.get('id')}",
                "title": r.get("title", "").strip(),
                "company": (r.get("company") or {}).get("display_name", "Unknown"),
                "description": r.get("description", ""),
                "url": r.get("redirect_url", ""),
                "location": (r.get("location") or {}).get("display_name", ""),
                "source": "adzuna",
            })
    except requests.RequestException as e:
        print(f"Adzuna fetch failed: {e}")
    return jobs


def fetch_jsearch(max_results=30):
    rapidapi_key = os.environ.get("RAPIDAPI_KEY")
    if not rapidapi_key:
        print("JSearch: skipping (RAPIDAPI_KEY not set)")
        return []

    jobs = []
    url = "https://jsearch.p.rapidapi.com/search"
    params = {
        "query": f"{SEARCH_QUERY} in {SEARCH_LOCATION}",
        "page": "1",
        "num_pages": "1",
    }
    headers = {
        "X-RapidAPI-Key": rapidapi_key,
        "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
    }
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        for r in data.get("data", [])[:max_results]:
            jobs.append({
                "id": f"jsearch_{r.get('job_id')}",
                "title": r.get("job_title", "").strip(),
                "company": r.get("employer_name", "Unknown"),
                "description": r.get("job_description", ""),
                "url": r.get("job_apply_link", "") or r.get("job_google_link", ""),
                "location": r.get("job_city", "") or r.get("job_country", ""),
                "source": "jsearch",
            })
    except requests.RequestException as e:
        print(f"JSearch fetch failed: {e}")
    return jobs


def fetch_all_jobs():
    jobs = fetch_adzuna() + fetch_jsearch()
    print(f"Fetched {len(jobs)} total jobs")
    return jobs


if __name__ == "__main__":
    for j in fetch_all_jobs():
        print(j["source"], "-", j["title"], "-", j["company"])
