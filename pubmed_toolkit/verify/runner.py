"""
Concurrent verification orchestration and reporting.

Per reference the pipeline is:

  1. CrossRef: resolve by DOI, or search bibliographically when no DOI is given.
  2. PubMed:   resolve by supplied PMID; otherwise derive one from the DOI.
  3. Cross-check the two identifiers against each other (see checks.py).
  4. Compare every supplied field against whichever canonical records resolved.

Entries are processed concurrently and each one's failures are isolated, so a
single stalled request cannot hold up the batch.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from .checks import (
    TITLE_MATCH_THRESHOLD,
    compare_fields,
    cross_check_identifiers,
    decide_status,
    normalize_doi,
)
from .clients import CrossRefClient, EntrezClient, HttpJsonClient
from .models import Issue, Reference, VerifyResult
from .normalize import title_similarity

logger = logging.getLogger("pubmed_toolkit.verify")


class ReferenceVerifier:
    def __init__(
        self,
        email: str = "",
        ncbi_api_key: str = "",
        timeout: float = 12.0,
        max_workers: int = 6,
        use_pubmed: bool = True,
    ):
        self.http = HttpJsonClient(email=email, timeout=timeout)
        self.crossref = CrossRefClient(self.http)
        self.entrez = EntrezClient(self.http, api_key=ncbi_api_key)
        self.max_workers = max_workers
        self.use_pubmed = use_pubmed

        # Populated by _prefetch_pubmed before the per-entry pass. The two
        # "prefetched" sets record which identifiers were *asked about*, so a
        # miss can be told apart from an identifier that was never looked up:
        # the first is a finding, the second needs an individual request.
        self._doi_to_pmid: dict[str, str] = {}
        self._pmid_meta: dict[str, dict[str, Any]] = {}
        self._prefetched_dois: set[str] = set()
        self._prefetched_pmids: set[str] = set()

    # ------------------------------------------------------------------
    # single entry
    # ------------------------------------------------------------------
    def verify_one(self, ref: Reference) -> VerifyResult:
        result = VerifyResult(key=ref.key)

        crossref_meta = self._resolve_crossref(ref, result)
        pubmed_meta, derived_pmid = self._resolve_pubmed(ref, crossref_meta, result)

        # Bidirectional identifier agreement — the strongest signal available.
        result.issues.extend(cross_check_identifiers(ref, derived_pmid, pubmed_meta))

        if crossref_meta:
            result.issues.extend(compare_fields(ref, crossref_meta, "crossref"))
            result.sources_agreeing.append("crossref")
        if pubmed_meta:
            result.issues.extend(compare_fields(ref, pubmed_meta, "pubmed"))
            result.sources_agreeing.append("pubmed")

        result.crossref = crossref_meta or {}
        result.pubmed = pubmed_meta or {}
        result.status = decide_status(result, bool(crossref_meta or pubmed_meta))
        return result

    def _resolve_crossref(self, ref: Reference, result: VerifyResult) -> dict[str, Any]:
        """Resolve by DOI when available, else fall back to a title search."""
        if ref.doi:
            meta = self.crossref.by_doi(ref.doi)
            if "__error__" not in meta:
                result.resolved_doi = meta.get("doi", "") or ref.doi
                return meta
            result.errors.append(f"crossref/doi: {meta['__error__']}")
            if meta["__error__"] == "http_404":
                result.issues.append(Issue(
                    field="doi", supplied=ref.doi, canonical="(not registered)",
                    source="crossref", severity="missing",
                ))
                return {}

        if not ref.title:
            return {}

        candidates = self.crossref.search(ref.title, ref.first_author)
        for cand in candidates:
            if title_similarity(ref.title, cand.get("title", "")) >= TITLE_MATCH_THRESHOLD:
                result.resolved_doi = cand.get("doi", "")
                return cand
        # Searching successfully and matching nothing is a *result* ("this work
        # is not in CrossRef"), not an error. Books, national guidelines and
        # many non-English journals land here legitimately, so keeping it out of
        # `errors` is what lets decide_status() report `not_found` rather than
        # implying the lookup itself failed.
        return {}

    def _resolve_pubmed(
        self,
        ref: Reference,
        crossref_meta: dict[str, Any],
        result: VerifyResult,
    ) -> tuple[dict[str, Any], str]:
        """Return (pubmed metadata, PMID independently derived from the DOI)."""
        if not self.use_pubmed:
            return {}, ""

        # Forward direction: DOI -> PMID, resolved independently of what was
        # supplied. Served from the batch prefetch when the DOI was known up
        # front; entries whose DOI only emerged from a CrossRef title search
        # fall through to an individual lookup.
        doi_for_lookup = ref.doi or result.resolved_doi
        derived_pmid = ""
        if doi_for_lookup:
            key = doi_for_lookup.strip().lower()
            derived_pmid = self._doi_to_pmid.get(key, "")
            # A prefetched DOI that mapped to nothing has been answered; only a
            # DOI that was never in the batch needs its own request.
            if not derived_pmid and key not in self._prefetched_dois:
                derived_pmid = self.entrez.pmid_from_doi(doi_for_lookup)

        # Reverse direction: prefer the supplied PMID so a wrong one is exposed
        # rather than silently replaced by the derived one.
        pmid_for_lookup = ref.pmid.strip() or derived_pmid
        if not pmid_for_lookup:
            return {}, derived_pmid

        cached = self._pmid_meta.get(pmid_for_lookup)
        # A PMID that was prefetched but produced no record does not exist;
        # asking again individually only turns a finding into wasted latency.
        if cached is not None:
            meta = cached
        elif pmid_for_lookup in self._prefetched_pmids:
            meta = {"__error__": "pmid_not_found"}
        else:
            meta = self.entrez.by_pmid(pmid_for_lookup)

        if "__error__" in meta:
            result.errors.append(f"pubmed/esummary: {meta['__error__']}")
            if meta["__error__"] == "pmid_not_found" and ref.pmid:
                result.issues.append(Issue(
                    field="pmid", supplied=ref.pmid, canonical="(no such record)",
                    source="pubmed", severity="missing",
                ))
            return {}, derived_pmid

        result.resolved_pmid = meta.get("pmid", "")
        if not result.resolved_doi:
            result.resolved_doi = normalize_doi(meta.get("doi", ""))
        return meta, derived_pmid

    # ------------------------------------------------------------------
    # batch
    # ------------------------------------------------------------------
    def _prefetch_pubmed(self, refs: list[Reference]) -> None:
        """
        Resolve every known identifier up front, in batches.

        Entrez allows 3 requests/second (10 with a key), and that cap — not
        --max-workers — is what bounds throughput. Done one reference at a time
        this costs two calls each, so 500 references spend 5-6 minutes waiting
        on the rate limiter. Batching collapses that to a handful of requests.

        Correctness is unchanged: the same ESearch and ESummary endpoints answer
        the same questions, just several identifiers at a time.
        """
        if not self.use_pubmed:
            return

        dois = [r.doi.strip() for r in refs if r.doi and r.doi.strip()]
        if dois:
            self._doi_to_pmid = self.entrez.batch_pmids_from_dois(dois)
            self._prefetched_dois = {d.lower() for d in dois}

        wanted = {r.pmid.strip() for r in refs if r.pmid and r.pmid.strip()}
        wanted |= set(self._doi_to_pmid.values())
        if wanted:
            self._pmid_meta = self.entrez.batch_summaries(sorted(wanted))
            self._prefetched_pmids = wanted

        logger.debug("prefetched %d DOI mappings and %d PubMed records",
                     len(self._doi_to_pmid), len(self._pmid_meta))

    def verify_all(self, refs: Iterable[Reference]) -> list[VerifyResult]:
        refs = list(refs)
        self._prefetch_pubmed(refs)
        results: list[VerifyResult] = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futures = {pool.submit(self._safe_verify, r): r for r in refs}
            for i, future in enumerate(as_completed(futures), 1):
                result = future.result()
                results.append(result)
                logger.info("[%d/%d] %-28s %s", i, len(refs), result.key, result.status)
        order = {r.key: i for i, r in enumerate(refs)}
        results.sort(key=lambda r: order.get(r.key, 0))
        return results

    def _safe_verify(self, ref: Reference) -> VerifyResult:
        try:
            return self.verify_one(ref)
        except Exception as e:  # noqa: BLE001 - one bad entry must not kill the run
            logger.error("verify failed for %s: %s: %s", ref.key, type(e).__name__, e)
            return VerifyResult(key=ref.key, status="error",
                                errors=[f"{type(e).__name__}: {e}"])


# ----------------------------------------------------------------------
# reporting
# ----------------------------------------------------------------------
def _has(result: VerifyResult, severity: str) -> bool:
    return any(i.severity == severity for i in result.issues)


def summarize(results: list[VerifyResult]) -> dict[str, int]:
    counts = {"verified": 0, "partial": 0, "mismatch": 0, "not_found": 0, "error": 0}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1
    counts["conflicts"] = sum(1 for r in results if _has(r, "conflict"))
    # Unregistered DOIs / nonexistent PMIDs are counted separately: they are the
    # signature of a fabricated citation, and they can be attached to results
    # whose status is not_found or error, so a status-only tally would hide them.
    counts["unresolvable_ids"] = sum(1 for r in results if _has(r, "missing"))
    counts["incomplete"] = sum(1 for r in results if r.errors)
    counts["total"] = len(results)
    return counts


def write_json_report(results: list[VerifyResult], path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {"summary": summarize(results), "results": [r.to_dict() for r in results]}
    p.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return p


def write_markdown_report(results: list[VerifyResult], path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    s = summarize(results)

    lines = [
        "# Reference verification report",
        "",
        f"- Entries checked: **{s['total']}**",
        f"- Verified: **{s['verified']}**",
        f"- Identifier conflicts: **{s['conflicts']}**",
        f"- Unregistered identifiers: **{s['unresolvable_ids']}**",
        f"- Field mismatches: **{s['mismatch']}**",
        f"- Partially checked: **{s['partial']}**",
        f"- Not found: **{s['not_found']}**",
        f"- Errors: **{s['error']}**",
        "",
    ]
    if s["incomplete"]:
        lines += [
            f"> {s['incomplete']} of {s['total']} entries had at least one lookup fail, "
            "so not every check ran on them. They are never counted as verified.",
            "",
        ]

    # Sections are keyed on the findings themselves, not on the entry status,
    # because a definite finding (an unregistered DOI) can sit on an entry whose
    # status is not_found or error. Filtering by status hid exactly the finding
    # this tool exists to surface.
    conflicts = [r for r in results if _has(r, "conflict")]
    if conflicts:
        lines += [
            "## Identifier conflicts",
            "",
            "The DOI and the PMID in these entries resolve to *different* papers.",
            "At least one identifier was not taken from the work being cited.",
            "",
            "| Key | Field | In bibliography | Independently resolved |",
            "| --- | --- | --- | --- |",
        ]
        for r in conflicts:
            for i in r.issues:
                if i.severity == "conflict":
                    lines.append(f"| `{r.key}` | {i.field} | `{i.supplied}` | `{i.canonical}` |")
        lines.append("")

    unregistered = [r for r in results if _has(r, "missing")]
    if unregistered:
        lines += [
            "## Unregistered identifiers",
            "",
            "These identifiers do not exist. A DOI that is not registered with",
            "CrossRef, or a PMID with no PubMed record, is not a coverage gap —",
            "it is a citation pointing at nothing.",
            "",
            "| Key | Field | In bibliography | Lookup result |",
            "| --- | --- | --- | --- |",
        ]
        for r in unregistered:
            for i in r.issues:
                if i.severity == "missing":
                    lines.append(f"| `{r.key}` | {i.field} | `{i.supplied}` | {i.canonical} |")
        lines.append("")

    mismatched = [
        r for r in results
        if _has(r, "mismatch") and not _has(r, "conflict") and not _has(r, "missing")
    ]
    if mismatched:
        lines += ["## Field mismatches", "",
                  "| Key | Field | In bibliography | Canonical | Source |",
                  "| --- | --- | --- | --- | --- |"]
        for r in mismatched:
            for i in r.issues:
                if i.severity == "mismatch":
                    sup = str(i.supplied)[:60]
                    can = str(i.canonical)[:60]
                    lines.append(f"| `{r.key}` | {i.field} | {sup} | {can} | {i.source} |")
        lines.append("")

    partial = [r for r in results if r.status == "partial"]
    if partial:
        lines += ["## Partially checked", "",
                  "Something resolved and nothing disagreed, but a lookup failed, so",
                  "at least one check — possibly the DOI/PMID cross-check — did not run.",
                  "Re-run these before treating them as clean.",
                  "",
                  "| Key | What failed |", "| --- | --- |"]
        for r in partial:
            lines.append(f"| `{r.key}` | {'; '.join(r.errors)[:90]} |")
        lines.append("")

    # Only entries with no definite finding at all belong here.
    unresolved = [
        r for r in results
        if r.status in ("not_found", "error") and not r.issues
    ]
    if unresolved:
        lines += ["## Unresolved", "",
                  "No canonical record, and no identifier was proven wrong. Often",
                  "legitimate — books, guidelines, standards and many non-English",
                  "journals are simply absent from CrossRef and PubMed.",
                  "",
                  "| Key | Status | Detail |", "| --- | --- | --- |"]
        for r in unresolved:
            detail = "; ".join(r.errors)[:80] if r.errors else "no matching record"
            lines.append(f"| `{r.key}` | {r.status} | {detail} |")
        lines.append("")

    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p
