"""
Reference checking logic.

The distinctive check here is **bidirectional identifier resolution**. Tools
that verify citations typically confirm that a record *exists* — they look up
the DOI, get a hit, and stop. That misses the failure mode that matters most
for LLM-generated bibliographies: an entry whose DOI is real and whose PMID is
real, but which point at two *different* papers.

So when an entry carries both identifiers, each is resolved independently and
the results are required to agree in both directions:

    DOI  --ESearch-->  PMID'   must equal the supplied PMID
    PMID --ESummary--> DOI'    must equal the supplied DOI

A disagreement is reported as a `conflict`, which is a strictly stronger
finding than any single-field mismatch: it means at least one of the two
identifiers was not taken from the paper being cited.
"""

from __future__ import annotations

import logging
from typing import Any

from .models import Issue, Reference, VerifyResult
from .normalize import (
    journal_matches,
    norm_text,
    pages_match,
    surname_candidates,
    title_similarity,
)

# Same logger as the runner: a check that could not be performed has to reach
# the operator, and this module has no other channel to say so.
logger = logging.getLogger("pubmed_toolkit.verify")

# Below this token-overlap ratio two titles are treated as different papers.
TITLE_MATCH_THRESHOLD = 0.55

# Words that mark a byline as a consortium rather than a person. Such papers
# list the collective first, so the individual a bibliography cites is a real
# author who simply is not in position one.
COLLECTIVE_MARKERS = frozenset({
    "group", "network", "consortium", "collaboration", "collaborators",
    "investigators", "committee", "society", "initiative", "project",
    "team", "trial", "study", "association", "college", "programme", "program",
})


def is_collective_name(name: str) -> bool:
    """True when a byline looks like an organisation rather than a person."""
    tokens = norm_text(name).split()
    return bool(tokens) and any(t in COLLECTIVE_MARKERS for t in tokens)


def normalize_doi(doi: str) -> str:
    """Strip URL prefixes and case so two spellings of one DOI compare equal."""
    d = (doi or "").strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/",
                   "http://dx.doi.org/", "doi:"):
        if d.startswith(prefix):
            d = d[len(prefix):]
    return d.strip()


def cross_check_identifiers(
    ref: Reference,
    derived_pmid: str,
    pubmed_meta: dict[str, Any],
) -> list[Issue]:
    """
    Compare supplied identifiers against independently resolved ones.

    Only reports a conflict when both sides are actually present — a missing
    resolution is an absence of evidence, not evidence of a mismatch.
    """
    issues: list[Issue] = []

    # Forward: supplied DOI resolved to a PMID that contradicts the supplied one.
    if ref.doi and ref.pmid and derived_pmid and derived_pmid != ref.pmid.strip():
        issues.append(Issue(
            field="pmid",
            supplied=ref.pmid,
            canonical=derived_pmid,
            source="cross-id",
            severity="conflict",
        ))

    # Reverse: supplied PMID's record carries a DOI that contradicts the supplied one.
    #
    # This must require ref.pmid, not just ref.doi. When the user supplied only
    # a DOI, `pubmed_meta` is the record of the PMID we *derived from that same
    # DOI*, so any DOI discrepancy inside PubMed (corrections, ahead-of-print,
    # supplement DOIs) would be reported as a conflict for an entry that never
    # carried a PMID at all. `conflict` is this tool's strongest claim; it must
    # not be reachable without two user-supplied identifiers to contradict.
    derived_doi = normalize_doi(pubmed_meta.get("doi", "")) if pubmed_meta else ""
    supplied_doi = normalize_doi(ref.doi)
    if ref.pmid and supplied_doi and derived_doi and derived_doi != supplied_doi:
        issues.append(Issue(
            field="doi",
            supplied=ref.doi,
            canonical=pubmed_meta.get("doi", ""),
            source="cross-id",
            severity="conflict",
        ))

    return issues


