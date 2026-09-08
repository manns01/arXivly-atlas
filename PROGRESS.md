# PROGRESS — arXivly-atlas

## Motivation

As a researcher I need to keep up with new arXiv papers every day across several
listings (astro-ph.CO, astro-ph.HE, gr-qc, hep-ph). Checking each listing page
separately is slow, and the sheer volume causes information-overload burnout —
cross-listing helps but not every relevant paper is cross-listed.

**Goal:** open *one* URL each morning and see today's papers filtered to my topics,
with the novelty of an "atlas" — similar papers grouped and connected in a visual
graph so the day's literature is fast to digest. Static site, GitHub Pages, daily
GitHub Actions cron, plain Python + HTML. Designed to be extended later with agentic
AI features (summarizing, idea brainstorming).

---

## Status

- **2026-09-08** — Planning session. Requirements gathered, plan reviewed by an Opus
  critic against live arXiv (two passes; the second measured the whole pipeline on the
  Mon 7 Sep 2026 announcement day), plan revised and saved below. User will continue in
  the afternoon.
- **2026-09-08 (pm)** — Build-order steps 1–2 done. Created project `.venv` (git-ignored)
  and `requirements.txt` (5 pinned deps; only `feedparser` was actually missing from the
  conda base env). Captured live RSS fixtures for the 4 categories to `tests/fixtures/`
  (frozen at announcement day **2026-09-07**, 146 raw items — matches the critic's 2nd
  pass exactly). Implemented `arxiv_text.py` (LaTeX+Unicode→ASCII, surname extraction
  with particle folding, arXiv-id parsing, abstract-preamble stripping) and
  `fetch_arxiv.py` (pure `parse_feed`/`merge_feeds`/`filter_papers`/`score_paper`/
  `build_day` + network `fetch_feed`/`main`). **32 offline unit tests pass**
  (`python -m unittest discover -s tests`). Pipeline reproduces the measured funnel:
  146 raw → 125 unique → 78 new+cross → 21 after the seed keyword filter.
  Notes: schema_version bumped to 2; `announce_type` key from feedparser is
  `entry.arxiv_announce_type`; feedparser does **not** split `dc:creator` on commas
  (we do). Still pending before step 3 is complete: `config.yaml`, `.gitignore`.

### Measured on real data (Opus critic, 2nd pass) — drove the refinements below
- One announcement day, the 4 categories, seed keywords: 146 raw feed items → 125 unique
  → 78 after dropping replace/replace-cross → **21 after the keyword filter**.
- TF-IDF cosine on those 21: max pair similarity 0.227, median 0.027. At an edge cutoff
  of 0.15 → **2 edges, 3/21 papers connected**. A single-day atlas is not viable.
- 5-day window (n≈79) → 18 coherent clusters + 24 singletons; 18-day (n≈206) → 59
  clusters. Labels come out sensible ("recoil/event/kev/higgsino" = LZ direct-detection,
  "observing/run/lvk/lensed" = lensed BBH, etc.). **The rolling window is the feature;
  the daily graph is not.** → window promoted to a hard requirement, default bumped to 14.
- A persistent 17–20 paper mega-blob appears at every cut/window because the *filter*
  keywords ("dark matter" hit 12/21, "cosmology" 6/21) dominate the vocabulary.
  → **stop-list the include-keywords in the vectorizer.**
- Pure-Python/numpy TF-IDF over n≈206 clusters in seconds — no perf concern.

### Decisions locked in this session
- Fetch from arXiv **RSS** feeds (`https://rss.arxiv.org/rss/<cat>`), not the arXiv API
  — the API cannot express "announced today" (verified: API `published` was 4 days
  behind the announcement day).
- Keep `announce_type ∈ {new, cross}`; drop `replace` / `replace-cross` (~44% of a feed).
- The "day" is the feed's channel `<pubDate>`, never `datetime.today()`. Guard:
  if `data/raw/<pubdate>.json` exists and is non-empty, exit 0 without rebuilding.
- Atlas = rolling **14 announcement days** (today highlighted, older neighbours dimmed;
  clusters/graph over the union). Builds up from 1 day on the first run. This is a hard
  requirement, not an enhancement — a single day yields too few papers to connect.
