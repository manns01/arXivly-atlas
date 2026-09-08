"""Build the "atlas" for a rolling window of announcement days: a TF-IDF /
cosine similarity graph over the window's papers, with visual edges (mutual
k-NN) and clusters (average-linkage agglomerative) computed *independently*,
plus a distinctive-term label per cluster.

All numpy, no scikit-learn / networkx / scipy. The corpus is a few hundred
short documents, so dense matrices are fine and everything runs in well under a
second.

Public surface used by generate_site.py / build.py:
    load_window(raw_dir, window_days)   -> (pubdate, papers)   # papers carry is_today
    build_atlas(papers, config)         -> atlas dict
    main()                              -> writes data/derived/<pubdate>.json
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np

RAW_DIR = Path("data/raw")
DERIVED_DIR = Path("data/derived")
CONFIG_PATH = Path("config.yaml")

# Measured starting points (2026-09-07 planning run); overridable via config.yaml.
DEFAULTS = {
    "knn": 4,
    "edge_threshold": 0.08,
    "distance_threshold": 0.92,
    "min_cluster_size": 2,
    "stoplist_keywords": True,
    "window_days": 14,
}

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9-]*")

# Deliberately small: generic English + arXiv-abstract boilerplate. Domain
# stop-words come from the configured keywords (see stoplist_keywords).
_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if", "then", "of", "to", "in", "on",
    "for", "with", "as", "by", "at", "from", "into", "is", "are", "was", "were",
    "be", "been", "being", "this", "that", "these", "those", "it", "its", "we",
    "our", "us", "which", "who", "whom", "whose", "such", "can", "may", "also",
    "not", "no", "than", "so", "both", "all", "any", "each", "more", "most",
    "other", "some", "only", "new", "using", "used", "use", "based", "show",
    "shown", "shows", "results", "result", "study", "studies", "paper", "here",
    "present", "presented", "propose", "proposed", "approach", "however",
    "within", "between", "over", "under", "up", "down", "out", "about", "via",
    "one", "two", "three", "first", "second", "given", "find", "found", "well",
    "provide", "provides", "provided", "consider", "considered", "obtain",
    "obtained", "case", "cases", "model", "models", "data", "method", "methods",
}


# --- window loading ---------------------------------------------------------

def raw_files(raw_dir: Path = RAW_DIR) -> list[Path]:
    """All non-empty ``data/raw/*.json`` paths, oldest name first."""
    return sorted(p for p in Path(raw_dir).glob("*.json") if p.stat().st_size > 0)


def load_window_files(window: list[Path]) -> tuple[str, list[dict]]:
    """Dedupe papers across an explicit, chronologically ordered list of raw
    files (keep the earliest appearance), tag each ``is_today`` if it is in the
    last file, and return ``(pubdate_of_last_file, papers)``.

    ``([])`` in -> ``("", [])`` out.
    """
    if not window:
        return "", []
    newest = window[-1]
    today_pubdate = json.loads(newest.read_text()).get("pubdate", newest.stem)
    today_ids: set[str] = set()
    seen: dict[str, dict] = {}
    for fp in window:  # oldest -> newest, so the first occurrence wins
        day = json.loads(fp.read_text())
        pubdate = day.get("pubdate", fp.stem)
        for paper in day.get("papers", []):
            if fp == newest:
                today_ids.add(paper["id"])
            seen.setdefault(paper["id"], {**paper, "first_pubdate": pubdate})

    papers = list(seen.values())
    for paper in papers:
        paper["is_today"] = paper["id"] in today_ids
    # Today's papers first, then by score, then id -- stable, deterministic order.
    papers.sort(key=lambda p: (not p["is_today"], -p.get("score", 0), p["id"]))
    return today_pubdate, papers


def load_window(raw_dir: Path = RAW_DIR, window_days: int = DEFAULTS["window_days"]
                ) -> tuple[str, list[dict]]:
    """Load the newest ``data/raw/*.json`` plus up to ``window_days - 1`` earlier
    files. See :func:`load_window_files`."""
    return load_window_files(raw_files(raw_dir)[-window_days:])


# --- TF-IDF ----------------------------------------------------------------

def _keyword_stopwords(keywords: list[str]) -> set[str]:
    """Every token appearing in a configured keyword phrase -- these match most
    of the corpus and carry no discriminative signal."""
    out: set[str] = set()
    for kw in keywords:
        out.update(_TOKEN_RE.findall(kw.lower()))
    return out


def tokenize(text: str, extra_stop: set[str]) -> list[str]:
    return [
        t for t in _TOKEN_RE.findall(text.lower())
        if len(t) > 1 and t not in _STOPWORDS and t not in extra_stop
    ]


def tfidf_matrix(docs: list[list[str]]) -> tuple[np.ndarray, list[str]]:
    """L2-normalized TF-IDF, ``tf * (log((N+1)/(df+1)) + 1)``. Returns
    ``(matrix [n_docs x n_terms], vocab)``. Empty vocab -> ``(zeros(n,0), [])``."""
    n = len(docs)
    vocab_set: set[str] = set()
    for d in docs:
        vocab_set.update(d)
    vocab = sorted(vocab_set)
    if not vocab:
        return np.zeros((n, 0)), []
    index = {t: i for i, t in enumerate(vocab)}

    tf = np.zeros((n, len(vocab)))
    for i, d in enumerate(docs):
        for t in d:
            tf[i, index[t]] += 1.0
    df = (tf > 0).sum(axis=0)
    idf = np.log((n + 1) / (df + 1)) + 1.0
    m = tf * idf
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return m / norms, vocab


# --- edges (mutual k-NN) + clusters (agglomerative) -----------------------

def mutual_knn_edges(cos: np.ndarray, k: int, threshold: float) -> list[tuple[int, int, float]]:
    """Undirected edges: ``j`` is in ``i``'s top-``k`` AND ``i`` is in ``j``'s
    top-``k`` AND ``cos[i, j] >= threshold``."""
    n = cos.shape[0]
    if n < 2:
        return []
    c = cos.copy()
    np.fill_diagonal(c, -1.0)
    knn = np.argsort(-c, axis=1)[:, :k]
    nbr = [set(row.tolist()) for row in knn]
    edges = []
    for i in range(n):
        for j in nbr[i]:
            if j > i and i in nbr[j] and cos[i, j] >= threshold:
                edges.append((i, j, float(cos[i, j])))
    return edges


def average_linkage(dist: np.ndarray, threshold: float) -> list[list[int]]:
    """Agglomerative average-linkage partition: repeatedly merge the two closest
    active clusters while their distance ``<= threshold`` (Lance-Williams
    update). Returns a list of member-index lists covering every row."""
    n = dist.shape[0]
    if n == 0:
        return []
    if n == 1:
        return [[0]]
    D = dist.astype(float).copy()
    np.fill_diagonal(D, np.inf)
    members: dict[int, list[int]] = {i: [i] for i in range(n)}
    sizes = np.ones(n)
    active = np.ones(n, dtype=bool)

    while active.sum() > 1:
        masked = np.where(active[:, None] & active[None, :], D, np.inf)
        a, b = np.unravel_index(np.argmin(masked), D.shape)
        if masked[a, b] > threshold:
            break
        na, nb = sizes[a], sizes[b]
        new = (na * D[a, :] + nb * D[b, :]) / (na + nb)
        D[a, :] = new
        D[:, a] = new
        D[a, a] = np.inf
        sizes[a] = na + nb
        members[a].extend(members.pop(b))
        active[b] = False
        D[b, :] = np.inf
        D[:, b] = np.inf

    return list(members.values())


def label_cluster(member_idx: list[int], tfidf: np.ndarray, vocab: list[str],
                  k: int = 4) -> str:
    """Top ``k`` terms ranked by (mean TF-IDF inside the cluster) minus (mean
    TF-IDF outside). ``"a/b/c"``; ``""`` if nothing is distinctive or vocab is
    empty."""
    if not vocab or not member_idx:
        return ""
    inside = tfidf[member_idx].mean(axis=0)
    mask = np.ones(tfidf.shape[0], dtype=bool)
    mask[member_idx] = False
    outside = tfidf[mask].mean(axis=0) if mask.any() else np.zeros_like(inside)
    contrast = inside - outside
    order = np.argsort(-contrast)
    return "/".join(vocab[i] for i in order[:k] if contrast[i] > 0)


# --- assembly ------------------------------------------------------------

def _empty_atlas(pubdate: str, papers: list[dict]) -> dict:
    return {
        "pubdate": pubdate,
        "window_size": len(papers),
        "nodes": [
            {
                "id": p["id"], "title": p["title"],
                "primary_category": p.get("primary_category", ""),
                "score": p.get("score", 0),
                "is_today": p.get("is_today", True),
                "cluster": -1,
            }
            for p in papers
        ],
        "links": [],
        "clusters": [],
        "unclustered": [p["id"] for p in papers],
    }


def build_atlas(papers: list[dict], config: dict) -> dict:
    """Full atlas for the window. Safe on 0 / 1 paper (no edges, no clusters)."""
    sim = {**DEFAULTS, **(config.get("similarity") or {})}
    pubdate = papers[0]["first_pubdate"] if papers else ""

    if len(papers) < 2:
        return _empty_atlas(pubdate, papers)

    extra_stop = (
        _keyword_stopwords(config.get("keywords") or [])
        if sim.get("stoplist_keywords", True) else set()
    )
    docs = [tokenize(f"{p['title']} {p.get('abstract', '')}", extra_stop) for p in papers]
    tfidf, vocab = tfidf_matrix(docs)

    if not vocab:
        return _empty_atlas(pubdate, papers)

    cos = tfidf @ tfidf.T
    np.clip(cos, -1.0, 1.0, out=cos)

    edges = mutual_knn_edges(cos, int(sim["knn"]), float(sim["edge_threshold"]))
    raw_clusters = average_linkage(1.0 - cos, float(sim["distance_threshold"]))

    min_size = int(sim["min_cluster_size"])
    cluster_of = [-1] * len(papers)
    clusters_out: list[dict] = []
    unclustered: list[int] = []
    for group in sorted(raw_clusters, key=len, reverse=True):
        if len(group) < max(2, min_size):
            unclustered.extend(group)
            continue
        cid = len(clusters_out)
        for i in group:
            cluster_of[i] = cid
        members = [papers[i]["id"] for i in group]
        clusters_out.append({
            "id": cid,
            "label": label_cluster(group, tfidf, vocab),
            "members": members,
            "size": len(group),
            "today_count": sum(papers[i]["is_today"] for i in group),
        })

    nodes = [
        {
            "id": p["id"], "title": p["title"],
            "primary_category": p.get("primary_category", ""),
            "score": p.get("score", 0),
            "is_today": p["is_today"],
            "cluster": cluster_of[i],
        }
        for i, p in enumerate(papers)
    ]
    links = [
        {"source": papers[i]["id"], "target": papers[j]["id"], "weight": round(w, 4)}
        for i, j, w in edges
    ]
    return {
        "pubdate": pubdate,
        "window_size": len(papers),
        "nodes": nodes,
        "links": links,
        "clusters": clusters_out,
        "unclustered": [papers[i]["id"] for i in sorted(unclustered)],
    }


# --- entrypoint --------------------------------------------------------------

def _load_config() -> dict:
    import yaml

    with open(CONFIG_PATH) as fh:
        return yaml.safe_load(fh) or {}


def main(argv: list[str] | None = None) -> int:
    config = _load_config()
    window_days = int((config.get("atlas") or {}).get("window_days", DEFAULTS["window_days"]))
    pubdate, papers = load_window(RAW_DIR, window_days)
    if not pubdate:
        print("no data/raw/*.json files -- run fetch_arxiv.py first", file=sys.stderr)
        return 1

    atlas = build_atlas(papers, config)
    DERIVED_DIR.mkdir(parents=True, exist_ok=True)
    out = DERIVED_DIR / f"{pubdate}.json"
    out.write_text(json.dumps(atlas, indent=2, ensure_ascii=False) + "\n")
    print(
        f"wrote {out}: {atlas['window_size']} papers, "
        f"{len(atlas['clusters'])} clusters, {len(atlas['links'])} edges, "
        f"{len(atlas['unclustered'])} unclustered"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
