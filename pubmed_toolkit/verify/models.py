"""Data models for reference verification."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# Fields that are compared against canonical metadata, in report order.
COMPARABLE_FIELDS = ("first_author", "year", "journal", "volume", "issue", "pages", "title")


@dataclass
class Reference:
    """One bibliography entry as supplied by the user."""

    key: str
    title: str = ""
    first_author: str = ""
    year: str = ""
    journal: str = ""
    volume: str = ""
    issue: str = ""
    pages: str = ""
    doi: str = ""
    pmid: str = ""
    entry_type: str = "article"

    def has_identifier(self) -> bool:
        return bool(self.doi or self.pmid)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Issue:
    """A single discrepancy between the supplied entry and canonical metadata."""

    field: str
    supplied: str
    canonical: str
    source: str          # "crossref" | "pubmed" | "cross-id"
    severity: str = "mismatch"   # "mismatch" | "missing" | "conflict"

    def describe(self) -> str:
        return (
            f"{self.field}: supplied={self.supplied!r} "
            f"{self.source}={self.canonical!r}"
        )


@dataclass
class VerifyResult:
    """Outcome of verifying one reference."""

    key: str
    status: str = "unchecked"
    # verified   — resolved, every check ran, everything agreed
    # partial    — resolved and nothing disagreed, but a lookup failed, so at
    #              least one check (possibly the DOI<->PMID cross-check) never
    #              ran. Deliberately not `verified`: certifying an entry whose
    #              headline check was skipped is the exact failure this tool
    #              exists to catch, and it would worsen under load because NCBI
    #              returns 429 precisely on large bibliographies.
    # mismatch   — resolved but one or more fields disagree
    # not_found  — no canonical record, and nothing proven wrong
    # error      — nothing resolved and a lookup failed; verdict unknown

    issues: list[Issue] = field(default_factory=list)
    resolved_doi: str = ""
    resolved_pmid: str = ""
    crossref: dict[str, Any] = field(default_factory=dict)
    pubmed: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    # Which independent sources produced a record for this entry.
    sources_agreeing: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status == "verified"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["issues"] = [asdict(i) for i in self.issues]
        return data
