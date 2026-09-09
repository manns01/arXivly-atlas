"""Render the static site into ``docs/`` from ``data/raw/*.json``.

Layout produced:
    docs/index.html            -- newest day (rendered, not a copy)
    docs/archive/<pubdate>.html -- one page per raw file, its day highlighted,
                                   atlas over the rolling window ending that day
    docs/archive/index.html     -- reverse-chronological list
    docs/assets/*               -- copied verbatim from assets/

Asset and navigation links are written **relative** to each page's location
(``""`` from ``index.html``, ``"../"`` from ``archive/*``) so the site works
both on GitHub Pages and when opened straight from disk. ``site.base_url`` is
used only for the ``<link rel="canonical">`` URL.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from build_atlas import DEFAULTS, build_atlas, load_window_files, raw_files

ASSETS_DIR = Path("assets")
TEMPLATES_DIR = Path("templates")
DOCS_DIR = Path("docs")
CONFIG_PATH = Path("config.yaml")

SNIPPET_CHARS = 320


def _json_for_script(obj) -> str:
    """Compact JSON safe to drop inside a ``<script>`` element: ``<``/``>``/``&``
    become ``\\uXXXX`` so a title can never close the tag. ``<script>`` is a raw
    text element, so HTML entities would NOT be decoded -- this must be real JSON."""
    return (
        json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
        .replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    )


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _snippet(text: str, limit: int = SNIPPET_CHARS) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut + "…"


def _decorate(papers: list[dict]) -> dict[str, dict]:
    """id -> paper dict with a display ``snippet`` added."""
    out = {}
    for p in papers:
        q = dict(p)
        q["snippet"] = _snippet(p.get("abstract", ""))
        out[p["id"]] = q
    return out


MATCH_CHARS = 800


def _spotlight_sections(config: dict, by_id: dict[str, dict]) -> list[dict]:
    """Config-defined highlight sections rendered above the auto clusters: papers
    whose title+abstract contains any of a section's ``match`` terms
    (case-insensitive substring). ``by_id`` is already in today-first / score
    order, so the filtered lists inherit it. A paper can land in several sections
    and still also appears in its normal cluster."""
    out = []
    for sec in config.get("spotlight") or []:
        terms = [str(t).lower() for t in (sec.get("match") or []) if str(t).strip()]
        if not terms:
            continue
        papers = [
            p for p in by_id.values()
            if any(t in f"{p.get('title', '')} {p.get('abstract', '')}".lower()
                   for t in terms)
        ]
        out.append({"label": sec.get("label", "Spotlight"), "papers": papers})
    return out


def _graph_nodes(atlas_nodes: list[dict], by_id: dict[str, dict],
                 pubdate: str, match_chars: int,
                 spotlight_ids: frozenset[str] = frozenset()) -> list[dict]:
    """Atlas nodes enriched with what the in-browser filters need to re-slice the
    view without a rebuild: a lowercased, truncated ``text`` (abstract) for
    substring matching, all ``categories``, the LaTeX/Unicode-normalized author
    keys as a ``"initial surname;..."`` string (``au``), the matched priority
    surnames (``starred``) + ``priority`` flag, and the day it first appeared."""
    out = []
    for n in atlas_nodes:
        p = by_id.get(n["id"], {})
        au = ";".join(f"{i}|{s}" for i, s in p.get("author_keys", []))
        out.append({
            **n,
            "text": (p.get("abstract", "") or "")[:match_chars].lower(),
            "categories": p.get("categories", []),
            "au": au,
            "keywords": p.get("matched_keywords", []),
            "starred": p.get("matched_authors", []),
            "priority": bool(p.get("matched_authors")),
            "announce_type": p.get("announce_type", ""),
            "first_pubdate": p.get("first_pubdate", pubdate),
            "spotlight": n["id"] in spotlight_ids,
        })
    return out


def _csv(values: list[str]) -> str:
    return ", ".join(values)


def _newest_first(papers: list[dict]) -> list[dict]:
    """Today's papers first, then newest arXiv id first."""
    return sorted(papers, key=lambda p: (p.get("is_today", False), p["id"]),
                  reverse=True)


