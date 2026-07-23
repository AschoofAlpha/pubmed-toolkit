"""
Advisor profile: what the PubMed record says about being this person's student.

The report answers one question — what is it like to be this named researcher's
graduate student — from publication metadata alone. It is not a literature
search, and it does not score, rank or compare researchers. Citation counts,
h-index, journal impact factor, quartile and CAS partition are out of scope and
never appear in the output or in any intermediate file.

Layout:

  roles    Section 6 of docs/profile-metrics-spec.md — PI resolution, record
           exclusions, person keys, strata, affiliation signal.
  metrics  Section 7 — one pure function per metric, each returning its value
           together with the denominator it was computed over.
  report   Sections 5, 8 and 9 — gates, the verbatim caveat strings, and the
           Markdown plus JSON rendering.

The package is named `profile` inside `pubmed_toolkit`, which shadows a
standard-library module name at the top level. Absolute imports keep that legal,
but anything importing the stdlib profiler from inside this package must say
`import profile` at top level and mean it.
"""

from __future__ import annotations

from .caveats import CAVEATS, caveat
from .metrics import (
    activity_span,
    affiliation_strings,
    equal_contrib_occurrences,
    first_author_slots,
    lead_slot_partition,
    person_roster,
    pi_byline_positions,
    records_per_year,
    roster_turnover,
    team_size,
    time_to_lead,
    titles_by_year,
    venue_repetition,
)
from .report import (
    build_report,
    build_report_from_path,
    check_corpus_gates,
    check_source_path,
    json_record,
    load_corpus,
    render_markdown,
    write_report,
)
from .roles import (
    affiliation_signal,
    apply_record_exclusions,
    build_people,
    default_gantt_exclude_names,
    is_collective_name,
    prepare_paper,
    resolve_pi,
)

__all__ = [
    "CAVEATS",
    "activity_span",
    "affiliation_signal",
    "affiliation_strings",
    "apply_record_exclusions",
    "build_people",
    "build_report",
    "build_report_from_path",
    "caveat",
    "check_corpus_gates",
    "check_source_path",
    "default_gantt_exclude_names",
    "equal_contrib_occurrences",
    "first_author_slots",
    "is_collective_name",
    "json_record",
    "lead_slot_partition",
    "load_corpus",
    "person_roster",
    "pi_byline_positions",
    "prepare_paper",
    "records_per_year",
    "render_markdown",
    "resolve_pi",
    "roster_turnover",
    "team_size",
    "time_to_lead",
    "titles_by_year",
    "venue_repetition",
    "write_report",
]
