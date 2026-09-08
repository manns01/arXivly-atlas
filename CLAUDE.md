# Project: "arXivly-atlas"

## What this is
A personal arXiv daily papers digest site which lists paper based on user's favourite arXiv bulletins (e.g., astro-ph, astro-ph.CO, astro-ph.HE, hep-ph, gr-qc etc), so that there is no need to check individual webpapges. Though cross listing exists, but not all papers do it.

## Goal
Automatically generate a personal website that shows today’s arXiv papers filtered by my research topics, hosted on GitHub Pages. I just open the URL each morning instead of browsing arXiv. The novely of this site should be to create an atlas, connect similar papers, list them together. Create a graph for visualization - which makes literature easy to digest.

## Requirements (flexible)
- Categories: astro-ph.CO, astro-ph.HE, gr-qc, hep-ph (configurable).
- Filters: keywords, optional authors, optional exclusions.
- Output: static HTML site with:
  - Today’s papers.
  - Optional: last 7 days + archive index.
- Hosting: GitHub Pages.
- Automation: GitHub Actions cron (daily).
- Language: Python + simple HTML (no heavy frameworks).

## Architecture (flexible)
1. GitHub Action (cron) triggers daily.
2. Python script:
   - Fetches new papers via arXiv API/RSS for chosen categories.
   - Filters by keywords/topics.
   - Optionally ranks or groups by topic.
   - Generates static HTML pages.
3. Action commits generated HTML to `docs/` (or `gh-pages` branch).
4. GitHub Pages serves the site.

## Config (flexible)
Use a single `config.yaml`:
- `categories`: list of arXiv categories.
- `keywords`: list of strings to match in title/abstract.
- `exclude_keywords`: optional.
- `authors`: optional priority authors.
- `site`:
  - `title`: e.g. “arXivly-atlas”
  - `max_papers_per_day`: e.g. 100.

## Deliverables (flexible)
- `config.yaml`
- `fetch_arxiv.py`
- `generate_site.py`
- `.github/workflows/daily_arxiv.yml`
- Basic CSS for readability.
- README with:
  - How to configure.
  - How to deploy.
  - How to customize filters.

## Constraints
- Keep code simple and readable.
- No external DB; just files.
- Optimize for reliability, not fancy features.
- Easy to extend later (more categories, scoring, email, etc.).
- Easy to integrate agentic AI features (like summarizing, brainstorming ideas) later.

## General rules
1. Think Before Coding: Don't assume. Don't hide confusion. Surface tradeoffs.
2. Simplicity First: Minimum code that solves the problem. Nothing speculative.
3. Goal-Driven Execution: Define success criteria. Loop until verified.

## Important
### Development Rules
- ❌ Do NOT edit any file outside 'arXivly-atlas' directory. 
- ❌ Do NOT install new Python packages without permission. 
- ✅ `arXivly-atlas` is the ONLY place for new development.
- ✅ You ARE free to create new directories for new tasks if needed

## Principles for Autonomous Development

### Progress Tracking
- **PROGRESS.md is the shared memory** — without it, agents waste time rediscovering work
- Update PROGRESS_glowGRF.md after every meaningful unit of work
- Check off completed items with dates
- Record what worked, what didn't, what's blocked
- Note failed approaches to avoid re-attempts
- Add new tasks discovered during implementation

### Agent Roles
For effective collaboration, use specialized agents:

| Role | Responsibility |
|------|-----------------|
| **Implementer** | Write module code to pass tests |
| **Test quality** | Review harness, add edge cases, improve coverage |
| **Performance** | Profile code, identify bottlenecks, optimize |
| **Code quality** | Refactor, remove duplication, improve clarity |
| **Documentation** | Keep PROGRESS_glowGRF.md, docstrings, and design in sync |