def _has_astro(cluster: dict) -> bool:
    return any(
        cat.startswith("astro-ph")
        for p in cluster["papers"] for cat in p.get("categories", [])
    )


def _dominant_category(cluster: dict) -> str:
    """Most common top-level archive across a cluster's members ('astro-ph',
    'gr-qc', 'hep-ph', ...); '' when there is nothing to count."""
    tally: dict[str, int] = {}
    for p in cluster["papers"]:
        cat = (p.get("primary_category") or "").split(".")[0]
        if cat:
            tally[cat] = tally.get(cat, 0) + 1
    return max(tally, key=tally.get) if tally else ""


def _subject_buckets(clusters: list[dict], config: dict) -> list[dict] | None:
    """Group cluster dicts under the curated ``subjects:`` list.

    A cluster is filed under the FIRST subject whose ``match`` terms hit its
    distinctive-term label (case-insensitive substring); if the label misses,
    the subject whose terms hit the most member titles; still nothing -> "Other",
    or a trailing "Particle physics" bucket when ``particle_only_last`` is set and
    the cluster has no astro-ph paper.

    Returns the buckets in render order (empty ones dropped), each cluster tagged
    with an ``open`` flag, or ``None`` when ``subjects:`` is absent/empty (the
    caller then renders a flat cluster list -- the pre-subjects behaviour).
    """
    subj_cfg = config.get("subjects") or []
    if not subj_cfg:
        return None

    site = config.get("site", {})
    open_subjects = int(site.get("open_subjects", 2))
    open_clusters = int(site.get("open_clusters", 3))
    particle_last = bool(config.get("particle_only_last"))

    subjects = [
        {
            "label": s.get("label", "Subject"),
            "terms": [str(t).strip().lower() for t in (s.get("match") or []) if str(t).strip()],
            "clusters": [],
        }
        for s in subj_cfg
    ]
    other = {"label": "Other", "clusters": []}
    particle = {"label": "Particle physics", "clusters": []}

    def subject_hits(terms: list[str], label: str) -> bool:
        """A subject claims a cluster only via its distinctive-term label: a
        single-word term must be one of the label's ``/``-separated tokens; a
        multi-word term must appear verbatim. Deliberately no abstract fallback
        -- abstracts mention everything, and that floods a subject."""
        label_l = label.lower()
        tokens = set(re.split(r"[\s/_-]+", label_l))
        for t in terms:
            if (" " in t and t in label_l.replace("/", " ")) or (" " not in t and t in tokens):
                return True
        return False

    for c in clusters:
        label = c["label"] or ""
        placed = next((s for s in subjects if subject_hits(s["terms"], label)), None)
        if placed is not None:
            placed["clusters"].append(c)
        elif particle_last and not _has_astro(c):
            particle["clusters"].append(c)
        else:
            other["clusters"].append(c)

    ordered = [s for s in subjects if s["clusters"]]
    if other["clusters"]:
        ordered.append(other)
    if particle["clusters"]:
        ordered.append(particle)

    for i, s in enumerate(ordered):
        s["open"] = i < open_subjects
        s["paper_count"] = sum(len(c["papers"]) for c in s["clusters"])
        s["today_count"] = sum(c["today_count"] for c in s["clusters"])
        for j, c in enumerate(s["clusters"]):
            c["open"] = i < open_subjects and j < open_clusters
    return ordered


