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

  svg      Domain-free SVG primitives (docs/profile-visual-spec.md Section 3).
  charts   The five figures, each a pure metric-dict-to-SVG-string function.
  html_report  The reading surface: one self-contained .html carrying the same
           numbers, the figures inline, and every caveat uncollapsed.

`charts.figures_for_report` is deliberately not re-exported here. `cmd_profile`
guards its import so that a drawing layer which will not load costs the reader
five figures instead of the whole report; re-exporting it would run that import
as a side effect of importing this package and make the guard unreachable.
Import it by module path: `from pubmed_toolkit.profile.charts import ...`.

The package is named `profile` inside `pubmed_toolkit`, which shadows a
standard-library module name at the top level. Absolute imports keep that legal,
but anything importing the stdlib profiler from inside this package must say
`import profile` at top level and mean it.
"""

from __future__ import annotations

from .caveats import CAVEATS, caveat
from .html_report import render_html, write_html
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
    "render_html",
    "render_markdown",
    "resolve_pi",
    "roster_turnover",
    "team_size",
    "time_to_lead",
    "titles_by_year",
    "venue_repetition",
    "write_html",
    "write_report",
]
