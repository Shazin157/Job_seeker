"""
RUN THIS FIRST, BEFORE fetch_firecrawl.py GOES NEAR main.py.

We got burned once already in this project by assuming an API's schema without
checking it live (JSearch silently moved /search -> /search-v2). Don't repeat
that with Firecrawl. This script hits Firecrawl's real endpoints and prints the
RAW response so you can confirm field names before any pipeline code depends
on them.

Usage:
    export FIRECRAWL_API_KEY=fc-...
    python scripts/test_firecrawl.py
"""
import json
import os
import requests

API_KEY = os.environ.get("FIRECRAWL_API_KEY")
BASE_URL = "https://api.firecrawl.dev/v1"

if not API_KEY:
    print("Set FIRECRAWL_API_KEY first.")
    raise SystemExit(1)

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}


def test_search():
    print("\n=== Testing /search ===")
    resp = requests.post(
        f"{BASE_URL}/search",
        headers=HEADERS,
        json={"query": "Computer Vision Engineer jobs India", "limit": 3},
        timeout=30,
    )
    print("Status:", resp.status_code)
    print(json.dumps(resp.json(), indent=2)[:3000])


def test_map(url="https://boards.greenhouse.io/example"):
    print(f"\n=== Testing /map on {url} ===")
    resp = requests.post(
        f"{BASE_URL}/map",
        headers=HEADERS,
        json={"url": url},
        timeout=30,
    )
    print("Status:", resp.status_code)
    print(json.dumps(resp.json(), indent=2)[:3000])


def test_scrape(url="https://firecrawl.dev"):
    print(f"\n=== Testing /scrape on {url} ===")
    resp = requests.post(
        f"{BASE_URL}/scrape",
        headers=HEADERS,
        json={"url": url, "formats": ["markdown"]},
        timeout=30,
    )
    print("Status:", resp.status_code)
    print(json.dumps(resp.json(), indent=2)[:3000])


if __name__ == "__main__":
    test_search()
    test_scrape()
    # test_map() -- uncomment and point at a REAL target company careers URL
    # you actually want to scrape before running this one, since it's the
    # one you'll wire into the pipeline
    print("\n\nCheck the printed JSON above against what fetch_firecrawl.py "
          "expects (see the field names it reads with .get(...)) before "
          "trusting the integration.")
