# arXivly-atlas

A personal, static arXiv daily digest. One URL each morning shows the day's new
papers across your chosen categories, filtered to your topics, **grouped into
clusters of similar work and connected in a force-directed "atlas" graph** so the
day's literature is fast to scan.

- Fetches arXiv **RSS** feeds (the only source that expresses "announced today")
  for whole archives — `astro-ph`, `gr-qc`, `hep-ph`, `hep-th`, `hep-ex`.
- Builds a TF-IDF / cosine similarity atlas over a **rolling window** of
  announcement days (a single day is too small to connect).
- Renders a static site into `docs/`, published by GitHub Pages.
- A GitHub Actions cron runs it every weekday morning.
- The page has **free-form filters** — type topics, authors, categories, and
  exclusions as comma-separated text; the cards and the graph re-slice live.

Plain Python + Jinja2 + numpy + a vendored copy of d3. No database, no server, no
build framework.

> **Want a different arXiv bulletin?** Add it to `categories` in `config.yaml`
> — one line — and the next daily run picks it up. Whole archives work
> (`astro-ph`, not just `astro-ph.CO`), so anything you type into the site's
> **Categories** box that lives under a fetched archive already has data behind
> it. A static site can't fetch a feed the daily job never pulled, so a genuinely
> new archive needs that config edit.

---

## Quick start (local)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python build.py                 # fetch today -> build atlas -> render docs/
python -m http.server -d docs 8000
# open http://localhost:8000/
```

Re-render from already-fetched data without hitting the network:

```bash
python build.py --date 2026-09-07
```

Run the tests:

```bash
python -m unittest discover -s tests
```

---

## Configuration — `config.yaml`

| Key | Meaning |
|---|---|
| `categories` | arXiv feeds to fetch. Whole archives (`astro-ph`) or sub-categories (`astro-ph.CO`) — an archive supersets its sub-categories. |
| `announce_types` | Keep only these RSS announce types. Default `[new, cross]` (drops `replace` / `replace-cross`, ~44% of a feed). |
| `filter_mode` | `all` — keep every `new`/`cross` paper in `categories`; `keywords`/`authors` only rank (scoring), seed the filter UI, and feed the stop-list. `keywords` — a paper must match a keyword or a priority author to appear at all. Use `all` with a broad `categories` net. |
| `keywords` | Case-insensitive substring for `score_paper` ranking, and (under `filter_mode: keywords`) the admission filter. Also the "start from the site's topics & authors" button on the page and the TF-IDF stop-list. **Not** pre-filled into the Topics field. `gravitational lensing` matches that phrase literally, not "lensing of gravitational waves". |
| `exclude_keywords` | A paper matching one (same substring rule) is dropped at fetch time regardless of `filter_mode`. Also feeds the page's "start from" button. |
| `authors` | Priority ("★ starred") authors — a card badge and the "starred authors only" toggle, plus `author_bonus` in scoring and the "start from" button. Matched on the **LaTeX/Unicode-normalized surname, exactly** (never a substring — `Hu` ≠ "Hubble"). Two forms: bare surname (`Suyu`) matches any first name; `Initial. Surname` (`L. Dai`) also requires the first initial. Particles stay with the surname: `van der Bij`, not `Bij`. |
| `scoring` | `title_weight` · (keyword hits in title) + `abstract_weight` · (hits in abstract) + `author_bonus` · (matched priority authors). Sets card order and the window cap's keep-order. |
| `similarity.knn` | Visual graph: each node keeps its top-k neighbours; an edge is drawn only if the link is **mutual** and cosine ≥ `edge_threshold`. |
| `similarity.edge_threshold` | Minimum cosine for a drawn edge (measured max pair ≈ 0.23, median ≈ 0.03 on one day). |
| `similarity.distance_threshold` | Clusters: average-linkage agglomerative merge on `1 − cosine`, cut here (0.92 ≈ cosine 0.08). Computed **independently** of the edge graph. |
| `similarity.min_cluster_size` | Groups smaller than this (and true singletons) go to the **Unclustered** list — expect ~30% of papers. |
| `similarity.stoplist_keywords` | Add every word of every `keywords` phrase to the TF-IDF stop-list. Unset it follows `filter_mode`: on for `keywords` (they saturate that corpus), off for `all` (they're discriminative there). Set `true`/`false` to force it. |
| `similarity.method` | `tfidf` today. This is the seam for swapping in embeddings later. |
| `atlas.window_days` | How many announcement days the atlas spans. `5` for the broad net (a narrow keyword net wants ~14). Builds up from 1 on the first run. |
| `atlas.max_window_papers` | Hard cap on the window corpus (page size, clustering cost, graph size). Applied after scoring; **today's papers are never dropped** — only the older context is trimmed to the highest-scored. |
| `site.title` | Site and page title. |
| `site.base_url` | Only used for `<link rel="canonical">`. Asset/nav links are relative, so the site works from `file://`, a project page, or a user page unchanged. Set `https://<you>.github.io/arXivly-atlas` (no trailing slash), or `""` to omit canonicals. |
| `site.repo_url` | Used by the "unknown category" hint to link to your `config.yaml`. Blank → the hint shows text only. |
| `site.match_chars` | Characters of each abstract embedded in the page for the in-browser filter to match against. Lower = smaller page, shallower text search. |
| `site.max_papers_per_day` | Hard cap on papers kept for a single day, after scoring. Keep it ≥ your typical daily volume so today is never truncated. |