- Vectorization: **hand-rolled TF-IDF + cosine + average-linkage clustering in numpy**
  (~80 lines). No scikit-learn, no networkx. `similarity.method` config is the seam for
  swapping in embeddings later. **The configured `keywords` are added to the TF-IDF
  stop-list** — filter terms match nearly every paper in the corpus and otherwise fuse
  everything into one mega-cluster.
- Clusters and edges are computed **separately**: clusters from average-linkage
  agglomerative partitioning (deterministic); visual edges from mutual k-NN (k≈4)
  **AND** a similarity floor (~0.08). Do NOT derive clusters from graph components —
  k-NN percolates into one giant component.
- Expect ~30% of papers to be genuine singletons with no close relatives → the day page
  needs a plain **"Unclustered"** list alongside the clusters.
- Deploy: CI builds `docs/` and publishes via `upload-pages-artifact` + `deploy-pages`;
  git commits **only** `data/raw/<date>.json`; `docs/` is git-ignored.
- `site.base_url` in config (default `/arXivly-atlas`); all HTML asset/links written
  base_url-absolute.
- First build = today only, no history backfill (RSS has no history).
- Author matching: split `<dc:creator>` on commas, normalize LaTeX escapes + Unicode to
  ASCII, compare **surnames exactly** (no raw substring — `Hu` must not match "Hubble").
  **Refined 2026-09-08:** an `authors:` entry may also carry a first initial
  (`L. Dai`), which is then required to match too. Feed authors are stored as
  `author_keys: [[initial, surname], ...]` alongside `surnames`.
- Keyword matching: plain case-insensitive substring on title+abstract (documented; user
  can add stems later).
- New deps (need install permission per CLAUDE.md): `feedparser`, `pyyaml`, `jinja2`,
  `requests`, `numpy`.

### Open items / to tune after first real run
- **Author false positives (found on the 2026-09-08 live run).** User chose
  first-initial matching. `authors:` entries are now either a bare surname (`Suyu`) or
  `Initial. Surname` (`L. Dai`) — surname still matched exactly, initial checked only
  when given. `config.yaml` pins best-guess initials for the common surnames
  (`W. Hu`, `L. Hui`, `L. Dai`, `S. More`, `B. Carr`, `D. Marsh`, `A. Green`, `H. Yu`,
  `Y. Mao`); **verify these are the intended researchers**. This dropped the clear junk
  (`Zhongtian Hu`, `Yuesheng Dai`) — author-only matches went 5 → 4 of the day's papers.
  Residual: `H. Yu` still matches `Hao Yu` / `Huai-Min Yu` (same initial); needs a full
  first name to disambiguate, deferred. `Natarajan` / `Kochanek` author-only hits remain
  and may be genuine (distinctive surnames, user-chosen).
- `similarity.edge_threshold` (~0.08), `distance_threshold` (~0.92), `knn` (4),
  `min_cluster_size` — retune once the window has real depth; measured starting points
  are in `config.yaml` comments.
- `atlas.window_days: 14` — could go to 21 if clusters still feel sparse; watch page/graph
  load time as the corpus grows.
- Verify the keyword stop-list actually breaks the observed 17–20 paper mega-blob; if not,
  also stop-list generic astro terms ("model", "mass", "constraint", …).
- `dark matter` / `cosmology` keywords are broad in astro-ph.CO — `max_papers_per_day`
  may become the real limiter; scoring order matters more than the include filter.
- `CLAUDE.md` mentions `PROGRESS_glowGRF.md` in places; the file in use is this one,
  `PROGRESS.md`.

---

## Plan

### File layout
```
arXivly-atlas/
  config.yaml
  requirements.txt          # feedparser, pyyaml, jinja2, requests, numpy  (pinned)
  .gitignore                # docs/, .venv/, __pycache__/, .DS_Store
  fetch_arxiv.py            # RSS -> filter -> dedupe -> data/raw/<pubdate>.json
  build_atlas.py            # 7-day window -> TF-IDF, cosine, kNN edges, clusters, labels
  generate_site.py          # jinja2 -> docs/  (index, archive index, per-day pages)
  build.py                  # orchestrator: fetch -> atlas -> generate; --date to re-render
  arxiv_text.py             # shared: LaTeX/Unicode normalization, surname extraction
  templates/
    base.html
    day.html                # clusters as <details>; paper cards; embedded graph
    archive_index.html
  assets/                   # source assets, copied into docs/assets/ at build
    style.css
    graph.js                # d3 v7 force sim glue
    d3.v7.min.js            # vendored, no CDN
  data/raw/<YYYY-MM-DD>.json # committed; immutable; the only tracked build output
  docs/                      # git-ignored; built in CI, published as Pages artifact
  .github/workflows/daily_arxiv.yml
  README.md
  PROGRESS.md
```
Flat scripts (no `src/` package) to match CLAUDE.md deliverables and keep it minimal.