def _cluster_map(buckets: list[dict], atlas: dict) -> dict | None:
    """Subject-level graph for the default 'map' view: one node per bucket, sized
    by paper count, ringed by today count, coloured by dominant archive; edges
    are the paper-level atlas links aggregated by the buckets they connect.

    ``None`` when there are fewer than two buckets (caller falls back to the
    paper graph)."""
    if not buckets or len(buckets) < 2:
        return None

    cluster_subject: dict[int, str] = {}
    node_count: dict[str, int] = {}
    today_count: dict[str, int] = {}
    cat_of: dict[str, str] = {}
    for b in buckets:
        for c in b["clusters"]:
            cluster_subject[c["id"]] = b["label"]
        node_count[b["label"]] = sum(len(c["papers"]) for c in b["clusters"])
        today_count[b["label"]] = sum(c["today_count"] for c in b["clusters"])
        merged = {"papers": [p for c in b["clusters"] for p in c["papers"]]}
        cat_of[b["label"]] = _dominant_category(merged)

    paper_cluster = {n["id"]: n["cluster"] for n in atlas["nodes"]}
    pair_weight: dict[tuple[str, str], float] = {}
    for lk in atlas["links"]:
        sa = cluster_subject.get(paper_cluster.get(lk["source"], -1))
        sb = cluster_subject.get(paper_cluster.get(lk["target"], -1))
        if not sa or not sb or sa == sb:
            continue
        key = tuple(sorted((sa, sb)))
        pair_weight[key] = pair_weight.get(key, 0.0) + lk.get("weight", 0.0)

    nodes = [
        {
            "id": b["label"], "label": b["label"],
            "count": node_count[b["label"]],
            "today": today_count[b["label"]],
            "cat": cat_of[b["label"]],
        }
        for b in buckets
    ]
    links = [
        {"source": a, "target": c, "weight": round(w, 4)}
        for (a, c), w in pair_weight.items()
    ]
    return {"nodes": nodes, "links": links}


def _day_context(window: list[Path], config: dict, generated_at: str,
                 max_window: int | None = None) -> dict:
    pubdate, papers = load_window_files(window, max_window)
    atlas = build_atlas(papers, config)
    by_id = _decorate(papers)

    site = config.get("site", {})
    open_clusters = int(site.get("open_clusters", 3))

    clusters = [
        {
            "id": c["id"],
            "label": c["label"],
            "today_count": c["today_count"],
            "papers": _newest_first(
                [by_id[mid] for mid in c["members"] if mid in by_id]
            ),
        }
        for c in atlas["clusters"]
    ]
    for i, c in enumerate(clusters):        # flat-list fallback open/closed
        c["open"] = i < open_clusters
    unclustered = _newest_first(
        [by_id[mid] for mid in atlas["unclustered"] if mid in by_id]
    )
    today_count = sum(1 for p in papers if p["is_today"])

    subjects = _subject_buckets(clusters, config)
    cluster_map = _cluster_map(subjects, atlas) if subjects else None
    default_window = "all" if today_count == 0 else site.get("default_window", "today")
    graph_default = "map" if cluster_map else "papers"

    spotlight = _spotlight_sections(config, by_id)
    spotlight_ids = frozenset(p["id"] for sec in spotlight for p in sec["papers"])

    days = sorted({p.get("first_pubdate", pubdate) for p in papers}, reverse=True)

    match_chars = int(site.get("match_chars", MATCH_CHARS))
    graph_labels = int(site.get("graph_labels", 20))

    # Distinct categories actually present, most common first -> filter hints +
    # the "unknown category" check.
    cat_count: dict[str, int] = {}
    for p in papers:
        for c in p.get("categories", []):
            cat_count[c] = cat_count.get(c, 0) + 1
    suggest_categories = sorted(cat_count.items(), key=lambda kv: (-kv[1], kv[0]))
    corpus_categories = [c for c, _ in suggest_categories]

    # Distinctive cluster-label terms are literally "what's in this window".
    seen_terms: set[str] = set()
    suggest_topics: list[str] = []
    for c in atlas["clusters"]:
        for term in (c["label"] or "").split("/"):
            term = term.strip()
            if term and term not in seen_terms:
                seen_terms.add(term)
                suggest_topics.append(term)
    suggest_topics = suggest_topics[:12]

    return {
        "pubdate": pubdate,
        "generated_at": generated_at,
        "site": site,
        "window_days": len(window),
        "today_count": today_count,
        "atlas": atlas,
        "compact_cards": bool(site.get("compact_cards", True)),
        "max_authors_shown": int(site.get("max_authors_shown", 10)),
        "default_window": default_window,
        "graph_default": graph_default,
        "subjects": subjects,
        "atlas_json": _json_for_script({
            "nodes": _graph_nodes(atlas["nodes"], by_id, pubdate, match_chars,
                                  spotlight_ids),
            "links": atlas["links"],
            "map": cluster_map,
            "graph_default": graph_default,
            "graph_labels": graph_labels,
            "default_window": default_window,
            "today_count": today_count,
            "days": days,
            "corpus_categories": corpus_categories,
            "repo_url": site.get("repo_url", ""),
            # The maintainer's config set -- NOT pre-filled into the fields;
            # offered as a one-click "use site defaults".
            "site_defaults": {
                "topics": _csv(config.get("keywords", [])),
                "authors": _csv(config.get("authors", [])),
                "categories": _csv(config.get("categories", [])),
                "exclude": _csv(config.get("exclude_keywords", [])),
            },
        }),
        "clusters": clusters,
        "unclustered": unclustered,
        "spotlight": spotlight,
        "has_site_defaults": bool(config.get("keywords") or config.get("authors")),
        "suggest_categories": suggest_categories,
        "suggest_topics": suggest_topics,
        "window_dates": days,
    }