### Tuning

The similarity numbers are starting points measured on a single day. Retune once
the rolling window has real depth: widen `window_days` if clusters feel sparse,
raise `edge_threshold` if the graph is a hairball, adjust `distance_threshold` if
clusters are too coarse or too fragmented. The built-in English/boilerplate
stop-list lives in `build_atlas.py` (`_STOPWORDS`).

---

## Filtering: two layers

**The fetch net** (`config.yaml`, runs daily). `categories` + `filter_mode`
decide which papers exist on the site at all. A broad net (`filter_mode: all`
over whole archives) means the browser can filter to almost anything; a narrow
net can't be widened from the browser.

**The view** (the Filters panel, runs per keystroke). Four comma-separated text
fields — **Topics**, **Authors**, **Categories**, **Exclude** — that **start
empty**, plus a **★ starred authors only** toggle and a window selector. A paper
is shown when:

```
in the chosen day window
AND (Categories empty OR its category matches a typed one — exact, or a whole
     archive: "astro-ph" matches "astro-ph.*")
AND (Exclude empty OR no typed exclude term is in its title+abstract)
AND (starred-only off OR it has a starred author)
AND ( Topics and Authors both empty
      OR a typed topic is a substring of its title+abstract
      OR a typed author matches )
```

Author matching reuses arXiv's surname normalization: the paper side is
LaTeX+Unicode-normalized (`Mu\~{n}oz` → `munoz`); a typed query is only
Unicode-normalized (`Kühnel` → `kuhnel`), since you type plain text, not LaTeX.
Surname is exact, initial checked only if you give one (`L. Dai` vs `Dai`).

The URL hash always mirrors the current view, so a filtered view is
bookmarkable and survives a reload. **Save** writes your terms to `localStorage`
(this browser only) so they come back on your next visit; **clear** empties the
fields; **start from the site's topics & authors** fills them from `config.yaml`
(the `keywords` / `authors` / `categories` lists) as a starting point to edit.
On load the order is: URL hash → your saved terms → empty. With JavaScript off,
the panel stays hidden and every paper renders.

Typing a category that isn't in the current window shows a hint pointing at
`config.yaml` (with a link when `site.repo_url` is set).

---

## Deploy to GitHub Pages

1. Create a repository and push this project to `main`.
2. **Settings → Pages → Build and deployment → Source: GitHub Actions.**
3. **Settings → Actions → General → Workflow permissions: Read and write**
   (so the daily job can commit `data/raw/<date>.json` back to `main`).
4. **Actions** tab → **daily-arxiv** → **Run workflow** to trigger the first
   build manually. After that the cron in
   `.github/workflows/daily_arxiv.yml` (`23 7 * * 1-5`, UTC) runs it every
   weekday morning.

Each run: fetch → build atlas → render `docs/` → commit only the new
`data/raw/<date>.json` → publish `docs/` as the Pages artifact. If the fetch
fails, the job fails and the previously published site stays up.

`docs/` and `data/derived/` are git-ignored — `docs/` is rebuilt in CI and
published as an artifact; `data/raw/*.json` is the only tracked build output and
is treated as immutable history.

---

## How the atlas is built

`fetch_arxiv.py` → `data/raw/<pubdate>.json` (one file per announcement day):
parse the RSS feeds, dedupe by arXiv id across categories, keep `new`/`cross`,
apply the `filter_mode` filter (drop excludes; under `keywords` also require a
keyword/author hit), score, truncate to `max_papers_per_day`.

`build_atlas.py`:

1. `load_window` — newest raw file plus up to `window_days − 1` earlier ones,
   deduped by id (earliest wins), each paper tagged `is_today`, then capped to
   `atlas.max_window_papers` (every `is_today` paper kept; older ones trimmed to
   the highest-scored).
2. Hand-rolled TF-IDF over `title + abstract`: tokenize, drop the English
   stop-list (+ the configured keyword words when `stoplist_keywords` is on),
   `tf · (log((N+1)/(df+1)) + 1)`, L2-normalize. Cosine = matrix · matrixᵀ.
3. **Edges** (visual only): mutual top-k neighbours with cosine ≥ threshold.
4. **Clusters** (independent): average-linkage agglomerative partitioning on
   `1 − cosine`, cut at `distance_threshold`. Not connected components — a
   k-NN graph percolates into one giant blob.
5. `label_cluster` — the terms with the highest (mean TF-IDF inside the cluster
   − mean outside).

`generate_site.py` renders `docs/` with Jinja2: `index.html` (newest day),
`archive/<date>.html` (one per raw file, its day highlighted), `archive/index.html`.

`build.py` chains the three and propagates any non-zero exit.

### Extending

- **Better similarity:** implement an embeddings path behind
  `similarity.method`; `tfidf_matrix` / `cosine` are the only things to swap.
- **Better labels / summaries:** `label_cluster` is a single pure function — a
  call to an LLM can replace it.
- **Agentic features** (summaries, idea brainstorming, email): `data/raw/*.json`
  is immutable, dated, and complete — read it and add a step; nothing else needs
  to change.

## License

MIT — see [LICENSE](LICENSE). Copyright (c) 2026 Manish Tamta.

You are free to use, modify, and deploy this. If you run a public fork or build
something on top of it, a credit line or link back to this repo is appreciated
(the generated site keeps an attribution in its footer — please leave it in).
