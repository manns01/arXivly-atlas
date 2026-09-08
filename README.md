# arXivly-atlas

A personal, static arXiv daily digest. One URL each morning shows the day's new
papers across your chosen categories, filtered to your topics, **grouped into
clusters of similar work and connected in a force-directed "atlas" graph** so the
day's literature is fast to scan.

- Fetches the per-category arXiv **RSS** feeds (the only source that expresses
  "announced today").
- Filters by keyword substrings and priority authors.
- Builds a TF-IDF / cosine similarity atlas over a **rolling window** of
  announcement days (a single day is too small to connect).
- Renders a static site into `docs/`, published by GitHub Pages.
- A GitHub Actions cron runs it every weekday morning.

Plain Python + Jinja2 + numpy + a vendored copy of d3. No database, no server, no
build framework.

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
| `categories` | arXiv categories to fetch, e.g. `astro-ph.CO`, `gr-qc`. |
| `announce_types` | Keep only these RSS announce types. Default `[new, cross]` (drops `replace` / `replace-cross`, ~44% of a feed). |
| `keywords` | A paper is kept if **any** of these is a **case-insensitive substring** of its title or abstract. `gravitational lensing` matches "gravitational lensing" but not "lensing of gravitational waves" — add the variants you want. Empty `keywords` **and** empty `authors` keeps everything. |
| `exclude_keywords` | If any matches (same substring rule), the paper is dropped even if a keyword or author matched. |
| `authors` | Priority authors. Matched on the **LaTeX/Unicode-normalized surname, exactly** (never a substring — `Hu` will not match "Hubble"). Two forms: a bare surname (`Suyu`) matches any first name; `Initial. Surname` (`L. Dai`, `Wayne Hu`) also requires the first initial to match — use this for common surnames. Particles stay with the surname: write `van der Bij`, not `Bij`. |
| `scoring` | `title_weight` · (keyword hits in title) + `abstract_weight` · (hits in abstract) + `author_bonus` · (matched priority authors). Sets the card order and the truncation cutoff. |
| `similarity.knn` | Visual graph: each node keeps its top-k neighbours; an edge is drawn only if the link is **mutual** and cosine ≥ `edge_threshold`. |
| `similarity.edge_threshold` | Minimum cosine for a drawn edge (measured max pair ≈ 0.23, median ≈ 0.03 on one day). |
| `similarity.distance_threshold` | Clusters: average-linkage agglomerative merge on `1 − cosine`, cut here (0.92 ≈ cosine 0.08). Computed **independently** of the edge graph. |
| `similarity.min_cluster_size` | Groups smaller than this (and true singletons) go to the **Unclustered** list — expect ~30% of papers. |
| `similarity.stoplist_keywords` | Add every word of every `keywords` phrase to the TF-IDF stop-list. Keep this **on**: the filter terms match nearly every paper and otherwise fuse the whole corpus into one cluster. |
| `similarity.method` | `tfidf` today. This is the seam for swapping in embeddings later. |
| `atlas.window_days` | How many announcement days the atlas spans. Default 14. Builds up from 1 on the first run. |
| `site.title` | Site and page title. |
| `site.base_url` | Only used for `<link rel="canonical">`. Asset and nav links are relative, so the site works from `file://`, a project page, or a user page unchanged. Set it to `https://<you>.github.io/arXivly-atlas` (no trailing slash) for correct canonical URLs, or `""` to omit them. |
| `site.max_papers_per_day` | Hard cap on papers kept for a day, after scoring. |

### Tuning

The similarity numbers are starting points measured on a single day. Retune once
the rolling window has real depth: widen `window_days` if clusters feel sparse,
raise `edge_threshold` if the graph is a hairball, adjust `distance_threshold` if
clusters are too coarse or too fragmented. The built-in English/boilerplate
stop-list lives in `build_atlas.py` (`_STOPWORDS`).

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
apply the keyword + author filter, score, truncate.

`build_atlas.py`:

1. `load_window` — newest raw file plus up to `window_days − 1` earlier ones,
   deduped by id (earliest wins), each paper tagged `is_today`.
2. Hand-rolled TF-IDF over `title + abstract`: tokenize, drop the English
   stop-list + every configured keyword word, `tf · (log((N+1)/(df+1)) + 1)`,
   L2-normalize. Cosine = matrix · matrixᵀ.
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
