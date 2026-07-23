#!/usr/bin/env python3
"""
Every place a PMID legitimately hides in a .bib file, and every place it must
not be scavenged from.

_read_pmid gained the note/annote/keywords/extra text scan because Zotero — the
dominant reference manager in biomedicine — maps its "Extra" field to `note`,
so real exports carry their PMIDs in prose rather than in a field. Without that
scan the bidirectional DOI<->PMID cross-check, the headline feature of the
verify module, could not fire at all on the files its intended users actually
produce. That fix shipped untested; this file is its coverage.

The rejection half matters more than the acceptance half. A missing PMID costs
one unchecked entry. A wrong PMID silently certifies the reference against a
different paper, which is the exact failure this module exists to prevent — so
every rejection case below is a real string that occurs in exported
bibliographies and contains digits that look harvestable.

Fully offline: every fixture is synthetic BibTeX, no network, no files.

Run: python tests/test_bibtex_pmid_sources.py
"""

from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pubmed_toolkit.verify.bibtex import (  # noqa: E402
    _PMID_IN_TEXT,
    _read_pmid,
    parse_bibtex,
)

_passed = 0
_failed = 0

# The PMID used throughout: a real, well-known record (Nature 2014). Reusing one
# value keeps a wrong answer obvious — anything else in the output is a bug.
PMID = "25079317"


def check(label: str, actual: object, expected: object) -> None:
    global _passed, _failed
    ok = actual == expected
    if ok:
        _passed += 1
    else:
        _failed += 1
    detail = "" if ok else f"  (expected {expected!r}, got {actual!r})"
    print(f"  {'[PASS]' if ok else '[FAIL]'} {label}{detail}")


def pmid_of(source: str) -> str:
    """
    The PMID as it lands on the parsed Reference, not as _read_pmid saw it.

    Routing through parse_bibtex keeps field splitting and brace stripping in
    the loop: a note _read_pmid would handle perfectly is still lost if the
    parser never hands the field over intact, and that seam is where the value
    users care about actually gets produced.
    """
    refs = parse_bibtex(source)
    if len(refs) != 1:
        raise AssertionError(f"fixture must parse to exactly 1 entry, got {len(refs)}: {source!r}")
    return refs[0].pmid


# ======================================================================
print("\n--- Sources a PMID may legitimately come from ---")
# ======================================================================
_ACCEPTED = [
    ("explicit pmid field", r"@article{a, doi = {10.1/x}, pmid = {25079317}}"),
    ("biblatex eprint", r"@article{b, doi = {10.1/x}, eprint = {25079317}, eprinttype = {pmid}}"),
    ("eprinttype spelled pubmed", r"@article{c, eprint = {25079317}, eprinttype = {pubmed}}"),
    # biblatex field values are not case-normalised by the parser, so the
    # eprinttype comparison has to fold case itself.
    ("eprinttype in mixed case", r"@article{d, eprint = {25079317}, eprinttype = {PubMed}}"),
    ("zotero note", r"@article{e, doi = {10.1/x}, note = {PMID: 25079317}}"),
    ("annote", r"@article{f, doi = {10.1/x}, annote = {PMID 25079317}}"),
    ("keywords", r"@article{g, keywords = {oncology, PMID: 25079317}}"),
    ("extra", r"@article{h, extra = {PMID: 25079317}}"),
]
for label, src in _ACCEPTED:
    check(f"reads PMID from {label}", pmid_of(src), PMID)


# ======================================================================
print("\n--- How the label may be written inside free text ---")
# ======================================================================
# Zotero's "Extra" is hand-edited by users and pasted from PubMed's own export,
# so the separator, the spacing and the case all vary between real files.
_LABEL_FORMS = [
    ("colon separator", r"@article{a, note = {PMID: 25079317}}"),
    ("no separator", r"@article{b, note = {PMID 25079317}}"),
    ("equals separator", r"@article{c, note = {PMID = 25079317}}"),
    ("no whitespace at all", r"@article{d, note = {PMID:25079317}}"),
    ("lowercase label", r"@article{e, note = {pmid: 25079317}}"),
    ("surrounded by prose", r"@article{f, note = {Publisher: Nature. PMID: 25079317. Cited 40}}"),
    # A comma inside a braced value must not end the field early, or the note is
    # truncated before the parser ever reaches the PMID.
    ("after a comma inside the note", r"@article{g, note = {Publisher: Nature, PMID: 25079317}}"),
    ("quoted value instead of braced", '@article{h, note = "PMID: 25079317"}'),
    ("braces around the digits", r"@article{i, note = {PMID: {25079317}}}"),
]
for label, src in _LABEL_FORMS:
    check(f"label written as {label}", pmid_of(src), PMID)