### `fetch_arxiv.py`
- Per category: `requests.get("https://rss.arxiv.org/rss/<cat>", timeout=30)` with 1–2
  retries + backoff, parse with `feedparser`. Any category failing after retries → log,
  **exit non-zero, write nothing** (fail closed; site keeps yesterday's page).
- `pubdate` = channel `pubDate`. If `data/raw/<pubdate>.json` exists and non-empty →
  print "already built", exit 0.
- Per item: keep if `announce_type ∈ config.announce_types`. Extract
  `{id, title, abstract, authors[], surnames[], categories[], primary_category,
  announce_type, link, pdf, pubdate}`. Strip arXiv's `arXiv:xxxx Announce Type: …`
  preamble from `<description>`.
- Dedupe by arXiv id across categories; union category lists; record matched configured
  categories.
- Filter: include if any `keywords` substring matches title+abstract (case-insensitive)
  OR any configured surname is in the paper's normalized surname set; drop if any
  `exclude_keywords` matches. Empty keywords + empty authors → include all.
- Score: `title_weight*(kw hits in title) + abstract_weight*(kw hits in abstract)
  + author_bonus*(matched priority authors)`. Sort score desc, then pubdate/id.
  Truncate to `site.max_papers_per_day`.
- Write `data/raw/<pubdate>.json`:
  `{schema_version, generated_at, pubdate, categories, papers: [...]}`.
- 0-paper day: still write the file (empty `papers`); downstream renders an honest
  "no matching papers today".

### `build_atlas.py`
- Load newest `data/raw/*.json` + up to `window_days-1` previous files → dedupe by id
  (keep earliest; flag which ids are "today").
- Guards: 0 papers → empty atlas; 1 paper → single node, no edges/clusters; proceed only
  with ≥2.
- TF-IDF over `title + " " + abstract`: tokenize (lowercase, `[a-z0-9-]+`, drop small
  English stoplist + 1-char tokens **+ every configured `keywords` phrase/word** — filter
  terms match nearly the whole corpus and carry no discriminative signal),
  `tf * log((N+1)/(df+1)) + 1`, L2-normalize rows. numpy dense (few hundred × few
  thousand — fine).
- Cosine = normalized matrix @ transpose.
- **Edges (visual only):** per node keep top-k (k≈4) neighbours, keep an edge only if
  **mutual AND `cosine ≥ edge_threshold`** (~0.08 — measured distribution: max pair 0.23,
  median 0.03). `weight = cosine`.
- **Clusters (computed independently of the edge graph):** average-linkage agglomerative
  merge on `1 - cosine`, cut at `atlas.distance_threshold` (~0.92, i.e. cosine ≥ 0.08).
  Do **not** use connected components — mutual-kNN percolates into one giant component.
  Clusters `< min_cluster_size` (2) and true singletons → an **"Unclustered"** bucket
  (expect ~30% of papers).
- `label_cluster(members) -> str`: rank terms by mean TF-IDF inside minus mean outside;
  top 3–4 distinctive terms. Isolated function → LLM labeler can replace it later.
- Emit in-memory `atlas` dict: `nodes` (id, title, cluster, is_today, score, primary
  category), `links` (source, target, weight), `clusters` (label, member ids, is_today
  count), `unclustered` (ids). Passed to `generate_site.py`; also written to git-ignored
  `data/derived/<pubdate>.json` for debugging.

### `generate_site.py`
- `jinja2`. Copy `assets/*` → `docs/assets/`.
- Render with **base_url-absolute** URLs for every asset and internal link:
  - `docs/archive/<pubdate>.html` for the target day (one per raw file on a full rebuild),
  - `docs/index.html` = latest day (rendered, not copied),
  - `docs/archive/index.html` = reverse-chronological list with per-day counts.
- Day page: header "Last updated: <generated_at> UTC" (staleness alarm); today's papers
  first; clusters as `<details><summary>` (label + count) with an **"Unclustered"** block
  after them for papers with no close relatives; paper cards (title, abstract snippet,
  authors, categories, arXiv/PDF links, matched keywords, priority-author badge); atlas
  graph below, data in `<script type="application/json" id="atlas-data">`. Graph shows the
  full rolling window with **today's papers highlighted and older neighbours dimmed**.
- `assets/graph.js`: d3 v7 force sim; nodes colored by cluster, today's papers
  ringed/enlarged; hover = tooltip; click = scroll to card. Degrades to a message when
  <2 papers.

### `build.py`
- `python build.py [--date YYYY-MM-DD]`. No arg → fetch → atlas → generate for the fetched
  day. `--date` → skip fetch, rebuild atlas+site from existing `data/raw/<date>.json`.
- Propagates non-zero exit from any stage.

### `config.yaml`
```yaml
categories: [astro-ph.CO, astro-ph.HE, gr-qc, hep-ph]
announce_types: [new, cross]        # drop replace / replace-cross

keywords:                            # plain case-insensitive substring on title+abstract
  - gravitational lensing
  - wave optics
  - microlensing
  - caustic crossing
  - weak lensing
  - gravitational waves
  - dark matter
  - ultralight dark matter
  - fuzzy dark matter
  - self-interacting dark matter
  - cosmology
  - stochastic gravitational waves
  - supermassive black holes
exclude_keywords: []

authors:                             # surname match, LaTeX/Unicode-normalized
  # lensing
  - Zumalacarregui
  - Suyu
  - Vegetti
  - Ezquiaga
  - Ajith
  - Venumadhav
  - Hannuksela
  - Keitel
  - Oguri
  - Dai
  - Natarajan
  - Kochanek
  - Schneider
  - More
  # ULDM
  - Hu
  - Hui
  - Broadhurst
  - Marsh
  - Slatyer
  - Thaler
  - Graham
  # PBH
  - Carr
  - Sasaki
  - Suyama
  - Green
  - Kühnel
  - Kaiser
  # SIDM
  - Spergel
  - Tulin
  - Yu
  - Vogelsberger
  # FRB lensing
  - Masui
  # structure / surveys
  - Wechsler
  - Mao

scoring:
  title_weight: 3
  abstract_weight: 1
  author_bonus: 5

similarity:
  method: tfidf                      # seam for "embeddings" later
  knn: 4                             # visual edges: mutual k-NN ...
  edge_threshold: 0.08              # ... AND cosine >= this (measured: max pair ~0.23)
  distance_threshold: 0.92          # clusters: agglomerative cut on 1 - cosine
  min_cluster_size: 2               # smaller -> "Unclustered" bucket
  stoplist_keywords: true           # add config.keywords to the TF-IDF stop-list

atlas:
  window_days: 14                   # single-day corpus is too small to connect

site:
  title: arXivly-atlas
  base_url: /arXivly-atlas           # "" for user site / custom domain
  max_papers_per_day: 100
```

### `.github/workflows/daily_arxiv.yml`
- Triggers: `schedule: - cron: "23 7 * * 1-5"` (UTC; weekday mornings, after the ~04:00
  UTC feed rebuild; `:23` dodges top-of-hour scheduler backlog) + `workflow_dispatch`.
- **build job:** checkout; setup-python 3.11 + pip cache; `pip install -r
  requirements.txt`; `python build.py`. Non-zero exit → job fails, nothing publishes. If
  a new `data/raw/*.json` was produced, commit **only that file** to `main`
  (`git add data/raw && git diff --cached --quiet || (git commit && git push)`).
  `permissions: contents: write`.
- **deploy job:** `actions/upload-pages-artifact` `path: docs/` → `actions/deploy-pages`.
  `permissions: pages: write, id-token: write`.
- Concurrency group so overlapping runs don't race the push.

### `README.md`
Configure (`config.yaml` fields, keyword substring semantics, author surname matching);
deploy (create repo, Settings→Pages source = GitHub Actions, Actions write permission,
first `workflow_dispatch`); run locally (`pip install -r requirements.txt && python
build.py`, open `docs/index.html`); how the atlas is built and where to extend
(`similarity.method` seam, `label_cluster`, immutable `data/raw` for future LLM
summarization/brainstorming).

### Dependencies (need install permission per CLAUDE.md)
`feedparser`, `pyyaml`, `jinja2`, `requests`, `numpy` — pinned in `requirements.txt`.
No scikit-learn, no networkx. d3 v7 vendored, not a pip dep.

---

## Build order (checklist)

- [x] 1. This PROGRESS.md (motivation + plan + checklist).
- [x] 2. Save real RSS response per category to `tests/fixtures/` (while live); build &
      unit-test `arxiv_text.py` (LaTeX/Unicode/surname) and the feed parser offline.
      *(2026-09-08: fixtures frozen at 2026-09-07; `arxiv_text.py` + `fetch_arxiv.py`
      pure pipeline done; 32 unit tests pass.)*
- [x] 3. `config.yaml`, `.gitignore`. *(all done 2026-09-08. `config.yaml` uses the
      planned values verbatim; `Kühnel`→`Kuhnel` in the author list since matching is
      done on normalized ASCII. `.gitignore` also excludes `data/derived/`.)*
- [x] 4. `fetch_arxiv.py` — run live once; inspect `data/raw/<date>.json`; spot-check ids
      and `announce_type` on arxiv.org. *(2026-09-08: live run wrote
      `data/raw/2026-09-07.json` — feed had not rolled to the 8th yet.
      Re-run → "already built", exit 0, no second write. Bad category → fail-closed,
      exit 1, existing file untouched. Spot-checks pass: `2609.04308` cross-listed
      CO/HE/hep-ph, preamble stripped, LaTeX names normalized in `authors`/`surnames`.
      After adding first-initial author matching: **25 papers**, 41 unit tests pass.)*
- [~] 5. `git init`, first commit, push; user creates GitHub repo, sets Pages source =
      GitHub Actions, enables Actions write permission.
      *(2026-09-08: `git init` on `main` + first commit `e8c71e8` done locally
      (14 files). **User still needs to:** create the GitHub repo, `git remote add
      origin …`, `git push -u origin main`, then Settings → Pages → Source = GitHub
      Actions and Settings → Actions → Workflow permissions = read/write.)*
- [ ] 6. Minimal workflow + placeholder `docs/index.html`; run via `workflow_dispatch`;
      confirm artifact deploy works and `base_url` resolves at the real Pages URL —
      before the real templates exist.
- [ ] 7. `build_atlas.py` — verify clusters/edges/labels on the window; tune `knn` /
      `distance_threshold`.
- [ ] 8. `templates/`, `generate_site.py`, `assets/` (CSS, `graph.js`, vendored d3) —
      open `docs/index.html` locally; check graph, links, collapsibles, "last updated".
- [ ] 9. `build.py` orchestrator; wire real build into the workflow.
- [ ] 10. `README.md`; final PROGRESS.md pass.

## Verification

- **Offline:** unit tests for `arxiv_text` (`Mu\~{n}oz`→Munoz, `Hlo\v{z}ek`→Hlozek,
  `Kühnel`→Kuhnel) and the parser (fixture in → expected filtered/deduped/scored papers,
  `replace` items excluded).
- **Fetch, live:** `python fetch_arxiv.py` → non-empty `data/raw/<date>.json`; re-run →
  "already built", exit 0, no second write. Bad URL → non-zero exit, no file written.
- **Atlas:** `python build_atlas.py` → related papers together, mutual-kNN graph connected
  but not a hairball; 0- and 1-paper inputs don't raise.
- **Site:** `python build.py` → open `docs/index.html`: today's papers first, clusters
  collapse/expand, graph renders and click-scrolls, every asset/link resolves under
  `base_url`, "Last updated" shows.
- **Re-render:** `python build.py --date <existing>` rebuilds without fetching.
- **CI:** `workflow_dispatch` → build job commits only `data/raw/<date>.json`; deploy job
  publishes `docs/`; live Pages URL matches local; a forced build failure publishes
  nothing and leaves the previous site intact.
- **Rolling window:** after ≥2 daily runs, the atlas spans multiple days and the archive
  index lists each.
