"""Reference verification against CrossRef and PubMed."""

from .bibtex import load_bibtex, load_json_refs, parse_bibtex
from .checks import compare_fields, cross_check_identifiers
from .models import Issue, Reference, VerifyResult
from .runner import (
    ReferenceVerifier,
    summarize,
    write_json_report,
    write_markdown_report,
)

__all__ = [
    "Reference",
    "Issue",
    "VerifyResult",
    "ReferenceVerifier",
    "load_bibtex",
    "load_json_refs",
    "parse_bibtex",
    "compare_fields",
    "cross_check_identifiers",
    "summarize",
    "write_json_report",
    "write_markdown_report",
]