def render_site(config: dict, out_dir: Path = DOCS_DIR,
                raw_dir: Path = Path("data/raw")) -> dict:
    files = raw_files(raw_dir)
    if not files:
        raise SystemExit("no data/raw/*.json -- run fetch_arxiv.py first")

    atlas_cfg = config.get("atlas") or {}
    window_days = int(atlas_cfg.get("window_days", DEFAULTS["window_days"]))
    max_window = atlas_cfg.get("max_window_papers", DEFAULTS["max_window_papers"])
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    env = _env()
    day_tpl = env.get_template("day.html")
    archive_tpl = env.get_template("archive_index.html")

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "archive").mkdir(exist_ok=True)
    assets_out = out_dir / "assets"
    if assets_out.exists():
        shutil.rmtree(assets_out)
    shutil.copytree(ASSETS_DIR, assets_out)

    days_meta = []
    for i, _ in enumerate(files):
        window = files[max(0, i + 1 - window_days): i + 1]
        ctx = _day_context(window, config, generated_at, max_window)

        archive_html = day_tpl.render(
            rel="../", canonical=f"/archive/{ctx['pubdate']}.html", **ctx)
        (out_dir / "archive" / f"{ctx['pubdate']}.html").write_text(archive_html)

        days_meta.append({
            "pubdate": ctx["pubdate"],
            "today_count": ctx["today_count"],
            "cluster_count": len(ctx["atlas"]["clusters"]),
        })

        if i == len(files) - 1:  # newest -> also the landing page
            index_html = day_tpl.render(rel="", canonical="/index.html", **ctx)
            (out_dir / "index.html").write_text(index_html)

    archive_index_html = archive_tpl.render(
        rel="../", canonical="/archive/index.html",
        site=config.get("site", {}), generated_at=generated_at,
        days=list(reversed(days_meta)),
    )
    (out_dir / "archive" / "index.html").write_text(archive_index_html)

    return {"days": len(days_meta), "newest": days_meta[-1]["pubdate"]}


def _load_config() -> dict:
    import yaml

    with open(CONFIG_PATH) as fh:
        return yaml.safe_load(fh) or {}


def main(argv: list[str] | None = None) -> int:
    result = render_site(_load_config())
    print(f"rendered {result['days']} day page(s) into {DOCS_DIR}/ "
          f"(index = {result['newest']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