# Zotero writes a multi-line Extra verbatim; the whitespace collapse in
# _strip_braces is what keeps `PMID:\n  25079317` readable to the text scan.
check("label split across lines in the note", pmid_of(
    "@article{multi,\n"
    "  note = {Publisher: Nature Publishing Group\n"
    "          PMID: 25079317},\n"
    "  doi = {10.1/x}\n"
    "}"
), PMID)


# ======================================================================
print("\n--- Rejections: digits that must never become a PMID ---")
# ======================================================================
# Each of these is a plausible bibliography string carrying 4-8 harvestable
# digits. Returning any of them would send the entry to PubMed and "verify" it
# against an unrelated paper, which reads as a clean bill of health.
_REJECTED = [
    # PMC3388858 -> 3388858 is a real, live, completely unrelated PubMed record.
    ("a PMCID", r"@article{a, doi = {10.1/x}, note = {PMCID: PMC3388858}}"),
    ("a bare PMC accession", r"@article{b, doi = {10.1/x}, note = {PMC11704023}}"),
    # The label being right does not make the payload right.
    ("a PMC accession behind a PMID label", r"@article{c, note = {PMID: PMC3388858}}"),
    ("a PMC accession in the pmid field", r"@article{d, pmid = {PMC3388858}}"),
    ("unlabelled digits in prose", r"@article{e, note = {see page 12345678 of the report}}"),
    ("an arXiv id", r"@article{f, eprint = {2604.03159}, eprinttype = {arxiv}}"),
    # An eprint with no eprinttype is of unknown provenance — arXiv uses the same
    # field, and guessing "PubMed" from digits alone is how the wrong record gets
    # fetched. biblatex only makes eprint meaningful together with eprinttype.
    ("an eprint with no eprinttype", r"@article{g, eprint = {25079317}}"),
    ("an arXiv id in the pmid field", r"@article{h, pmid = {arXiv:2604.03159}}"),
    ("a versioned identifier", r"@article{i, pmid = {25079317v1}}"),
    # Nine digits is not a PubMed identifier. The \b after the digit group is what
    # makes this a rejection instead of a silent truncation to the first eight.
    ("nine digits behind a PMID label", r"@article{j, note = {PMID: 250793171}}"),
    ("a twelve-digit number in the pmid field", r"@article{k, pmid = {123456789012}}"),
    ("a PMC article URL", r"@article{l, pmid = {https://www.ncbi.nlm.nih.gov/pmc/articles/PMC3388858/}}"),
    ("no identifier at all", r"@article{m, title = {A paper with nothing to go on}}"),
]
for label, src in _REJECTED:
    check(f"rejects {label}", pmid_of(src), "")

# The mixed note is the case the whole PMCID guard exists for: both numbers are
# present, and only one of them is this paper.
check("takes the PMID and not the PMCID when a note carries both",
      pmid_of(r"@article{both, note = {PMCID: PMC3388858. PMID: 25079317}}"), PMID)


# ======================================================================
print("\n--- PMID supplied as a URL ---")
# ======================================================================
# Copy-pasting the browser address bar is the most common way a PMID reaches a
# .bib file by hand, in both the current and the legacy URL shape.
check("current pubmed URL",
      pmid_of(r"@article{a, pmid = {https://pubmed.ncbi.nlm.nih.gov/25079317/}}"), PMID)
check("legacy /pubmed/ URL",
      pmid_of(r"@article{b, pmid = {http://www.ncbi.nlm.nih.gov/pubmed/25079317}}"), PMID)
check("URL behind a PMID label",
      pmid_of(r"@article{c, pmid = {PMID: https://pubmed.ncbi.nlm.nih.gov/25079317/}}"), PMID)


# ======================================================================
print("\n--- Precedence between the three sources ---")
# ======================================================================
# Structured fields outrank prose: a tool that wrote a real field knew what it
# meant, whereas a note is whatever the user typed.
check("explicit pmid field outranks eprint",
      _read_pmid({"pmid": "111", "eprinttype": "pmid", "eprint": "222"}), "111")
check("eprint outranks the note",
      _read_pmid({"eprinttype": "pmid", "eprint": "222", "note": "PMID: 333"}), "222")
