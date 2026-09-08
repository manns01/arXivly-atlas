"""Shared text utilities for arXivly-atlas.

Pure functions, no I/O. Used by fetch_arxiv.py (author matching, abstract
cleanup) and later by build_atlas.py / generate_site.py.

Covers:
  - LaTeX escape + Unicode -> ASCII normalization (author names, keyword text)
  - surname extraction from an arXiv ``dc:creator`` string
  - arXiv id extraction from a feed entry id or abs URL
  - stripping arXiv's "Announce Type / Abstract:" preamble off an RSS summary
"""

from __future__ import annotations

import re
import unicodedata

# --- LaTeX -> ASCII -----------------------------------------------------------

# Multi-character LaTeX control words for letters that have no combining-mark
# decomposition (so NFKD can't help). Longest keys first when applied.
_LATEX_LETTERS = {
    r"\ss": "ss", r"\SS": "SS",
    r"\ae": "ae", r"\AE": "AE",
    r"\oe": "oe", r"\OE": "OE",
    r"\aa": "a", r"\AA": "A",
    r"\dh": "d", r"\DH": "D",
    r"\th": "th", r"\TH": "TH",
    r"\ng": "ng", r"\NG": "NG",
    r"\o": "o", r"\O": "O",
    r"\l": "l", r"\L": "L",
    r"\i": "i", r"\j": "j",
}

# Accent control chars/words that take one letter as argument. We just drop the
# accent and keep the base letter; NFKD afterwards mops up any real combining
# marks that slipped through as literal Unicode.
_ACCENT_SYMBOLS = "\"'`^~=."      # \"o  \'e  \`a  \^i  \~n  \=o  \.z
_ACCENT_WORDS = "uvHtcdbrk"       # \u \v \H \t \c \d \b \r \k  (+ argument)

_re_accent_braced = re.compile(
    r"\\([" + re.escape(_ACCENT_SYMBOLS) + _ACCENT_WORDS + r"])\s*\{\\?([A-Za-z])\}"
)
_re_accent_word_sp = re.compile(r"\\([" + _ACCENT_WORDS + r"])\s+\\?([A-Za-z])")
_re_accent_sym = re.compile(r"\\([" + re.escape(_ACCENT_SYMBOLS) + r"])\s*\\?([A-Za-z])")
_re_leftover_cmd = re.compile(r"\\[A-Za-z]+")
_re_braces = re.compile(r"[{}]")
_re_ws = re.compile(r"\s+")


def _strip_latex(s: str) -> str:
    for _ in range(3):  # a few passes catch nested forms like {\"{o}}
        prev = s
        s = _re_accent_braced.sub(r"\2", s)
        s = _re_accent_word_sp.sub(r"\2", s)
        s = _re_accent_sym.sub(r"\2", s)
        if s == prev:
            break
    for key in sorted(_LATEX_LETTERS, key=len, reverse=True):
        # ``\o rensen`` -> ``orensen``: a control word eats one following space.
        s = re.sub(re.escape(key) + r"(?![A-Za-z]) ?", _LATEX_LETTERS[key], s)
    s = _re_leftover_cmd.sub("", s)     # unknown \command -> drop
    s = _re_braces.sub("", s)
    s = s.replace("\\", "")
    return s


def normalize_text(s: str) -> str:
    """LaTeX escapes + Unicode accents -> plain ASCII, whitespace-collapsed.

    ``Mu\\~{n}oz`` -> ``Munoz``,  ``Hlo\\v{z}ek`` -> ``Hlozek``,
    ``K\\"uhnel`` / ``Kühnel`` -> ``Kuhnel``.
    """
    if not s:
        return ""
    s = _strip_latex(s)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.encode("ascii", "ignore").decode("ascii")
    return _re_ws.sub(" ", s).strip()


# --- surnames ---------------------------------------------------------------

# Lowercase name particles that belong with the surname that follows them.
_PARTICLES = {
    "de", "del", "della", "der", "den", "van", "von", "di", "da", "dos",
    "das", "la", "le", "el", "al", "bin", "ibn", "ter", "ten", "st",
}


