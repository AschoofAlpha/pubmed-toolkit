"""
Self-contained BibTeX reader.

The original verification scripts imported a parser by absolute path from a
local tools directory, which made them unrunnable anywhere else. This module
replaces that with a dependency-free parser covering the subset of BibTeX that
appears in real bibliographies: @type{key, field = {value} | "value" | bare}.

It is a reader, not a full BibTeX implementation — @string macros, @preamble
and cross-references are out of scope and are skipped rather than guessed at.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from .models import Reference

logger = logging.getLogger("pubmed_toolkit.verify.bibtex")

# Both delimiters are legal BibTeX. Only braces were accepted before, so
# `@article(key, ...)` entries were dropped without a word — a silent omission
# from a bibliography is exactly the failure this tool exists to prevent.
_ENTRY_START = re.compile(r"@(\w+)\s*([{(])\s*([^,\s{}()]+)\s*,", re.MULTILINE)

# @string{nat = "Nature"} — collected before parsing so that `journal = nat`
# resolves instead of being compared literally as 'nat' against 'Nature'.
_STRING_RE = re.compile(
    r'@string\s*[{(]\s*([A-Za-z][\w.:+-]*)\s*=\s*(\{[^{}]*\}|"[^"]*"|[^,})]+)\s*[})]',
    re.IGNORECASE,
)

# BibTeX month abbreviations are not years; guard the year extractor.
_YEAR_RE = re.compile(r"\b(1[6-9]\d{2}|20\d{2}|21\d{2})\b")

# Predefined in every BibTeX style, so files use them without an @string.
_BUILTIN_MACROS = {
    "jan": "January", "feb": "February", "mar": "March", "apr": "April",
    "may": "May", "jun": "June", "jul": "July", "aug": "August",
    "sep": "September", "oct": "October", "nov": "November", "dec": "December",
}


def _strip_braces(value: str) -> str:
    """Remove TeX braces/escapes and collapse whitespace to a plain string."""
    v = value.strip()
    while len(v) >= 2 and v[0] in "{\"" and v[-1] in "}\"":
        v = v[1:-1].strip()
    v = v.replace("\\&", "&").replace("\\%", "%").replace("\\_", "_")
    v = re.sub(r"[{}]", "", v)
    return re.sub(r"\s+", " ", v).strip()


def collect_macros(text: str) -> dict[str, str]:
    """Read every @string definition into a lowercase-keyed lookup table."""
    macros = dict(_BUILTIN_MACROS)
    for m in _STRING_RE.finditer(text):
        macros[m.group(1).lower()] = _strip_braces(m.group(2))
    return macros


def _resolve_value(raw: str, macros: dict[str, str], key: str, field: str) -> str:
    """
    Resolve an unquoted BibTeX value: a macro name, a number, or a `#`
    concatenation of those with quoted literals.

    An unresolvable non-numeric word is returned unchanged but warned about,
    because comparing it literally is what produced false 'journal mismatch'
    findings on files whose @string definitions live in another file.
    """
    def unwrap(part: str) -> str:
        # Like _strip_braces but without trimming the edges: in `nrc # " Suppl"`
        # the leading space inside the literal is the only thing separating the
        # two halves, and stripping it yields 'Nat Rev CancerSuppl'.
        v = part
        if len(v) >= 2 and ((v[0] == "{" and v[-1] == "}") or (v[0] == '"' and v[-1] == '"')):
            v = v[1:-1]
        v = v.replace("\\&", "&").replace("\\%", "%").replace("\\_", "_")
        return re.sub(r"\s+", " ", re.sub(r"[{}]", "", v))

    pieces: list[str] = []
    for part in (p.strip() for p in raw.split("#")):
        if not part:
            continue
        if (part.startswith("{") and part.endswith("}")) or \
           (part.startswith('"') and part.endswith('"')):
            pieces.append(unwrap(part))
        elif part.lower() in macros:
            pieces.append(macros[part.lower()])
        else:
            if not part.isdigit():
                logger.warning(
                    "BibTeX entry '%s': field '%s' uses undefined macro '%s'; "
                    "comparing it literally may report a spurious mismatch. "
                    "Define it with @string, or brace the value.", key, field, part,
                )
            pieces.append(part)
    return "".join(pieces).strip()


def _split_fields(body: str, macros: dict[str, str], key: str = "") -> dict[str, str]:
    """Split an entry body into field->value, respecting brace nesting."""
    fields: dict[str, str] = {}
    i, n = 0, len(body)
    while i < n:
        eq = body.find("=", i)
        if eq == -1:
            break
        name = body[i:eq].strip().strip(",").strip().lower()
        j = eq + 1
        while j < n and body[j].isspace():
            j += 1
        if j >= n:
            break

        if body[j] == "{":
            depth, start = 0, j
            while j < n:
                if body[j] == "{":
                    depth += 1
                elif body[j] == "}":
                    depth -= 1
                    if depth == 0:
                        j += 1
                        break
                j += 1
            raw = body[start:j]
        elif body[j] == '"':
            start = j
            j += 1
            while j < n and body[j] != '"':
                j += 2 if body[j] == "\\" else 1
            j += 1
            raw = body[start:j]
        else:
            # Unquoted: a macro name, a number, or a `#` concatenation. Scan to
            # the next top-level comma, stepping over any quoted segment so a
            # comma inside `nat # "Rev, Cancer"` does not truncate the value.
            start, in_quote = j, False
            while j < n and (in_quote or body[j] != ","):
                if body[j] == "\\":
                    j += 1
                elif body[j] == '"':
                    in_quote = not in_quote
                j += 1
            raw = body[start:j]

        if name:
            if raw.lstrip()[:1] in "{\"":
                fields[name] = _strip_braces(raw)
            else:
                fields[name] = _resolve_value(raw, macros, key, name)
        while j < n and body[j] != ",":
            j += 1
        i = j + 1
    return fields


def _first_author(author_field: str) -> str:
    """Take the first name from an 'A and B and C' author list."""
    if not author_field:
        return ""
    return re.split(r"\s+and\s+", author_field, maxsplit=1)[0].strip()


def _clean_identifier(value: str, kind: str) -> str:
    """Normalise a DOI or PMID that may arrive wrapped in a URL or prefix."""
    v = (value or "").strip()
    if kind == "doi":
        for p in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/",
                  "http://dx.doi.org/", "doi:", "DOI:"):
            if v.lower().startswith(p.lower()):
                v = v[len(p):]
        return v.strip()

    # PMID. Reject anything that is not cleanly a PubMed identifier rather than
    # salvaging digits out of it. Scavenging with a loose \d{4,9} search turned
    # 'PMC3388858' into '3388858' — a real but completely unrelated PMID, which
    # would then be "verified" against the wrong paper. Silence is safer than a
    # confident wrong answer here.
    v = re.sub(r"^\s*(pmid|pubmed)\s*[:=]?\s*", "", v, flags=re.IGNORECASE)
    v = re.sub(r"^https?://(www\.)?(pubmed\.ncbi\.nlm\.nih\.gov|ncbi\.nlm\.nih\.gov/pubmed)/",
               "", v, flags=re.IGNORECASE)
    v = v.strip().rstrip("/")
    return v if re.fullmatch(r"\d{1,8}", v) else ""


def _strip_comments(text: str) -> str:
    """
    Blank out %-to-end-of-line comments outside braces and quotes.

    Commenting an entry out with `%` is the standard TeX idiom. Without this,
    a disabled entry is parsed, looked up and reported as if it were live.
    Characters are replaced with spaces rather than deleted so that every
    offset in the original text stays valid.
    """
    out = list(text)
    depth = in_quote = 0
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == "\\":
            i += 2
            continue
        if c == '"' and depth == 0:
            in_quote = not in_quote
        elif c == "{":
            depth += 1
        elif c == "}":
            depth = max(0, depth - 1)
        elif c == "%" and depth == 0 and not in_quote:
            while i < n and text[i] != "\n":
                out[i] = " "
                i += 1
            continue
        i += 1
    return "".join(out)


# A PMID labelled as such inside free text. The negative lookbehind on 'C' is
# what stops 'PMCID: PMC3388858' from being harvested as PMID 3388858 — a real
# but unrelated record, which would then be "verified" against the wrong paper.
_PMID_IN_TEXT = re.compile(r"\bPM(?<!PMC)ID\s*[:=]?\s*(\d{1,8})\b", re.IGNORECASE)


def _read_pmid(fields: dict[str, str]) -> str:
    """
    Read a PMID from wherever the exporting tool actually put it.

    Three locations occur in the wild, and only the first is obvious:

      pmid = {25079317}                     explicit field (rare in practice)
      eprint = {25079317}, eprinttype={pmid}  biblatex / JabRef
      note = {PMID: 25079317}               Zotero, via its "Extra" field

    The Zotero case matters most and was missed at first release. Zotero is the
    dominant reference manager in biomedicine, and its BibTeX translator maps
    "Extra" to `note`, so a bibliography exported from it carries its PMIDs in
    prose rather than in a field. Missing them meant the bidirectional
    DOI<->PMID check — the whole point of this module — could not fire on the
    exports most of its intended users produce.

    Text extraction is deliberately strict: only digits explicitly labelled
    PMID are taken. Bare numbers in a note are not PMIDs, and a confident wrong
    identifier is far worse here than a missing one.
    """
    if fields.get("pmid"):
        return _clean_identifier(fields["pmid"], "pmid")

    if fields.get("eprinttype", "").strip().lower() in {"pmid", "pubmed"}:
        return _clean_identifier(fields.get("eprint", ""), "pmid")

    for field in ("note", "annote", "keywords", "extra"):
        m = _PMID_IN_TEXT.search(fields.get(field, ""))
        if m:
            return m.group(1)
    return ""


def _find_entry_end(text: str, opener_pos: int, opener: str, hard_limit: int) -> tuple[int, bool]:
    """
    Locate the delimiter closing an entry. Returns (index, closed_cleanly).

    Brace-delimited entries nest plainly. Paren-delimited entries need braces
    tracked separately, so that a ')' inside `title = {Something (2020)}` does
    not end the entry early.
    """
    if opener == "{":
        depth, j = 0, opener_pos
        while j < hard_limit:
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
                if depth == 0:
                    return j, True
            j += 1
        return j, False

    depth = brace_depth = 0
    in_quote = False
    j = opener_pos
    while j < hard_limit:
        c = text[j]
        if c == "\\":
            j += 2
            continue
        if c == '"' and brace_depth == 0:
            in_quote = not in_quote
        elif not in_quote:
            if c == "{":
                brace_depth += 1
            elif c == "}":
                brace_depth = max(0, brace_depth - 1)
            elif brace_depth == 0:
                if c == "(":
                    depth += 1
                elif c == ")":
                    depth -= 1
                    if depth == 0:
                        return j, True
        j += 1
    return j, False


def parse_bibtex(text: str) -> list[Reference]:
    """Parse BibTeX source into Reference objects."""
    text = _strip_comments(text)
    macros = collect_macros(text)
    refs: list[Reference] = []

    starts = list(_ENTRY_START.finditer(text))
    for idx, m in enumerate(starts):
        entry_type, opener, key = m.group(1).lower(), m.group(2), m.group(3)
        if entry_type in {"string", "preamble", "comment"}:
            continue

        # An entry may never extend past the start of the next entry. Without
        # this bound, a single unbalanced brace inside a title swallows the
        # following entries and the parser silently attributes *their* DOI and
        # PMID to this one — producing a confident verification of the wrong
        # paper. A stray '{' is among the most common .bib typos, so this has
        # to fail loudly rather than bleed.
        hard_limit = starts[idx + 1].start() if idx + 1 < len(starts) else len(text)

        opener_pos = text.find(opener, m.start())
        if opener_pos == -1 or opener_pos >= hard_limit:
            continue
        j, closed = _find_entry_end(text, opener_pos, opener, hard_limit)

        if not closed:
            logger.warning(
                "BibTeX entry '%s' is unbalanced; parsed up to the next entry. "
                "Its fields may be incomplete — fix the delimiters and re-run.", key,
            )
        body = text[m.end():min(j, hard_limit)]

        f = _split_fields(body, macros, key)
        year = f.get("year", "")
        if year and not _YEAR_RE.fullmatch(year.strip()):
            found = _YEAR_RE.search(year)
            year = found.group(1) if found else year

        refs.append(Reference(
            key=key,
            title=f.get("title", ""),
            first_author=_first_author(f.get("author", "") or f.get("editor", "")),
            year=year,
            journal=f.get("journal", "") or f.get("journaltitle", "") or f.get("booktitle", ""),
            volume=f.get("volume", ""),
            issue=f.get("number", "") or f.get("issue", ""),
            pages=f.get("pages", ""),
            doi=_clean_identifier(f.get("doi", ""), "doi"),
            pmid=_read_pmid(f),
            entry_type=entry_type,
        ))
    return refs


def load_bibtex(path: str | Path) -> list[Reference]:
    """Read a .bib file, tolerating the usual encoding variations."""
    p = Path(path)
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return parse_bibtex(p.read_text(encoding=encoding))
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Could not decode {p} as UTF-8 or Latin-1")


def load_json_refs(path: str | Path) -> list[Reference]:
    """
    Read references from JSON: either a list of objects, or {"references": [...]}.

    Lets callers verify entries that never existed as BibTeX — e.g. a reference
    list pasted out of a manuscript and structured by hand.
    """
    import json

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("references") or data.get("entries") or []
    known = set(Reference.__dataclass_fields__)
    refs = []
    for i, item in enumerate(data, 1):
        fields = {k: str(v) for k, v in item.items() if k in known and v is not None}
        fields.setdefault("key", f"ref{i}")
        # Identifiers must go through the same normalisation as the BibTeX path.
        # Skipping it meant a JSON entry carrying 'https://doi.org/10.1038/...'
        # was sent to CrossRef verbatim, 404'd, and got reported as an
        # unregistered DOI — a fabricated finding about a perfectly good record.
        if fields.get("doi"):
            fields["doi"] = _clean_identifier(fields["doi"], "doi")
        if fields.get("pmid"):
            fields["pmid"] = _clean_identifier(fields["pmid"], "pmid")
        refs.append(Reference(**fields))
    return refs
