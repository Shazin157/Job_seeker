# Job Radar (Hybrid: Free LLM + Free Fallback)

Daily automated job search that scores postings against your resume by explicit
skill overlap and sends a Telegram digest, split into:

- 🟢 **Apply now** — 80%+ of the job's detected skills match your resume
- 🟡 **Gap-closable** — 50-79% match, with the specific missing skills listed so you
  know exactly what to add to your resume or learn next

## How extraction works (hybrid, $0 either way)

Every skill extraction call (resume, and each new job posting) tries **Groq's
free LLM API** first for better nuance and phrasing coverage. If Groq is
unavailable for any reason — rate limit, timeout, deprecated model, malformed
response — it falls back automatically to a static keyword taxonomy
(`data/skills_taxonomy.json`), so the pipeline never hard-fails, it just
degrades in quality for that run.

**You will be told when this happens.** Console logs and a Telegram alert fire
if more than half a run's jobs fell back to the taxonomy — a silent Groq outage
should not silently produce worse matches without you knowing.

Real constraint to know about: free-tier LLM model catalogs get deprecated or
rate-limited without warning across every provider, not just Groq. That's why
the fallback exists rather than treating Groq as guaranteed available.

## One-time setup

### 1. Create the repo
Push this folder to a new GitHub repo. **Use a private repo** — your resume text
lives in `data/resume.txt` in plain text.

### 2. Get your API keys / tokens

| Secret | Where to get it | Cost | Required? |
|---|---|---|---|
| `GROQ_API_KEY` | console.groq.com → API keys, no card | Free (1,000 req/day on 70B models) | Optional — omit to run taxonomy-only |
| `ADZUNA_APP_ID` / `ADZUNA_APP_KEY` | developer.adzuna.com → register app | Free, 1,000 calls/month | Yes |
| `RAPIDAPI_KEY` | rapidapi.com or openwebninja.com → subscribe to "JSearch" | Free tier, no card | Yes |
| `TELEGRAM_BOT_TOKEN` | Message @BotFather → `/newbot` → copy token | Free | Yes |
| `TELEGRAM_CHAT_ID` | Message your bot, then visit `https://api.telegram.org/bot<TOKEN>/getUpdates`, read `message.chat.id` | Free | Yes |

If `GROQ_MODEL` (in `scripts/llm_skill_extractor.py`) ever gets deprecated,
check console.groq.com/docs/models and update the constant — the fallback keeps
things running in the meantime, but LLM quality only comes back once you fix it.

### 3. Add secrets to GitHub
Repo → Settings → Secrets and variables → Actions → New repository secret.

### 4. Generate your resume skill list (run locally)
```bash
export GROQ_API_KEY=gsk_...   # optional
python scripts/extract_resume_skills.py path/to/your_resume.txt
```
Writes `data/resume.txt` and `data/resume_skills.json` (which records which
method — `groq_llm` or `taxonomy_fallback` — actually produced it). **Check the
output.** If something's missing and it used the fallback, either fix your
Groq key or add the missing wording to `data/skills_taxonomy.json`.

```bash
git add data/resume.txt data/resume_skills.json
git commit -m "Add resume skill inventory"
git push
```

`main.py` also warns (console + Telegram) if `resume.txt` is newer than
`resume_skills.json` — meaning you edited your resume but forgot to re-run
the extraction script.

### 5. Enable the workflow
Runs daily at 09:00 IST automatically once pushed. To test immediately:
Actions tab → "Daily Job Search" → Run workflow.

## Tuning

- `JOB_SEARCH_QUERY` / `JOB_SEARCH_LOCATION` — edit in the workflow file's `env` block.
- `APPLY_NOW_THRESHOLD` / `GAP_CLOSABLE_THRESHOLD` — edit constants in `scripts/score_jobs.py`.
- `GROQ_MODEL` — edit in `scripts/llm_skill_extractor.py` if Groq deprecates the current one.
- `data/skills_taxonomy.json` — the fallback's only lever. Keep it current even
  while Groq is working, since it's your safety net.

## Known limitations

- Groq's free tier is generous for your volume (~40 jobs/day vs. a 1,000/day cap)
  but not contractually guaranteed — treat any single day's LLM availability as
  best-effort, not SLA-backed.
- The taxonomy fallback can't distinguish must-have from nice-to-have skills in
  a posting — everything detected counts toward the denominator. Treat a
  fallback-scored match % as an upper bound, not an exact requirement count.
- Adzuna and JSearch don't cover every company — large Indian MNCs on Workday/Taleo
  won't show up. Greenhouse/Lever JSON endpoints are worth adding later for
  specific target companies.