def _split_name(name: str) -> tuple[list[str], list[str]]:
    """(given_tokens, surname_tokens) for one author name, ASCII-normalized.

    Handles ``Last, First`` ordering; trailing lowercase particles fold into the
    surname (``van der Bij`` -> surname ``["van", "der", "bij"]``).
    """
    if "," in name:  # "Last, First"
        last, _, first = name.partition(",")
        given = [t for t in normalize_text(first).split(" ") if t]
        surn = [t for t in normalize_text(last).split(" ") if t]
        return given, [t.lower() for t in surn]
    parts = [t for t in normalize_text(name).split(" ") if t]
    if not parts:
        return [], []
    surn = [parts[-1]]
    i = len(parts) - 2
    while i >= 0 and parts[i].lower() in _PARTICLES:
        surn.insert(0, parts[i])
        i -= 1
    return parts[: i + 1], [t.lower() for t in surn]


def surname_of(name: str) -> str:
    """Lowercase ASCII surname from a single author name (``First M. Last``).

    Trailing particles are folded in (``van der Bij`` -> ``van der bij``) so a
    configured ``Bij`` still needs to be written as ``van der Bij`` to match --
    exact surname comparison, never a substring.
    """
    return " ".join(_split_name(name)[1])


def name_key(name: str) -> tuple[str, str]:
    """``(first_initial, surname)`` for one author name, lowercased ASCII.

    ``"Nikko John Leo S. Lobos"`` -> ``("n", "lobos")``,
    ``"C. Megan Urry"`` -> ``("c", "urry")``,
    ``"Einstein, Albert"`` -> ``("a", "einstein")``.
    The initial is ``""`` when no given name is present.
    """
    given, surn = _split_name(name)
    if not surn:
        return "", ""
    initial = given[0][0].lower() if given and given[0] else ""
    return initial, " ".join(surn)


def surnames_from_creator(creator: str) -> list[str]:
    """Comma-separated ``dc:creator`` string -> list of lowercase surnames."""
    if not creator:
        return []
    return [s for s in (surname_of(part) for part in creator.split(",")) if s]


def name_keys_from_creator(creator: str) -> list[list[str]]:
    """``dc:creator`` string -> ``[[initial, surname], ...]`` (empty surnames dropped)."""
    if not creator:
        return []
    out = []
    for part in creator.split(","):
        initial, surname = name_key(part)
        if surname:
            out.append([initial, surname])
    return out


def author_spec_key(spec: str) -> tuple[str, str]:
    """Parse a configured ``authors:`` entry into ``(first_initial, surname)``.

    ``"Hu"`` -> ``("", "hu")``  (surname only; any first name matches)
    ``"W. Hu"`` / ``"W Hu"`` / ``"Wayne Hu"`` -> ``("w", "hu")``
    """
    return name_key(spec)


def author_spec_matches(paper_keys: list[list[str]], spec_key: tuple[str, str]) -> bool:
    """True if any of a paper's ``[initial, surname]`` pairs satisfies ``spec_key``.

    Surname must match exactly; the initial is checked only when the spec gives one.
    """
    want_i, want_s = spec_key
    if not want_s:
        return False
    for pair in paper_keys:
        p_i, p_s = pair[0], pair[1]
        if p_s == want_s and (not want_i or want_i == p_i):
            return True
    return False


# --- arXiv id + abstract cleanup -----------------------------------------------

_re_arxiv_id = re.compile(r"(\d{4}\.\d{4,5})(v\d+)?")
_re_old_id = re.compile(r"([a-z-]+(?:\.[A-Z]{2})?/\d{7})(v\d+)?")
_re_preamble = re.compile(
    r"^\s*arXiv:\S+\s+Announce Type:\s+\S+\s*\.?\s*(?:Abstract:\s*)?",
    re.IGNORECASE,
)


def arxiv_id(raw: str) -> str:
    """Bare arXiv id (no version) from a feed ``id`` or an ``/abs/`` URL.

    ``oai:arXiv.org:2609.04254v1`` -> ``2609.04254``.
    """
    if not raw:
        return ""
    m = _re_arxiv_id.search(raw)
    if m:
        return m.group(1)
    m = _re_old_id.search(raw)
    return m.group(1) if m else ""


def clean_abstract(summary: str) -> str:
    """Drop arXiv's ``arXiv:xxxx Announce Type: new \\nAbstract:`` preamble."""
    if not summary:
        return ""
    return _re_ws.sub(" ", _re_preamble.sub("", summary)).strip()
