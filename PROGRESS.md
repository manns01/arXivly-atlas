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

- **2026-09-11 (map graph spacing + graph->card click fix)**:
  - Map view (`assets/graph.js`) was cramped -- few subject nodes with short
    link distances (40-100px) and modest repulsion (-420) settled into a
    tight knot with lots of dead canvas around it. Widened map-only link
    distance to 200-380px, charge to -700, and shrank node radius range
    34px->22px max so bubbles read as a spread-out map, not a packed clump.
    Papers-view force params untouched.
  - Clicking an atlas-graph node for a paper outside the current window
    (e.g. a non-today neighbour of today's cluster) silently did nothing --
    its card was `hidden` by the window filter and `onNodeClick` never
    checked. `filters.js` now tracks the last applied visible-id set and
    exposes `window.atlasFilters.ensureVisible(id)`, which widens the window
    to "whole window" only when that's specifically what's hiding the id
    (other active filters are left alone); `graph.js` calls it before
    scrolling to the card.

- **2026-09-11 (trigger timing fix)** — The 03:40 UTC cron-job.org trigger (set
  2026-09-10) consistently no-ops: it POSTs before arXiv's feed is ready, so
  `fetch_arxiv` sees the prior day's `data/raw/<date>.json` already built and
  exits 0 with nothing new. RSS channel `pubDate` claims 00:00 ET (04:00 UTC)
  but `rss.arxiv.org` itself lags that -- confirmed fresh content only landed
  at 05:40 UTC (2026-09-10) and 05:49 UTC (2026-09-11), both via manual
  `repository_dispatch`. Fix:
  - Moved both `schedule` crons in `daily_arxiv.yml` to `0 6 * * 1-5` (06:00
    UTC primary) and `30 6 * * 1-5` (06:30 UTC backup), ~11:30/12:00 IST --
    small margin past the two observed data points.
  - **TODO (user, external):** update the cron-job.org job to POST at 06:00
    UTC, and add a second job at 06:30 UTC as a cheap safety net (a no-op run
    costs ~30s and does nothing) instead of relying on GitHub's own
    `schedule` trigger, which is the same unreliable mechanism that motivated
    moving to cron-job.org in the first place.
  - Only 2 days of data on the feed-ready time -- revisit 06:00 UTC if it
    keeps no-op'ing.

- **2026-09-10 (scheduled-run reliability)** — GitHub's built-in `schedule` dropped
  this repo's runs: the `31 3 * * 1-5` primary never fired on Sep 9 or Sep 10, and the
  Sep 9 backup ran ~5h late. Site was stuck on 2026-09-09. Fixes:
  - Manually dispatched the build for 2026-09-10 (100 papers, live).
  - Added `repository_dispatch: types: [daily-arxiv]` to `daily_arxiv.yml` so an
    off-platform scheduler can trigger it punctually. Verified via
    `gh api -X POST /repos/manns01/arXivly-atlas/dispatches -f event_type=daily-arxiv`
    → full build + deploy. The two `schedule` crons stay as fallback.
  - **DONE:** cron-job.org job live — POST to
    `https://api.github.com/repos/manns01/arXivly-atlas/dispatches`, body
    `{"event_type":"daily-arxiv"}`, headers `Authorization: Bearer <fine-grained PAT,
    Contents: write>` + `Accept: application/vnd.github+json` + `X-GitHub-Api-Version:
    2022-11-28`, weekdays 03:40 UTC (09:10 IST). Test run 2026-09-10 07:04 UTC → 204 →
    build+deploy OK. PAT is fine-grained, `arXivly-atlas` only, Contents: write; set to
    no expiration (rotate via Regenerate + update the cron-job.org header).

- **2026-09-09 (researcher-friendly redesign)** — Plan:
  `~/.claude/plans/reactive-chasing-falcon.md` (Opus plan + Sonnet critic pass).
  Branch `redesign-tidy-page`. **95 unit tests pass.** Shipped:
  - **Cron**: primary `31 3 * * 1-5` (~09:01 IST) + backup `23 7 * * 1-5`; both
    weekdays. First scheduled run was manually dispatched 2026-09-09.
  - **`fetch_arxiv.build_day`**: daily cap → **newest 100 by arXiv id** (was top-200
    by score). Score still computed; it no longer orders the page, only ranks graph
    labels. `site.max_papers_per_day 200→100`.
  - **★ author match** (`arxiv_text.author_full_matches`): surname exact, then full
    given name must match ("Liang Dai" ≠ "Lei Dai") — but an initial-only paper
    rendering ("L. Dai") still counts. `filter_papers` now matches config specs
    against the full normalized names (`it["authors"]`), and `matched_authors`
    carries the config spec string so the badge shows the full name. `config.authors`
    → `[Suyu, Liang Dai]`. Re-tagged the stale `data/raw/2026-09-07.json` (had an old
    personal author list) to current config.
  - **Compact rows** (`templates/day.html` `paper_row`): title is a plain heading link
    (outside the `<details>` — no toggle clash); a one-line meta summary; abstract +
    full author list + badges + links behind the expander. Author list capped at
    `site.max_authors_shown` (10) → "first 10 … +N more" (fixes the 1000-author
    collaboration paper). `site.compact_cards`.
  - **Subject sections** (`generate_site._subject_buckets`): the 60-odd auto-clusters
    grouped under a curated, ordered `config.yaml` `subjects:` list (Lensing →
    Gravitational waves → Cosmology → Astroparticle physics → Other → Particle
    physics). A cluster is filed by its distinctive-term **label** only (no abstract
    fallback — abstracts mention everything). `particle_only_last` sinks
    astro-ph-free clusters below "Other", but a subject-label match wins. Empty/absent
    `subjects:` → the old flat cluster list. `open_subjects` (3) / `open_clusters` (3)
    control what's expanded; the rest collapse with a 2-title peek line.
  - **Atlas graph** (`assets/graph.js` rewrite): default **map** view — one node per
    subject, sized by paper count, ringed by today's share, coloured by dominant
    archive, click to jump to the section; a `map | papers` toggle. Papers view is
    scoped to today + direct neighbours and labels only the top `site.graph_labels`
    (20) by score. Category legend; "no strong links" caption when the aggregated map
    has 0 edges. Narrow filter now `display:none`s hidden nodes instead of dimming.
  - **Window toggle** (header "Today" / "Whole window"): `site.default_window: today`,
    but forced to `all` whenever `today_count == 0` (the empty-day case). filters.js
    threads the default through load/serialise so "Whole window" survives a reload and
    a shared `#topics=` link no longer forces "all". Buttons wired directly (they sit
    outside `.filters`).
  - **Filters panel** un-hidden and rendered `open` (collapsed abstracts are invisible
    to browser find, so the built-in filter is the substitute).
  - New: `assets/cards.js` (expand/collapse-all). New config: `subjects`,
    `particle_only_last`, `site.{compact_cards,open_subjects,open_clusters,
    default_window,graph_default,graph_labels,max_authors_shown}` — all with
    behaviour-preserving defaults.

- **2026-09-08** — Planning session. Requirements gathered, plan reviewed by an Opus
  critic against live arXiv (two passes; the second measured the whole pipeline on the
  Mon 7 Sep 2026 announcement day), plan revised and saved below. User will continue in
  the afternoon.
- **2026-09-08 (deploy + iterate)** — Live at **https://manns01.github.io/arXivly-atlas/**.
  Repo `manns01/arXivly-atlas` (public) created via the GitHub API using the keychain PAT;
  pushed `main`; set Actions workflow perms = write; Pages source = GitHub Actions;
  dispatched `daily-arxiv` (run #1 build+deploy green). `site.repo_url` set in config.
  Then, on user feedback, reworked the filter UX: **fields no longer seeded from
  config.yaml** — all four start empty so a new visitor types their own. Added **Save**
  (persists current terms to `localStorage`, this browser only) and **clear**; a
  "start from the site's topics & authors" chip fills the fields from
  `config.yaml` for editing. URL hash still auto-mirrors the view (shareable,
  reload-safe); load order hash → saved → empty. Dropped the `v=1`/`data-default`
  cleared-vs-absent machinery (no longer needed without seeding). `STORE_KEY` → `:3`.
  Blob carries `site_defaults`; `has_site_defaults` gates the button. 80 tests pass.
  Also fixed: reset/clear now `preventDefault`+`stopPropagation` so the `<details>`
  doesn't toggle, and clears the debounce.
- **2026-09-08 (latest)** — Free-form filters + broad fetch net (plan:
  `~/.claude/plans/glittery-inventing-boole.md`). **80 unit tests pass.**
  - **Rejected browser-side live arXiv queries**: `curl` with an `Origin` header shows
    neither `export.arxiv.org/api/query` nor `rss.arxiv.org` sends
    `Access-Control-Allow-Origin`, so a static page can't `fetch()` arXiv without a
    third-party CORS proxy. Whole-archive RSS (`rss.arxiv.org/rss/astro-ph`) verified
    HTTP 200 + valid channel, so broadening is config-only.
  - **`config.yaml`**: `categories` → whole archives `[astro-ph, gr-qc, hep-ph, hep-th,
    hep-ex]`; new `filter_mode: all` (keep every new/cross; keywords/authors only rank
    + seed the UI); `atlas.window_days 14→5`; new `atlas.max_window_papers: 400`,
    `site.match_chars: 800`, `site.repo_url: ""`, `site.max_papers_per_day 100→200`.
  - **`fetch_arxiv.filter_papers`**: `mode="all"|"keywords"`; the
    `matched_keywords`/`matched_authors` tags are now set on every kept paper (needed
    for scoring + the UI), gate is `mode=="all" or …`. `fetch_feed` timeout 30→60.
  - **`build_atlas.load_window_files(window, max_papers)`**: caps the corpus after the
    score sort, never dropping an `is_today` paper. `stoplist_keywords` default now
    follows `filter_mode` (on for keywords, off for all — under `all` the keywords are
    discriminative). **Retune on real broad-net data.**
  - **`generate_site._graph_nodes`**: embeds `text` (lowercased abstract truncated to
    `match_chars`), `au` (`"initial|surname;…"` from the already-normalized
    `author_keys`), `starred` (was `authors`); blob adds `corpus_categories`,
    `repo_url`; drops the config keyword/category lists (now template defaults).
  - **`templates/day.html` + `assets/filters.js` (rewrite) + `style.css`**: four
    comma-separated fields (Topics/Authors/Categories/Exclude) seeded from config via
    `value=`/`data-default=`, ★-starred-only toggle, window select (0/3/1 day), click-
    to-append suggestion chips (present categories + cluster-label terms), and an
    "unknown category" hint. Predicate: window ∧ category ∧ ¬exclude ∧ priority ∧
    (Topics/Authors empty ∨ topic-substring ∨ author-match). Category match is exact or
    whole-archive prefix. Author query gets a ~25-line JS port of
    `arxiv_text.name_key`/`_PARTICLES` (only the cheap half; LaTeX/Unicode stays in
    Python). **State design**: `v=1` marker + only-differs-from-`data-default` fields
    persisted, so "cleared Topics" ≠ "no saved state"; `STORE_KEY` bumped to `:2`
    (old `catoff`/`kwoff` bookmarks silently fall back to defaults).
  - **Volume math** (measured `2026-09-07` data): 3,216 B/paper today; uncapped
    5-archive×14-day ≈ 7 MB/page; capped (400 papers, 800-char text, 5-day window)
    ≈ 1 MB (~210 KB gz). Node JSON now ~1,250 B.
  - **Watch-item**: `render_site` re-renders every archive day with its own window — at
    ~400-paper pages × 60 days that's ~48 MB `docs/` + ~60 atlas builds per CI run.
    `docs/` is gitignored + a Pages artifact so nothing breaks; bound with a new
    `site.archive_days` if CI time creeps up.
  - **Not yet exercised on real data**: broad-net volume, `window_days: 5` atlas
    quality, `stoplist_keywords` default — all need a live announcement day
    (`2026-09-08` feeds were empty).
  Earlier this session (superseded above): first-pass in-browser filters used fixed
  checkboxes from config; the tooltip fix `9ce36c3` was correct on `position` but its
  flip/clamp still pinned the tooltip to the box edge in narrow layouts — now rewritten
  (`placeTooltip` shrinks-to-fit + flips only when the far side fits).
- **2026-09-08 (evening)** — Steps 7, 8, 9 done; 6 and 10 written but not yet
  exercised end-to-end on GitHub. `build_atlas.py` + `generate_site.py` + `build.py`
  + templates + assets (d3 vendored) + `.github/workflows/daily_arxiv.yml` + `README.md`
  all landed. **74 unit tests pass.** The live arXiv feed rolled to **2026-09-08 during
  the session — a 0-paper day** — which exercised the empty-day path for real: the site
  still renders, showing "0 papers announced today" plus the atlas over the 2-day rolling
  window (25 papers, 5 clusters). `data/raw/2026-09-08.json` (empty `papers`) committed.
  Open: browser eyeball of the page (Chrome ext declined this session), and the GitHub
  push + Pages config + first `workflow_dispatch` (all user actions).
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
- **Author false positives (found on the 2026-09-08 live run).** Chose first-initial
  matching. `authors:` entries are now either a bare surname (`Suyu`) or
  `Initial. Surname` (`L. Dai`) — surname matched exactly, initial checked only when
  given. Use the initial form for common surnames and **verify the pinned initials are
  the intended researcher**. This dropped the clear same-surname junk; author-only
  matches went 5 → 4 of the day's papers. Residual: an `Initial. Surname` spec still
  collides when two researchers share both (e.g. `H. Yu`); needs a full first name to
  disambiguate, deferred. (The maintainer's real watchlist is not committed — the
  public `config.yaml` ships a 2-entry example; see the file's comments.)
- `similarity.edge_threshold` (~0.08), `distance_threshold` (~0.92), `knn` (4),
  `min_cluster_size` — retune once the window has real depth; measured starting points
  are in `config.yaml` comments.
- `atlas.window_days: 14` — could go to 21 if clusters still feel sparse; watch page/graph
  load time as the corpus grows.
- ~~Verify the keyword stop-list actually breaks the observed 17–20 paper mega-blob~~
  **Confirmed 2026-09-08.** On the single 25-paper day: 5 clusters (max size 3 — the LZ
  exothermic/inelastic-DM triplet), 14 unclustered, 9 edges. No mega-blob. The built-in
  `_STOPWORDS` in `build_atlas.py` already also drops `model`/`mass`/`data`/`method`/`new`
  etc. Retune thresholds once the rolling window has depth.
- `dark matter` / `cosmology` keywords are broad in astro-ph.CO — `max_papers_per_day`
  may become the real limiter; scoring order matters more than the include filter.
- `CLAUDE.md` mentions `PROGRESS_glowGRF.md` in places; the file in use is this one,
  `PROGRESS.md`.
- **Cosmology coverage + spotlight (done 2026-09-08).** `config.yaml` `keywords` grew a
  cosmology block (facilities: JWST/Roman/Euclid/Rubin/LSST/DESI…; dark-energy &
  tensions: `evolving dark energy`/`w0waCDM`/`Hubble tension`…; LSS & lensing probes;
  ML-in-astro). `exclude_keywords` now drops hep-ph collider noise
  (`LHC`/`collider`/`parton …`). New `spotlight:` config block → always-on highlight
  sections above the clusters (first entry: "ML in cosmology & astro"). `max_papers_per_day`
  kept at 200 by user request — the keyword scores are what lift these papers out of the
  truncated tail. Next-level topic structure is in **Roadmap — beyond v1** below.

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
  - Suyu                             # ship an example list; the maintainer's real
  - L. Dai                           # watchlist is not committed (see config.yaml)

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
- [x] 5. `git init`, first commit, push; GitHub repo + Pages + Actions perms.
      *(2026-09-08: done. Repo **`manns01/arXivly-atlas`** (public) created via the
      GitHub API using the macOS-keychain PAT; `main` pushed; Actions workflow
      permissions → write; Pages source → GitHub Actions; `site.repo_url` set.)*
- [x] 6. GitHub Actions workflow. *(2026-09-08: `.github/workflows/daily_arxiv.yml`
      — cron `23 7 * * 1-5` + `workflow_dispatch`; `build` job (checkout, setup-python
      3.11 + pip cache, `pip install -r requirements.txt`, `python build.py`, commit
      only `data/raw/` if changed, `upload-pages-artifact docs/`); `deploy` job
      (`deploy-pages`, `needs: build`); `concurrency: daily-arxiv`. **Run via
      `workflow_dispatch` 3×, all green; site live at
      https://manns01.github.io/arXivly-atlas/.**)*
- [x] 7. `build_atlas.py` — verify clusters/edges/labels on the window; tune `knn` /
      `distance_threshold`. *(2026-09-08: implemented — `load_window` (rolling window,
      dedupe keep-earliest, `is_today` tag), hand-rolled TF-IDF (`tf·(log((N+1)/(df+1))+1)`,
      L2 rows), cosine, `mutual_knn_edges` (mutual top-k AND cosine ≥ threshold),
      `average_linkage` (Lance-Williams O(N²/merge), cut on `1−cos`, NOT graph
      components), `label_cluster` (mean-TF-IDF inside − outside, top 4). Writes
      git-ignored `data/derived/<pubdate>.json`. 0/1-paper guards return an empty atlas.
      20 new unit tests (61 total pass). Thresholds unchanged from `config.yaml`
      measured defaults — retune when the window fills.)*
- [x] 8. `templates/`, `generate_site.py`, `assets/` (CSS, `graph.js`, vendored d3).
      *(2026-09-08: `templates/{base,day,archive_index}.html` (Jinja2, autoescape),
      `assets/{style.css,graph.js,d3.v7.min.js}` (d3 7.9.0 vendored from cdnjs,
      279 KB). `generate_site.py`: `render_site()` iterates `data/raw/*.json`, builds
      the window ending at each day, writes `docs/archive/<date>.html` + newest as
      `docs/index.html` + `docs/archive/index.html`. **Deviation from plan:** asset/nav
      links are written **relative** (`""` from index, `../` from archive/) instead of
      `base_url`-absolute, so the site opens correctly from `file://` and any path;
      `site.base_url` now feeds only `<link rel="canonical">`. Atlas JSON is embedded
      via `_json_for_script` (`<`/`>`/`&` → `\uXXXX`; `<script>` is raw-text so HTML
      entities would NOT be decoded — must be literal JSON). 8 new unit tests.
      Verified structurally (25 cards, 5 clusters + Unclustered, "Last updated",
      d3 before graph.js, JSON re-parses, every local ref resolves). **Not yet
      eyeballed in a browser — Chrome extension declined this session; a local
      `python -m http.server docs/` check is still owed.**)*
- [x] 9. `build.py` orchestrator. *(2026-09-08: `python build.py` = fetch → atlas →
      generate; `--date YYYY-MM-DD` skips fetch and rebuilds from existing
      `data/raw/`. Any stage's non-zero exit stops and propagates. Wired into the
      workflow. 5 unit tests.)*
- [x] 10. `README.md`. *(2026-09-08: full config table (incl. `filter_mode`,
      window caps, `match_chars`, `repo_url`), the "Filtering: two layers" section
      + predicate, deploy steps, "how the atlas is built", extension seams.)*

**v1 shipped 2026-09-08.** All 10 build-order steps done; site live at
https://manns01.github.io/arXivly-atlas/ ; daily cron armed (`23 7 * * 1-5` UTC);
80 offline unit tests pass. Post-v1 in the same session: in-browser free-form
filters (empty-by-default + Save), broad→trimmed fetch net
(`categories: [astro-ph, gr-qc, hep-ph]`, `filter_mode: all`, `window_days: 5`,
`max_window_papers: 400`), tooltip + footer fixes. **Still to tune on a real
announcement day** (2026-09-08 feeds were empty): broad-net volume vs. the
1 MB/page budget, `window_days: 5` atlas quality, and the `stoplist_keywords`
default under `filter_mode: all`.

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

---

## Roadmap — beyond v1

Recorded 2026-09-08 from a design conversation about making cosmology (DESI / dark energy
/ Hubble tension) first-class and giving the atlas real topic structure. **Not built.**
The keyword + `spotlight:` work already shipped (see *Open items*) is the flat precursor.

### 1. Literature-generated topic *tree*

Target: a cosmologist opens the atlas and sees, generated from the window (not hand-drawn):

```
            Dark Energy
                │
     ┌──────────┼──────────┐
 Modified GR  DESI / BAO  H0 tension
     │                        │
  f(R), EFT              Supernovae, SH0ES
```

`build_atlas.average_linkage()` (`build_atlas.py:176-207`) already computes the full merge
dendrogram, then throws it away by cutting flat once at `distance_threshold: 0.92`. Keep
the tree: expose 2–3 cut levels, label each internal node by distinctive terms
(`label_cluster`), render as nested `<details>` and/or a collapsible graph.
Medium change; data model stays paper = node.
**Open question:** replace the flat cluster list on the page, or add a separate "map" view.

### 2. Research knowledge graph

Promote the fundamental object from *paper* to *research entity*. Typed nodes —
**Person, Paper, Method, Topic, Dataset** — with typed edges (`wrote`, `uses`, `studies`,
`related-to`):

```
 Person ──wrote──▶ Paper ──uses──▶ Method
                    │                 │
                 studies              ▼
                    ▼               Topic ◀──related-to──▶ Dataset
```

Needs: an entity schema; a file-based entity store (no DB, per `CLAUDE.md`); a multi-type
graph view (extend `graph.js` or a new one). Architecturally separable from #1 — the
topic tree can feed the `Topic` nodes.

### 3. Entity-extraction pass (feeds #2)

- **Deterministic first:** `Person` from arXiv metadata (already have `author_keys`);
  `Dataset` / `Method` / `Facility` from a curated gazetteer — the `config.yaml` cosmology
  keyword block is the seed list.
- **LLM extraction later:** a pass over title+abstract for entities/relations the gazetteer
  misses. This is the "easy to integrate agentic AI features later" the brief anticipates;
  must stay within "no new runtime deps / reliability first" (cache results to
  `data/derived/`, degrade to the deterministic pass if the call fails).
