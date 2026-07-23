#!/usr/bin/env python3
"""
Offline tests for the reference verifier.

No network access: every canonical record here is a synthetic fixture, so the
suite is deterministic and runs in CI.

Run: python tests/test_verify.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pubmed_toolkit.verify.bibtex import parse_bibtex  # noqa: E402
from pubmed_toolkit.verify.checks import (  # noqa: E402
    compare_fields,
    cross_check_identifiers,
    is_collective_name,
    normalize_doi,
)
from pubmed_toolkit.verify.models import Reference  # noqa: E402
from pubmed_toolkit.verify.normalize import (  # noqa: E402
    expand_page_range,
    journal_matches,
    norm_author,
    norm_pages,
    pages_match,
    surname_of,
    title_similarity,
)

_passed = 0
_failed = 0


def check(label: str, actual, expected) -> None:
    global _passed, _failed
    ok = actual == expected
    if ok:
        _passed += 1
    else:
        _failed += 1
    status = "[PASS]" if ok else "[FAIL]"
    detail = "" if ok else f"  (expected {expected!r}, got {actual!r})"
    print(f"  {status} {label}{detail}")


# ======================================================================
print("\n--- normalisation ---")
# ======================================================================
check("page range with dash", norm_pages("229-263"), "229 263")
check("page range with en-dash", norm_pages("229–263"), "229 263")
check("page range with article suffix", norm_pages("422-437.e7"), "422 437 e7")
check("accented surname folds", norm_author("Følling"), "folling")
check("umlaut folds", norm_author("Häussinger"), "haussinger")
check("eszett expands", norm_author("Weiß"), "weiss")
check("PubMed style surname", surname_of("Bray F"), "bray")
check("comma style surname", surname_of("Bray, Freddie"), "bray")
check("western style surname", surname_of("Freddie Bray"), "bray")
check("apostrophe surname", surname_of("O'Brien M"), "obrien")
check("journal abbreviation is substring", journal_matches("Lancet", "The Lancet"), True)
check("unrelated journals differ", journal_matches("Nature", "Cell"), False)
check("identical titles score 1.0", title_similarity("Gastric cancer", "gastric cancer"), 1.0)

check("abbreviated end page expands", expand_page_range("202-9"), "202-209")
check("two-digit abbreviation expands", expand_page_range("422-37"), "422-437")
check("four-digit abbreviation expands", expand_page_range("1234-8"), "1234-1238")
check("full range unchanged", expand_page_range("229-263"), "229-263")
check("end longer than start unchanged", expand_page_range("95-101"), "95-101")
check("non-numeric pages passed through", expand_page_range("e1234"), "e1234")

check("PubMed abbreviation matches CrossRef full", pages_match("202-209", "202-9"), True)
check("article-number suffix tolerated", pages_match("422-437.e7", "422-437"), True)
check("en-dash tolerated", pages_match("229–263", "229-263"), True)
check("genuinely different pages rejected", pages_match("202-209", "300-310"), False)
check("off-by-one end page rejected", pages_match("202-209", "202-208"), False)
check("missing side is not a mismatch", pages_match("", "202-209"), True)

doi_variants = [
    "https://doi.org/10.1038/nature13480",
    "DOI:10.1038/nature13480",
    "10.1038/NATURE13480",
]
for v in doi_variants:
    check(f"DOI normalises: {v[:32]}", normalize_doi(v), "10.1038/nature13480")


# ======================================================================
print("\n--- bidirectional identifier cross-check (the core check) ---")
# ======================================================================
# Ground truth: Bass 2014, Nature 513:202-209, DOI 10.1038/nature13480, PMID 25079317
GOOD_REF = Reference(
    key="bass2014", title="Comprehensive molecular characterization of gastric adenocarcinoma",
    first_author="Bass", year="2014", journal="Nature", volume="513", issue="7517",
    pages="202-209", doi="10.1038/nature13480", pmid="25079317",
)
GOOD_PUBMED = {"pmid": "25079317", "doi": "10.1038/nature13480", "year": "2014",
               "journal": "Nature", "first_author": "Bass AJ", "volume": "513",
               "issue": "7517", "pages": "202-9",
               "title": "Comprehensive molecular characterization of gastric adenocarcinoma"}

issues = cross_check_identifiers(GOOD_REF, derived_pmid="25079317", pubmed_meta=GOOD_PUBMED)
check("consistent identifiers raise nothing", len(issues), 0)

# The failure mode this tool exists to catch: real DOI + real PMID, different papers.
issues = cross_check_identifiers(GOOD_REF, derived_pmid="99999999", pubmed_meta=GOOD_PUBMED)
check("DOI resolving to a different PMID is a conflict", len(issues), 1)
check("  ...flagged on the pmid field", issues[0].field, "pmid")
check("  ...with conflict severity", issues[0].severity, "conflict")

mismatched_pubmed = dict(GOOD_PUBMED, doi="10.1016/j.cell.2008.07.001")
issues = cross_check_identifiers(GOOD_REF, derived_pmid="25079317", pubmed_meta=mismatched_pubmed)
check("PMID carrying a different DOI is a conflict", len(issues), 1)
check("  ...flagged on the doi field", issues[0].field, "doi")

# Both directions wrong at once -> two independent conflicts.
issues = cross_check_identifiers(GOOD_REF, derived_pmid="88888888", pubmed_meta=mismatched_pubmed)
check("both directions disagreeing yields two conflicts", len(issues), 2)

# Absence of evidence must not be reported as evidence of conflict.
issues = cross_check_identifiers(GOOD_REF, derived_pmid="", pubmed_meta={})
check("unresolved identifiers raise nothing", len(issues), 0)

no_pmid = Reference(key="x", doi="10.1038/nature13480")
issues = cross_check_identifiers(no_pmid, derived_pmid="25079317", pubmed_meta={})
check("deriving a PMID where none was supplied is not a conflict", len(issues), 0)


# ======================================================================
print("\n--- field comparison ---")
# ======================================================================
check("clean entry has no field issues",
      len(compare_fields(GOOD_REF, GOOD_PUBMED, "pubmed")), 0)

check("'202-209' vs '202-9' tolerated",
      len(compare_fields(Reference(key="k", pages="202-209"),
                         {"pages": "202-9"}, "pubmed")), 0)

check("wrong year flagged",
      len(compare_fields(Reference(key="k", year="2015"),
                         {"year": "2014"}, "crossref")), 1)

# The real-world case from the source bibliography: right paper, wrong journal.
wrong_journal = compare_fields(
    Reference(key="kennedy2015", journal="Antiviral Research"),
    {"journal": "Virology"}, "crossref")
check("wrong journal flagged", len(wrong_journal), 1)
check("  ...names the journal field", wrong_journal[0].field, "journal")

check("surname-only comparison ignores initials",
      len(compare_fields(Reference(key="k", first_author="Bass"),
                         {"first_author": "Bass AJ"}, "pubmed")), 0)

check("different first author flagged",
      len(compare_fields(Reference(key="k", first_author="Smith"),
                         {"first_author": "Bass AJ"}, "pubmed")), 1)

# A fabricated title against a real DOI — the other half of the hallucination problem.
check("unrelated title flagged",
      len(compare_fields(Reference(key="k", title="cccDNA in the CRISPR era"),
                         {"title": "Gene editing technologies to target HBV cccDNA"},
                         "crossref")), 1)

check("empty supplied fields are skipped",
      len(compare_fields(Reference(key="k"), GOOD_PUBMED, "pubmed")), 0)


# ======================================================================
print("\n--- consortium authorship (false-positive guard) ---")
# ======================================================================
# Bass 2014 is credited to a consortium, so CrossRef reports the collective as
# author[0] while bibliographies cite the individual. Flagging that as a
# mismatch would make the tool cry wolf on a perfectly correct entry.
CONSORTIUM_META = {
    "first_author": "The Cancer Genome Atlas Research Network",
    "all_authors": ["The Cancer Genome Atlas Research Network", "Bass AJ",
                    "Thorsson V", "Shmulevich I", "Ng SM"],
    "year": "2014", "journal": "Nature",
}

check("collective byline detected", is_collective_name("The Cancer Genome Atlas Research Network"), True)
check("consortium detected via 'Group'", is_collective_name("EASL Study Group"), True)
check("ordinary surname is not collective", is_collective_name("Bass AJ"), False)

check("cited author present but not first is accepted",
      len(compare_fields(Reference(key="bass2014", first_author="Bass, Adam J."),
                         CONSORTIUM_META, "crossref")), 0)

check("author absent from a listed roster is still flagged",
      len(compare_fields(Reference(key="k", first_author="Nonexistent, Q."),
                         CONSORTIUM_META, "crossref")), 1)

# CrossRef records consortium papers with the collective as the *only* author,
# so there is no roster to check a person against. Comparing a person to an
# organisation is not a finding; PubMed supplies the individual authors and
# performs the real check.
CROSSREF_CONSORTIUM_ONLY = {
    "first_author": "The Cancer Genome Atlas Research Network",
    "all_authors": ["The Cancer Genome Atlas Research Network"],
    "year": "2014", "journal": "Nature",
}
check("person vs collective-only byline is not a finding",
      len(compare_fields(Reference(key="bass2014", first_author="Bass, Adam J."),
                         CROSSREF_CONSORTIUM_ONLY, "crossref")), 0)
check("collective cited against a different collective is still flagged",
      len(compare_fields(Reference(key="k", first_author="EASL Study Group"),
                         CROSSREF_CONSORTIUM_ONLY, "crossref")), 1)

# Non-consortium reordering: cited author is a genuine co-author, just not first.
REORDERED = {"first_author": "Thorsson V",
             "all_authors": ["Thorsson V", "Bass AJ", "Shmulevich I"]}
check("co-author cited instead of first author is accepted",
      len(compare_fields(Reference(key="k", first_author="Bass"), REORDERED, "pubmed")), 0)

# When no author list is available, a collective byline cannot be contradicted.
check("collective with no author list does not flag",
      len(compare_fields(Reference(key="k", first_author="Bass"),
                         {"first_author": "EASL Study Group"}, "crossref")), 0)

check("plain byline with no author list still flags",
      len(compare_fields(Reference(key="k", first_author="Smith"),
                         {"first_author": "Bass AJ"}, "pubmed")), 1)


# ======================================================================
print("\n--- BibTeX parsing ---")
# ======================================================================
SAMPLE = r"""
@article{bass2014,
  title   = {Comprehensive molecular characterization of gastric adenocarcinoma},
  author  = {Bass, Adam J. and Thorsson, Vesteinn and Shmulevich, Ilya},
  journal = {Nature},
  volume  = {513},
  number  = {7517},
  pages   = {202--209},
  year    = {2014},
  doi     = {10.1038/nature13480},
  pmid    = {25079317}
}

