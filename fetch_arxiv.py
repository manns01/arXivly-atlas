"""Fetch today's arXiv announcements from the per-category RSS feeds, filter to
the configured topics/authors, dedupe across categories, score, and write
``data/raw/<pubdate>.json``.

Design: everything except :func:`fetch_feed` and :func:`main` is a pure function
so the parse/filter/dedupe/score pipeline is unit-tested offline against saved
fixtures in ``tests/fixtures/``.

Why RSS and not the arXiv API: the API's ``published`` date lags the
announcement day by several days; only the RSS feed expresses "announced today"
(via the channel ``pubDate`` and per-item ``Announce Type``).
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import feedparser

from arxiv_text import (
    arxiv_id,
    author_spec_key,
    author_spec_matches,
    clean_abstract,
    name_keys_from_creator,
    normalize_text,
    surnames_from_creator,
)

SCHEMA_VERSION = 2
FEED_URL = "https://rss.arxiv.org/rss/{cat}"
RAW_DIR = Path("data/raw")
CONFIG_PATH = Path("config.yaml")

_USER_AGENT = "arXivly-atlas/0.1 (+https://github.com/; personal arXiv digest)"


# --- network ---------------------------------------------------------------

def fetch_feed(cat: str, *, retries: int = 2, backoff: float = 2.0,
               timeout: int = 30) -> bytes:
    """GET one category feed, retrying on transport/HTTP errors. Raises on
    final failure so the caller can fail closed (write nothing)."""
    import requests

    url = FEED_URL.format(cat=cat)
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, timeout=timeout,
                             headers={"User-Agent": _USER_AGENT})
            r.raise_for_status()
            if not r.content.strip():
                raise ValueError(f"empty feed body for {cat}")
            return r.content
        except Exception as e:  # noqa: BLE001 - retried, then re-raised
            last_err = e
            if attempt < retries:
                time.sleep(backoff * (attempt + 1))
    raise RuntimeError(f"failed to fetch {cat} after {retries + 1} tries: {last_err}")


# --- parsing -------------------------------------------------------------------

def channel_pubdate(parsed: feedparser.FeedParserDict) -> str:
    """Announcement day as ``YYYY-MM-DD`` from the channel ``pubDate``.

    Uses the date in the feed's own UTC offset (arXiv Eastern), never
    ``datetime.today()`` -- the run may cross midnight relative to the feed.
    """
    raw = parsed.feed.get("published") or parsed.feed.get("updated")
    if not raw:
        raise ValueError("feed has no channel pubDate")
    return parsedate_to_datetime(raw).date().isoformat()


def parse_feed(raw: bytes, source_category: str) -> tuple[str, list[dict]]:
    """(pubdate, items) for one category feed. ``items`` keeps every announce
    type; filtering by type happens in :func:`merge_feeds`."""
    parsed = feedparser.parse(raw)
    pubdate = channel_pubdate(parsed)
    items: list[dict] = []
    for e in parsed.entries:
        aid = arxiv_id(e.get("id") or e.get("link", ""))
        if not aid:
            continue
        creator = e.get("author", "") or ""
        cats = [t.get("term") for t in e.get("tags", []) if t.get("term")]
        items.append({
            "id": aid,
            "title": normalize_text(e.get("title", "")),
            "abstract": clean_abstract(e.get("summary", "")),
            "authors": [normalize_text(a) for a in creator.split(",") if a.strip()],
            "surnames": surnames_from_creator(creator),
            "author_keys": name_keys_from_creator(creator),
            "categories": cats,
            "primary_category": cats[0] if cats else source_category,
            "announce_type": (e.get("arxiv_announce_type") or "").strip().lower(),
            "link": e.get("link", f"https://arxiv.org/abs/{aid}"),
            "pdf": f"https://arxiv.org/pdf/{aid}",
            "_source_categories": {source_category},
        })
    return pubdate, items


def merge_feeds(parsed_feeds: list[tuple[str, list[dict]]],
                configured_categories: list[str],
                announce_types: list[str]) -> tuple[str, list[dict]]:
    """Dedupe items by arXiv id across category feeds, union their category
    lists, and keep only the wanted announce types.

    A paper announced ``new`` in its primary feed but seen as ``cross`` in
    another is kept once as ``new``.
    """
    pubdates = {pd for pd, _ in parsed_feeds if pd}
    if len(pubdates) > 1:
        # Different feeds rebuilt across a boundary -- take the newest.
        pubdate = max(pubdates)
    else:
        pubdate = next(iter(pubdates), "")

    allowed = set(announce_types)
    cfg = set(configured_categories)
    by_id: dict[str, dict] = {}
    for _, items in parsed_feeds:
        for it in items:
            cur = by_id.get(it["id"])
            if cur is None:
                by_id[it["id"]] = {**it, "_source_categories": set(it["_source_categories"])}
                continue
            cur["_source_categories"] |= it["_source_categories"]
            cur["categories"] = sorted(set(cur["categories"]) | set(it["categories"]))
            if it["announce_type"] == "new":
                cur["announce_type"] = "new"

    out = []
    for it in by_id.values():
        if it["announce_type"] not in allowed:
            continue
        it["matched_categories"] = sorted(it["_source_categories"] & cfg)
        del it["_source_categories"]
        out.append(it)
    return pubdate, out


# --- filter + score ----------------------------------------------------------

def _kw_hits(text: str, keywords: list[str]) -> list[str]:
    low = text.lower()
    return [k for k in keywords if k.lower() in low]


def filter_papers(items: list[dict], *, keywords: list[str],
                  exclude_keywords: list[str],
                  author_surnames: list[str]) -> list[dict]:
    """Keep a paper if any keyword is a substring of title+abstract
    (case-insensitive) OR any configured author spec matches one of its authors;
    drop it if any exclude keyword matches. Empty keywords AND empty authors ->
    keep all (still honouring excludes).

    An ``authors:`` entry is either a bare surname (``Suyu`` -- any first name) or
    ``Initial. Surname`` / ``Firstname Surname`` (``L. Dai`` -- first initial must
    also match), disambiguating common surnames.
    """
    author_specs = [(s, author_spec_key(s)) for s in author_surnames if s.strip()]
    keep_all = not keywords and not author_specs
    kept = []
    for it in items:
        haystack = f"{it['title']} {it['abstract']}"
        if exclude_keywords and _kw_hits(haystack, exclude_keywords):
            continue
        matched_kw = _kw_hits(haystack, keywords)
        matched_auth = sorted({
            key[1] for _, key in author_specs
            if author_spec_matches(it["author_keys"], key)
        })
        if keep_all or matched_kw or matched_auth:
            it["matched_keywords"] = matched_kw
            it["matched_authors"] = matched_auth
            kept.append(it)
    return kept


def score_paper(item: dict, *, keywords: list[str], scoring: dict) -> float:
    title_hits = len(_kw_hits(item["title"], keywords))
    abstract_hits = len(_kw_hits(item["abstract"], keywords))
    return (
        scoring.get("title_weight", 3) * title_hits
        + scoring.get("abstract_weight", 1) * abstract_hits
        + scoring.get("author_bonus", 5) * len(item.get("matched_authors", []))
    )


def build_day(parsed_feeds: list[tuple[str, list[dict]]], config: dict) -> dict:
    """Full pipeline: merge -> filter -> score -> sort -> truncate."""
    site = config.get("site", {})
    pubdate, merged = merge_feeds(
        parsed_feeds,
        config.get("categories", []),
        config.get("announce_types", ["new", "cross"]),
    )
    kept = filter_papers(
        merged,
        keywords=config.get("keywords", []),
        exclude_keywords=config.get("exclude_keywords", []),
        author_surnames=config.get("authors", []),
    )
    scoring = config.get("scoring", {})
    for it in kept:
        it["score"] = score_paper(it, keywords=config.get("keywords", []), scoring=scoring)
    kept.sort(key=lambda it: (-it["score"], it["id"]))
    max_papers = site.get("max_papers_per_day", 100)
    kept = kept[:max_papers]
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pubdate": pubdate,
        "categories": config.get("categories", []),
        "papers": kept,
    }


# --- entrypoint --------------------------------------------------------------

def _load_config() -> dict:
    import yaml

    with open(CONFIG_PATH) as fh:
        return yaml.safe_load(fh) or {}


def main(argv: list[str] | None = None) -> int:
    config = _load_config()
    categories = config.get("categories", [])
    if not categories:
        print("config.yaml has no categories", file=sys.stderr)
        return 1

    parsed_feeds = []
    for cat in categories:
        try:
            raw = fetch_feed(cat)
        except Exception as e:  # noqa: BLE001
            print(f"ERROR fetching {cat}: {e}", file=sys.stderr)
            print("failing closed -- nothing written, previous site kept", file=sys.stderr)
            return 1
        parsed_feeds.append(parse_feed(raw, cat))

    day = build_day(parsed_feeds, config)
    pubdate = day["pubdate"]
    if not pubdate:
        print("could not determine announcement date from feeds", file=sys.stderr)
        return 1

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RAW_DIR / f"{pubdate}.json"
    if out_path.exists() and out_path.stat().st_size > 0:
        print(f"{out_path} already built ({len(day['papers'])} papers today) -- exit 0")
        return 0

    out_path.write_text(json.dumps(day, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {out_path}: {len(day['papers'])} papers for {pubdate}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