check("an empty pmid field falls through to the note",
      _read_pmid({"pmid": "", "note": "PMID: 25079317"}), PMID)
check("note is read before annote",
      _read_pmid({"note": "PMID: 111", "annote": "PMID: 222"}), "111")
check("no fields at all", _read_pmid({}), "")


# ======================================================================
print("\n--- Known gaps and hazards: current behaviour, pinned ---")
# ======================================================================
# These expectations describe what _read_pmid does today, not what it should do.
# They are here so that a change in any of them is visible in the diff rather
# than discovered on someone's bibliography. Update the expectation when the
# behaviour is deliberately fixed; do not delete the case.

# A junk structured field returns early and never reaches the note fallback, so
# a Zotero export with a PMCID in `pmid` and the real PMID in `note` yields
# nothing. Fails safe (missing, not wrong) but defeats the fix on exactly the
# files it was written for.
check("KNOWN GAP: a PMCID in `pmid` hides a good PMID in `note`",
      _read_pmid({"pmid": "PMC3388858", "note": "PMID: 25079317"}), "")
check("KNOWN GAP: an empty biblatex eprint hides a good PMID in `note`",
      _read_pmid({"eprinttype": "pmid", "eprint": "", "note": "PMID: 25079317"}), "")

# Digit-group separators truncate at the first group because \d{1,8} stops at the
# separator and \b is satisfied by it. '25' is a real PubMed record, so this is
# the one path that returns a confidently WRONG identifier rather than none.
check("KNOWN HAZARD: a comma-grouped PMID truncates to a real but wrong id",
      _read_pmid({"note": "PMID: 25,079,317"}), "25")
check("KNOWN HAZARD: a space-grouped PMID truncates the same way",
      _read_pmid({"note": "PMID: 25 079 317"}), "25")

# PubMed's own "Comment on" / "Erratum in" lines carry another paper's PMID, and
# users paste them into Zotero's Extra wholesale. Nothing in the text tells the
# scan whose identifier it is, so the first label wins.
check("KNOWN HAZARD: a 'Comment on' note yields the commented paper's PMID",
      _read_pmid({"note": "Comment on: Nature 2010;464:1067. PMID: 20393562"}), "20393562")
check("first labelled PMID wins when a note carries two",
      _read_pmid({"note": "PMID: 25079317. Retracted, see PMID: 30000000"}), PMID)

# There is no lower bound, so an obviously impossible identifier passes through
# to the lookup instead of being dropped here.
check("KNOWN GAP: zero passes as a PMID", _read_pmid({"note": "PMID: 0"}), "0")

# Lossy but safe: recognised in the pmid field, not in prose. Worth knowing
# before someone reports it as a parser bug.
check("a pubmed URL inside a note is not read",
      _read_pmid({"note": "https://pubmed.ncbi.nlm.nih.gov/25079317/"}), "")
check("a plural 'PMIDs:' label is not read", _read_pmid({"note": "PMIDs: 25079317"}), "")

# The `(?<!PMC)` lookbehind in _PMID_IN_TEXT is inert: it is placed after `PM`,
# where the three preceding characters always end in "PM" and so can never equal
# "PMC". PMCIDs are rejected only because "PMCID" does not contain the substring
# "PMID". The guard is therefore load-bearing in the comment, not in the regex —
# pinned here so that anyone relaxing the pattern (e.g. to accept "PMC ID")
# learns that the real protection has to be rebuilt, not inherited.
_WITHOUT_LOOKBEHIND = re.compile(r"\bPMID\s*[:=]?\s*(\d{1,8})\b", re.IGNORECASE)
_PROBES = [
    "PMCID: PMC3388858", "PMID: 25079317", "PMC3388858", "PMID PMC3388858",
    "PMCPMID: 25079317", "PMIDPMID: 25079317", "xPMID: 1", "a PMID: 25079317",
]


def _matched(pattern: re.Pattern[str], text: str) -> str | None:
    m = pattern.search(text)
    return m.group(1) if m else None


check("KNOWN DEAD CODE: the (?<!PMC) lookbehind changes no result",
      [_matched(_PMID_IN_TEXT, s) for s in _PROBES],
      [_matched(_WITHOUT_LOOKBEHIND, s) for s in _PROBES])


print("\n" + "=" * 70)
print(f"Summary: {_passed} passed / {_failed} failed / {_passed + _failed} total")
print("=" * 70)
sys.exit(0 if _failed == 0 else 1)
