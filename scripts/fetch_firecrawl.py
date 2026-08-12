"""
Firecrawl adds two things Adzuna/JSearch can't do:
  1. search_web_for_jobs()    -- broader open-web search, not limited to those
                                  two aggregators' own indexes.
  2. scrape_target_companies() -- hits specific companies' career pages
                                  directly, working around the "every ATS has
                                  different HTML" problem raised earlier in
                                  this project, without needing to write a
                                  custom scraper per company.

COST WARNING: Firecrawl is NOT free like the rest of this stack. Free tier is
1,000 credits/month (Scrape/Map = 1 credit/page). This module deliberately
avoids the /extract endpoint, which has been reported to bill separately on
top of your plan -- everything here uses /scrape and /map only.

Both functions are optional -- if FIRECRAWL_API_KEY isn't set, main.py should
skip calling them entirely, same pattern as Groq's optional fallback.

SCHEMA WARNING: run scripts/test_firecrawl.py against your real key BEFORE
trusting this file's parsing. This project already got burned once by an
API silently changing its response shape (JSearch). All response parsing
below uses .get() with fallbacks and prints a warning rather than crashing
if a field is missing, but that's a safety net, not a substitute for
actually checking the real response shape yourself first.
"""
import json
import os
import re
import requests

FIRECRAWL_BASE_URL = "https://api.firecrawl.dev/v1"

# Hard caps to keep monthly credit usage predictable on the free tier.
# Adjust via env if you upgrade your Firecrawl plan.
SEARCH_MAX_RESULTS = int(os.environ.get("FIRECRAWL_SEARCH_MAX_RESULTS", "5"))
MAX_NEW_COMPANY_SCRAPES_PER_RUN = int(os.environ.get("FIRECRAWL_MAX_NEW_SCRAPES", "10"))

TARGET_COMPANIES_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "target_companies.json"
)

# Career-page URLs that look like an individual job posting, not a listing
# page, nav link, or footer link. Adjust based on what you see when you
# actually run this against your target companies -- this is a rough
# heuristic, not a guarantee.
_JOB_URL_PATTERN = re.compile(
    r"/(jobs?|careers?|positions?|openings?)/[\w\-]+", re.IGNORECASE
)


def _headers():
    api_key = os.environ.get("FIRECRAWL_API_KEY")
    if not api_key:
        raise RuntimeError("FIRECRAWL_API_KEY not set")
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}


def search_web_for_jobs(query: str) -> list:
    """
    Broad open-web search for job postings, as a 3rd source alongside
    Adzuna/JSearch. Returns the same normalized job dict shape as fetch_jobs.py.
    Raises on failure -- caller should catch and treat as "this source is down."
    """
    resp = requests.post(
        f"{FIRECRAWL_BASE_URL}/search",
        headers=_headers(),
        json={
            "query": f"{query} jobs India",
            "limit": SEARCH_MAX_RESULTS,
            "scrapeOptions": {"formats": ["markdown"]},
        },
        timeout=45,
    )
    resp.raise_for_status()
    payload = resp.json()

    results = payload.get("data", [])
    if not isinstance(results, list):
        print(f"Firecrawl search: unexpected response shape, got keys {list(payload.keys())}. "
              "Check scripts/test_firecrawl.py output against this parsing.")
        return []

    # Exclude major aggregators whose ToS prohibits direct scraping (this
    # applies regardless of which tool does the technical work) and whose
    # postings JSearch already sources legally via Google for Jobs anyway --
    # so excluding them loses no real coverage, only redundant risk.
    EXCLUDED_DOMAINS = ("linkedin.com", "indeed.com", "glassdoor.com")

    jobs = []
    for r in results:
        url = r.get("url", "")
        if not url or any(domain in url for domain in EXCLUDED_DOMAINS):
            continue
        jobs.append({
            "id": f"firecrawl_search_{abs(hash(url))}",
            "title": r.get("title", "Untitled posting"),
            "company": "Unknown (from web search)",
            "description": r.get("markdown", "") or r.get("description", ""),
            "url": url,
            "location": "",
            "source": "firecrawl_search",
        })
    return jobs


def _load_target_companies() -> list:
    if not os.path.exists(TARGET_COMPANIES_PATH):
        return []
    with open(TARGET_COMPANIES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _map_company_careers(careers_url: str) -> list:
    """Returns a list of URLs found under the given careers page domain."""
    resp = requests.post(
        f"{FIRECRAWL_BASE_URL}/map",
        headers=_headers(),
        json={"url": careers_url},
        timeout=30,
    )
    resp.raise_for_status()
    payload = resp.json()
    links = payload.get("links", [])
    if not isinstance(links, list):
        print(f"Firecrawl map: unexpected response shape for {careers_url}, "
              f"got keys {list(payload.keys())}.")
        return []
    return links


def _scrape_job_page(url: str) -> dict:
    """Returns {title, markdown} for a single job posting URL."""
    resp = requests.post(
        f"{FIRECRAWL_BASE_URL}/scrape",
        headers=_headers(),
        json={"url": url, "formats": ["markdown"]},
        timeout=30,
    )
    resp.raise_for_status()
    payload = resp.json()
    data = payload.get("data", {})
    markdown = data.get("markdown", "")
    title = (data.get("metadata", {}) or {}).get("title", "") or "Untitled posting"
    return {"title": title, "markdown": markdown}


def scrape_target_companies(seen_ids: set) -> list:
    """
    Maps each company in data/target_companies.json, filters for URLs that
    look like individual job postings, skips anything already in seen_ids
    (checked BEFORE scraping, to avoid spending a credit re-fetching a job
    you've already seen), then scrapes up to MAX_NEW_COMPANY_SCRAPES_PER_RUN
    new postings. Returns the same normalized job dict shape as fetch_jobs.py.
    """
    companies = _load_target_companies()
    if not companies:
        print("Firecrawl company scrape: no companies configured in "
              "data/target_companies.json, skipping.")
        return []

    jobs = []
    scrapes_used = 0

    for company in companies:
        if scrapes_used >= MAX_NEW_COMPANY_SCRAPES_PER_RUN:
            break

        name = company.get("name", "Unknown company")
        careers_url = company.get("careers_url", "")
        if not careers_url:
            continue

        try:
            links = _map_company_careers(careers_url)
        except requests.RequestException as e:
            print(f"Firecrawl map failed for {name}: {e}")
            continue

        job_links = [l for l in links if _JOB_URL_PATTERN.search(l)]

        for link in job_links:
            if scrapes_used >= MAX_NEW_COMPANY_SCRAPES_PER_RUN:
                break

            job_id = f"firecrawl_company_{abs(hash(link))}"
            if job_id in seen_ids:
                continue  # skip BEFORE spending a scrape credit

            try:
                scraped = _scrape_job_page(link)
            except requests.RequestException as e:
                print(f"Firecrawl scrape failed for {link}: {e}")
                continue

            scrapes_used += 1
            jobs.append({
                "id": job_id,
                "title": scraped["title"],
                "company": name,
                "description": scraped["markdown"],
                "url": link,
                "location": "",
                "source": "firecrawl_company",
            })

    print(f"Firecrawl company scrape: {scrapes_used} new postings scraped "
          f"(cap: {MAX_NEW_COMPANY_SCRAPES_PER_RUN}/run).")
    return jobs