@article{quoted2020,
  title   = "A study with {HBV} braces and a \& ampersand",
  author  = "Følling, Ivar",
  journal = "The Lancet",
  year    = "2020",
  doi     = "https://doi.org/10.1016/S0140-6736(20)30183-5"
}

@book{textbook2018,
  title     = {Human Parasitology},
  author    = {Zhu, Ming},
  publisher = {Example Press},
  year      = {2018}
}
"""

refs = parse_bibtex(SAMPLE)
check("three entries parsed", len(refs), 3)

r0 = refs[0]
check("key read", r0.key, "bass2014")
check("first author extracted from 'and' list", r0.first_author, "Bass, Adam J.")
check("surname of parsed author", surname_of(r0.first_author), "bass")
check("journal read", r0.journal, "Nature")
check("number maps to issue", r0.issue, "7517")
check("TeX double dash preserved for normalisation", norm_pages(r0.pages), "202 209")
check("doi read", r0.doi, "10.1038/nature13480")
check("pmid read", r0.pmid, "25079317")

r1 = refs[1]
check("quoted values parsed", r1.journal, "The Lancet")
check("inner braces stripped", r1.title, "A study with HBV braces and a & ampersand")
check("DOI URL prefix stripped", r1.doi, "10.1016/S0140-6736(20)30183-5")
check("accented author folds for comparison", surname_of(r1.first_author), "folling")

r2 = refs[2]
check("book entry type kept", r2.entry_type, "book")
check("book without identifiers", r2.has_identifier(), False)


# ======================================================================
print("\n" + "=" * 70)
print(f"Summary: {_passed} passed / {_failed} failed / {_passed + _failed} total")
print("=" * 70)
sys.exit(0 if _failed == 0 else 1)