def compare_fields(ref: Reference, meta: dict[str, Any], source: str) -> list[Issue]:
    """Compare a reference against one canonical record, field by field."""
    issues: list[Issue] = []
    if not meta or "__error__" in meta:
        return issues

    def add(field: str, supplied: str, canonical: str) -> None:
        issues.append(Issue(field=field, supplied=supplied,
                            canonical=canonical, source=source))

    # First author — compare surnames only; given-name conventions vary wildly.
    #
    # Two real-world patterns would otherwise produce false positives:
    #
    #  * Consortium papers. For Bass 2014 CrossRef records exactly one author,
    #    "The Cancer Genome Atlas Research Network", and no individuals at all,
    #    while bibliographies cite a person. A person cannot be compared against
    #    an organisation, so that comparison is skipped rather than failed.
    #    PubMed does list the individuals, so the check still happens there.
    #  * Author ordering differences between sources. If the cited author
    #    appears anywhere in the known author list, the citation is accepted.
    #  * Ambiguous name order. 'Jing WU' may be given+SURNAME or surname+initials,
    #    so every plausible reading is compared and any overlap counts as
    #    agreement (see normalize.surname_candidates).
    #
    # What remains flagged is the case that actually signals a bad citation:
    # a named person who does not appear among the paper's authors.
    if ref.first_author and meta.get("first_author"):
        supplied = surname_candidates(ref.first_author)
        canonical_names = surname_candidates(meta["first_author"])
        if not supplied or not canonical_names:
            # Normalisation emptied a name that was not empty to begin with:
            # a byline that survived parsing as punctuation, digits or markup.
            # `surnames_agree` answers True for that ("nothing comparable"), and
            # a plain truthiness test on the normalised value swallows it just
            # as quietly, so the entry gets reported as clean although no author
            # check ever ran. This is a deliberate skip like the
            # person-vs-collective one below, and for the same reason — an unrun
            # check must never be mistaken for a passed one — but said out loud,
            # because unlike a consortium byline there is nothing in the report
            # to hint that a name was involved at all.
            #
            # A log line rather than an Issue: an Issue would flip the entry to
            # `mismatch`, which is the very false alarm this branch avoids.
            logger.warning(
                "%s [%s]: first-author check skipped, %r vs %r normalise to nothing",
                ref.key, source, ref.first_author, meta["first_author"],
            )
        elif not (supplied & canonical_names):
            roster = [a for a in (meta.get("all_authors") or []) if a]
            people: set[str] = set()
            for a in roster:
                if not is_collective_name(a):
                    people |= surname_candidates(a)
            # Skip only when the record offers no individual to compare against
            # and the cited name is a person: that is missing data, not a defect.
            uncomparable = (
                not people
                and is_collective_name(meta["first_author"])
                and not is_collective_name(ref.first_author)
            )
            if not (supplied & people) and not uncomparable:
                add("first_author", ref.first_author, meta["first_author"])

    if ref.year and meta.get("year"):
        if ref.year.strip() != str(meta["year"]).strip():
            add("year", ref.year, str(meta["year"]))

    if ref.journal and meta.get("journal"):
        if not journal_matches(ref.journal, meta["journal"]):
            add("journal", ref.journal, meta["journal"])

    if ref.volume and meta.get("volume"):
        if norm_text(ref.volume) != norm_text(str(meta["volume"])):
            add("volume", ref.volume, str(meta["volume"]))

    if ref.issue and meta.get("issue"):
        if norm_text(ref.issue) != norm_text(str(meta["issue"])):
            add("issue", ref.issue, str(meta["issue"]))

    if ref.pages and meta.get("pages"):
        if not pages_match(ref.pages, str(meta["pages"])):
            add("pages", ref.pages, str(meta["pages"]))

    if ref.title and meta.get("title"):
        if title_similarity(ref.title, meta["title"]) < TITLE_MATCH_THRESHOLD:
            add("title", ref.title, meta["title"])

    return issues


def decide_status(result: VerifyResult, resolved_anything: bool) -> str:
    """
    Collapse the accumulated evidence into a single status.

    `verified` means every check that this tool performs actually ran and
    agreed. It must never be returned when a lookup failed, because the
    headline check here is the bidirectional DOI<->PMID agreement: if CrossRef
    answers and Entrez times out, that check never happened. Reporting such an
    entry as `verified` would be exactly the "succeeded while being wrong"
    failure this tool exists to catch — and it would get *worse* under load,
    since NCBI returns 429 precisely when a bibliography is large.

    Hence `partial`: something resolved and nothing disagreed, but at least one
    source could not be reached, so the entry is not certified.
    """
    if not resolved_anything:
        return "error" if result.errors else "not_found"
    if result.issues:
        return "mismatch"
    if result.errors:
        return "partial"
    return "verified"
