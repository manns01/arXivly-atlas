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


def _day_context(window: list[Path], config: dict, generated_at: str) -> dict:
    pubdate, papers = load_window_files(window)
    atlas = build_atlas(papers, config)
    by_id = _decorate(papers)

    clusters = [
        {
            "label": c["label"],
            "today_count": c["today_count"],
            "papers": [by_id[mid] for mid in c["members"] if mid in by_id],
        }
        for c in atlas["clusters"]
    ]
    unclustered = [by_id[mid] for mid in atlas["unclustered"] if mid in by_id]
    today_count = sum(1 for p in papers if p["is_today"])

    return {
        "pubdate": pubdate,
        "generated_at": generated_at,
        "site": config.get("site", {}),
        "window_days": len(window),
        "today_count": today_count,
        "atlas": atlas,
        "atlas_json": _json_for_script({
            "nodes": atlas["nodes"], "links": atlas["links"],
        }),
        "clusters": clusters,
        "unclustered": unclustered,
    }


def render_site(config: dict, out_dir: Path = DOCS_DIR,
                raw_dir: Path = Path("data/raw")) -> dict:
    files = raw_files(raw_dir)
    if not files:
        raise SystemExit("no data/raw/*.json -- run fetch_arxiv.py first")

    window_days = int((config.get("atlas") or {}).get(
        "window_days", DEFAULTS["window_days"]))
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
        ctx = _day_context(window, config, generated_at)

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
