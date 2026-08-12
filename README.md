# Job Radar

Daily automated job search that scores postings against your resume by explicit
skill overlap and sends a Telegram digest, split into:

- APPLY NOW: 80%+ of the job's detected skills match your resume
- GAP-CLOSABLE: 35-79% match, with missing skills listed
- Postings requiring more than MAX_YEARS_EXPERIENCE (default 2) are filtered
  out before scoring, since skill-matching alone can't judge seniority fit.

## Sources
- **Adzuna** + **JSearch** (RapidAPI) -- free-tier job board aggregators.
- **Firecrawl** (optional, requires FIRECRAWL_API_KEY) -- adds:
  - Broad open-web search for postings beyond the two aggregators' own index
  - Direct scraping of specific companies' career pages (configured in
    data/target_companies.json), working around the "every ATS has different
    HTML" problem without writing a custom scraper per company.
  - COST WARNING: Firecrawl is NOT free like the rest of this stack. Free tier
    is 1,000 credits/month (Scrape/Map = 1 credit/page). This integration
    deliberately avoids the /extract endpoint (reported to bill separately).
  - Run `python scripts/test_firecrawl.py` against your real API key FIRST,
    before trusting fetch_firecrawl.py's parsing -- this project already got
    burned once by assuming an API schema without checking it live (JSearch
    silently moved endpoints mid-project).

## Extraction: hybrid, mostly free
Every skill/query extraction tries Groq's free LLM API first
(llama-3.3-70b-versatile, ~1,000 req/day free). Falls back automatically to a
static keyword taxonomy (data/skills_taxonomy.json) on any Groq failure.

The search query is also derived FROM the resume (via Groq, with a rough
fallback guess if Groq's down) -- not hardcoded. Swap resumes, get a matching
query automatically.

## One-time setup
1. Create a private GitHub repo, push this project.
2. Get free API keys: Adzuna (developer.adzuna.com), JSearch/RapidAPI, Telegram
   bot (@BotFather), Groq (console.groq.com, optional), Firecrawl (optional).
3. Add all as repo secrets (Settings -> Secrets and variables -> Actions).
4. Run `python scripts/extract_resume_skills.py path/to/resume.txt` locally.
   Review the printed skills AND suggested_query before committing
   data/resume.txt + data/resume_skills.json.
5. If using Firecrawl for target companies: edit data/target_companies.json
   with real company names + career page URLs, and test with
   scripts/test_firecrawl.py first.
6. Reset data/seen_jobs.json to [] via GitHub's WEB EDITOR (never via a local
   shell echo -- PowerShell writes UTF-16 with a BOM, which corrupts the file).
7. Actions tab -> Daily Job Search -> Run workflow, to test manually.

## Git workflow habit
The daily workflow commits data/seen_jobs.json back to main after every run.
Run `git pull --rebase origin main` as the FIRST command every time you open
this project locally, before making any edits, to avoid rejected pushes.

## Known limitations
- Experience filter is regex-based and can false-positive on phrasing like
  "our company has 20 years of experience" (misread as a role requirement).
- Firecrawl's exact response schema should be verified against your own key
  via test_firecrawl.py -- don't trust the parsing blind.
- Keyword taxonomy fallback only catches skills phrased the way it expects.
