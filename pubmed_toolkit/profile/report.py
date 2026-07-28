"""
Rendering for the advisor profile report.

Owns the corpus gates and the section ordering that turns metric dicts into a
Markdown document plus a JSON record of the same numbers. The caveat strings it
renders come from `caveats.py` unchanged.

This module draws nothing. The activity timeline is an inline SVG in the HTML
report (`charts.person_timeline_chart`); `build_report` keeps `gantt_path` so a
caller holding a raster of its own (`analyze`) can still point at one.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from . import metrics as M
from .caveats import DROPPED_REGISTER, caveat
from .roles import apply_record_exclusions, build_people, prepare_paper

SCHEMA_VERSION = 1

DEFAULT_ADVISOR_CONFIG: dict[str, Any] = {"exclude_names": [], "lag_years": 3}

# Section 6.4. The only permitted labels. No field in PubMed separates a PhD
# student from a postdoc, technician, staff scientist, clinical fellow, rotation
# student or visiting scholar, so the report never claims to.
STRATUM_LABEL = {
    "A": "lead-trainee candidate",
    "B": "support candidate",
    "C": "single appearance",
    "D": "senior collaborator",
    "unclassified": "unclassified",
}

# --- Gates ---

# Name and refusal message per gate, in one mapping so the two cannot drift apart.
GATES: dict[str, tuple[str, str]] = {
    "G1": ("truncation",
           "esearch matched {count} records but only {returned} were retrieved. Every count in this "
           "report would be wrong by an unbounded amount. Raise retmax, reduce years_back, or add "
           "affiliation_keywords, then re-fetch."),
    "G2": ("identity fallback",
           "No paper passed identity verification. The corpus is 'every paper by anyone sharing this "
           "name' and describes several different researchers. Configure orcid, affiliation_keywords, "
           "or email_domains and re-fetch."),
    "G3": ("weak identity config",
           "No identity evidence is configured, so the corpus is a name match only. For any common "
           "surname this blends several people. Set at least one of orcid / affiliation_keywords / "
           "email_domains."),
    "G4": ("no structured authors",
           "Corpus lacks structured author records. Run the profile fetch stage; the report cannot be "
           "built from the Excel export."),
    "G5": ("empty corpus", "0 papers remain after exclusions. Nothing can be reported."),
}


def _gate(gate_id: str, observed: dict[str, Any], **fields: Any) -> dict[str, Any]:
    name, message = GATES[gate_id]
    return {
        "id": gate_id,
        "name": name,
        "message": message.format(**fields),
        "observed": observed,
    }


def check_corpus_gates(corpus: dict[str, Any]) -> dict[str, Any] | None:
    """
    Gates G1-G4, evaluated before anything is computed. G5 needs the record
    exclusions and fires later.

    There is no degrade-with-a-warning path. A warning gets scrolled past; a
    missing report does not.
    """
    query = corpus.get("query") or {}
    count = int(query.get("esearch_count") or 0)
    returned = int(query.get("pmids_returned") or 0)
    if count > returned:
        return _gate("G1", {"esearch_count": count, "pmids_returned": returned},
                     count=count, returned=returned)

    if bool(corpus.get("fallback_fired")):
        return _gate("G2", {"fallback_fired": True})

    identity = corpus.get("identity") or {}
    if not (identity.get("orcid") or "").strip() \
            and not (identity.get("affiliation_keywords") or []) \
            and not (identity.get("email_domains") or []):
        return _gate("G3", {
            "orcid": identity.get("orcid", ""),
            "affiliation_keywords": identity.get("affiliation_keywords", []),
            "email_domains": identity.get("email_domains", []),
        })

    papers = corpus.get("papers")
    if not isinstance(papers, list):
        return _gate("G4", {"papers": type(papers).__name__})
    for paper in papers:
        authors = paper.get("authors") if isinstance(paper, dict) else None
        if not isinstance(authors, list) or not authors or not all(isinstance(a, dict) for a in authors):
            return _gate("G4", {"pmid": (paper or {}).get("pmid", "?") if isinstance(paper, dict) else "?"})
    return None


_SPREADSHEET_SUFFIXES = {".xlsx", ".xlsm", ".xls", ".csv"}


def check_source_path(path: str | Path) -> dict[str, Any] | None:
    """
    G4 for the Excel export, decided from the extension so the file is never
    opened.

    `build_author_records` silently falls back to splitting `authors_str` when a
    record has no PMID match, which forces equal_contrib=False,
    is_corresponding=False and affiliation="" for every author. That converts
    "unknown" into a confident zero, which is the most dangerous silent failure
    in the pipeline — so the report refuses to start from a spreadsheet at all.
    """
    if Path(path).suffix.lower() in _SPREADSHEET_SUFFIXES:
        return _gate("G4", {"path": str(path)})
    return None


# --- Corpus loading and window derivation ---


def load_corpus(path: str | Path) -> dict[str, Any]:
    """Read one advisor corpus JSON. The only file this module ever opens."""
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Advisor corpus must be a JSON object: {path}")
    return data


def _year_in(text: Any) -> int | None:
    match = re.search(r"(\d{4})", str(text or ""))
    return int(match.group(1)) if match else None


def window_years(corpus: dict[str, Any], papers: Sequence[dict[str, Any]]) -> tuple[int, int]:
    """
    Window bounds from the recorded query, falling back to the corpus itself.

    Taking them from the query rather than from the data matters for censoring:
    a person whose first paper is the earliest in the corpus is only
    left-censored if the window actually starts there.
    """
    query = corpus.get("query") or {}
    years = [paper["year"] for paper in papers]
    start = _year_in(query.get("mindate"))
    end = _year_in(query.get("maxdate"))
    if start is None:
        start = min(years) if years else 0
    if end is None:
        end = max(years) if years else start
    return start, max(start, end)


# --- Report construction ---


def _section(
    section_id: int,
    title: str,
    body: Sequence[str] = (),
    caveats: Sequence[str] = (),
    prose: Sequence[str] = (),
) -> dict[str, Any]:
    """
    One rendered section.

    `body` holds computed values, `prose` and `caveats` hold fixed text. The
    split exists so a test can scan the computed half for prohibited quantities
    without tripping over the caveats that name those same quantities in order
    to rule them out.
    """
    return {
        "id": section_id,
        "title": title,
        "body": list(body),
        "caveats": list(caveats),
        "prose": list(prose),
    }


def _fmt_number(value: float | None) -> str:
    if value is None:
        return "n/a"
    return str(int(value)) if float(value).is_integer() else f"{value:.1f}"


def _fmt_person(entry: dict[str, Any]) -> str:
    return f"{entry['name']}{entry.get('marker', '')}".strip()


def _pmid_list(pmids: Sequence[str]) -> str:
    return ", ".join(pmids) if pmids else "none"


def build_report(
    corpus: dict[str, Any],
    config: dict[str, Any] | None = None,
    gantt_path: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """
    Build the whole report from one corpus dict.

    Returns a dict carrying the metric values, the rendered sections, and
    `refused`/`exit_code` so a caller can honour a fired gate without inspecting
    the text.
    """
    now = now or datetime.now()
    config = config or {}
    advisor = {**DEFAULT_ADVISOR_CONFIG, **(config.get("advisor") or {})}
    identity = corpus.get("identity") or {}
    author_name = identity.get("author_name", "") or config.get("author_name", "")

    gate = check_corpus_gates(corpus)
    if gate:
        return _refusal(gate, author_name, now)

    prepared = [prepare_paper(paper, identity) for paper in corpus["papers"]]
    exclusions = apply_record_exclusions(prepared)
    kept = exclusions["kept"]
    records_only = exclusions["records_only"]
    if not kept:
        return _refusal(_gate("G5", {"papers_after_exclusions": 0}), author_name, now)

    start_year, end_year = window_years(corpus, kept + records_only)
    people_data = build_people(
        kept, identity, advisor["exclude_names"], start_year, end_year
    )
    people = people_data["people"]
    lead_stratum = people_data["lead_stratum_by_pmid"]
    position_filtered = bool(corpus.get("position_filtered", True))

    partition = M.lead_slot_partition(people, end_year, advisor["lag_years"])
    computed = {
        "s2": M.person_roster(people, people_data["n_strict"], people_data["n_loose"]),
        "s3a": M.first_author_slots(kept, lead_stratum),
        "s3b": partition,
        "s4": M.time_to_lead(people, partition),
        "s5": M.activity_span(people),
        "s6": M.roster_turnover(people, start_year, end_year),
        "s7": M.pi_byline_positions(kept, position_filtered),
        "s8": M.equal_contrib_occurrences(kept),
        "s9": M.records_per_year(kept, records_only, start_year, end_year),
        "s10": M.team_size(kept, lead_stratum),
        "s11": M.venue_repetition(kept),
        "s12": M.affiliation_strings(kept, start_year, end_year),
        "s13": M.titles_by_year(kept),
    }

    counts = corpus.get("counts") or {}
    provenance = {
        "author_name": author_name,
        "query": corpus.get("query") or {},
        "identity": {
            "orcid": identity.get("orcid", ""),
            "affiliation_keywords": identity.get("affiliation_keywords", []),
            "email_domains": identity.get("email_domains", []),
            "require_affiliation_effective": identity.get("require_affiliation_effective", "unknown"),
        },
        "counts": counts,
        "fallback_fired": bool(corpus.get("fallback_fired")),
        "position_filtered": position_filtered,
        "window_start_year": start_year,
        "window_end_year": end_year,
        "lag_years": advisor["lag_years"],
        "exclude_names": list(advisor["exclude_names"]),
        "corpus_size": len(kept),
        "records_only_size": len(records_only),
        "exclusions": exclusions["excluded"],
        "title_duplicates": exclusions["title_duplicates"],
        "slot0_collective_pmids": exclusions["slot0_collective_pmids"],
        "sole_author_papers": people_data["sole_author_papers"],
        "ambiguous_pi_papers": [p["pmid"] for p in kept if p["pi_ambiguous"]],
        "n_strict": people_data["n_strict"],
        "n_loose": people_data["n_loose"],
        "n_people": len(people),
        "flips": people_data["flips"],
    }

    used_caveats: dict[str, str] = {}
    sections = _build_sections(provenance, computed, used_caveats, gantt_path)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now.isoformat(timespec="seconds"),
        "author_name": author_name,
        "refused": False,
        "exit_code": 0,
        "gate": None,
        "gantt_path": str(gantt_path) if gantt_path else None,
        "provenance": provenance,
        "metrics": computed,
        "caveats": used_caveats,
        "sections": sections,
    }


def _refusal(gate: dict[str, Any], author_name: str, now: datetime) -> dict[str, Any]:
    """A fired gate produces the gate, the observed values and the fix. Nothing else."""
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now.isoformat(timespec="seconds"),
        "author_name": author_name,
        "refused": True,
        "exit_code": 1,
        "gate": gate,
        "gantt_path": None,
        "provenance": {},
        "metrics": {},
        "caveats": {},
        "sections": [],
    }


def build_report_from_path(
    path: str | Path,
    config: dict[str, Any] | None = None,
    gantt_path: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Load a corpus file and build the report, refusing spreadsheets unopened."""
    gate = check_source_path(path)
    if gate:
        return _refusal(gate, (config or {}).get("author_name", ""), now or datetime.now())
    return build_report(load_corpus(path), config, gantt_path, now)


# --- Sections ---


def _build_sections(
    prov: dict[str, Any],
    computed: dict[str, Any],
    used: dict[str, str],
    gantt_path: str | Path | None,
) -> list[dict[str, Any]]:
    def cav(caveat_id: str, **fields: Any) -> str:
        text = caveat(caveat_id, **fields)
        used[caveat_id] = text
        return text

    query = prov["query"]
    years_back = query.get("years_back", "?")
    name_only = (prov["counts"] or {}).get("name_only", 0)

    sections = [
        # Section 0 precedes provenance because the limits reframe every number
        # that follows.
        _section(0, "What this report is and is not", prose=[cav("CAV-00")]),
        _section(1, "Corpus provenance", body=_provenance_body(prov),
                 caveats=[cav("CAV-01", n=name_only),
                          cav("CAV-02", n_strict=prov["n_strict"], n_loose=prov["n_loose"])]),
        _section(2, "People and activity timeline",
                 body=_roster_body(computed["s2"], gantt_path),
                 caveats=[used["CAV-02"], cav("CAV-03")]),
        _section(3, "First-author slots",
                 body=_first_author_body(computed["s3a"], computed["s3b"]),
                 caveats=[cav("CAV-04"), cav("CAV-05"), cav("CAV-06")]),
        _section(4, "Time to a first-author slot", body=_time_to_lead_body(computed["s4"]),
                 caveats=[cav("CAV-07"), cav("CAV-08")]),
        _section(5, "Observed activity span",
                 body=_span_body(computed["s5"], prov["flips"]),
                 caveats=[cav("CAV-09"), cav("CAV-10", years_back=years_back), cav("CAV-11")]),
        _section(6, "Group size and turnover", body=_turnover_body(computed["s6"]),
                 caveats=[cav("CAV-12")]),
        _section(7, "The PI's own byline position", body=_pi_position_body(computed["s7"]),
                 caveats=(
                     [cav("CAV-13")] if not computed["s7"]["measured"] else []
                 ) + [
                     cav("CAV-14"),
                     cav("CAV-15",
                         covered=computed["s7"]["email_coverage"]["covered"],
                         total=computed["s7"]["email_coverage"]["denominator"]),
                 ]),
        _section(8, "Shared-authorship flags", body=_equal_contrib_body(computed["s8"]),
                 caveats=[cav("CAV-16")]),
        _section(9, "Records per year", body=_records_body(computed["s9"]),
                 caveats=[cav("CAV-17"), cav("CAV-18")]),
        _section(10, "Team size", body=_team_size_body(computed["s10"]), caveats=[cav("CAV-19")]),
        _section(11, "Venues", body=_venue_body(computed["s11"]), caveats=[cav("CAV-20")]),
        _section(12, "Affiliation strings", body=_affiliation_body(computed["s12"]),
                 caveats=[cav("CAV-21")]),
        _section(13, "Titles by year", body=_titles_body(computed["s13"]), caveats=[cav("CAV-22")]),
        _section(14, "What was deliberately not computed",
                 prose=[f"- **{name}** — {reason}" for name, reason in DROPPED_REGISTER]),
    ]
    return sections


def _provenance_body(prov: dict[str, Any]) -> list[str]:
    query = prov["query"]
    counts = prov["counts"] or {}
    by_evidence = counts.get("by_evidence") or {}
    lines = [
        f"- esearch term: `{query.get('term', '')}`",
        f"- date range: {query.get('mindate', '?')} to {query.get('maxdate', '?')} "
        f"(years_back={query.get('years_back', '?')})",
        f"- retmax {query.get('retmax', '?')}; esearch matched {query.get('esearch_count', '?')}; "
        f"PMIDs returned {query.get('pmids_returned', '?')}; truncated: {query.get('truncated', False)}",
        f"- fetched {counts.get('fetched', '?')} / verified {counts.get('verified', '?')} / "
        f"name_only {counts.get('name_only', 0)} / rejected {counts.get('rejected', '?')}",
        "- verified by evidence tier: "
        + (", ".join(f"{tier} {value}" for tier, value in sorted(by_evidence.items())) or "not recorded"),
        f"- identity: orcid={prov['identity']['orcid'] or '(none)'}; "
        f"affiliation_keywords={len(prov['identity']['affiliation_keywords'])}; "
        f"email_domains={len(prov['identity']['email_domains'])}",
        f"- effective require_affiliation: {prov['identity']['require_affiliation_effective']}",
        f"- position_filtered: {prov['position_filtered']}",
        f"- identity fallback fired: {prov['fallback_fired']}",
        f"- window used: {prov['window_start_year']} to {prov['window_end_year']}",
        f"- records usable after exclusions: {prov['corpus_size']} "
        f"(plus {prov['records_only_size']} counted only in records-per-year)",
        "",
        "Record exclusions (Section 6.5):",
    ]
    for reason, pmids in prov["exclusions"].items():
        lines.append(f"- {reason}: {len(pmids)} — {_pmid_list(pmids)}")
    lines += [
        "",
        f"- title-identical records flagged but not merged: {len(prov['title_duplicates'])} "
        f"group(s) — {'; '.join(', '.join(g) for g in prov['title_duplicates']) or 'none'}",
        f"- consortium in the lead slot: {len(prov['slot0_collective_pmids'])} — "
        f"{_pmid_list(prov['slot0_collective_pmids'])}",
        f"- sole-author records (the author is forced into the senior slot by the last-author rule): "
        f"{len(prov['sole_author_papers'])} — {_pmid_list(prov['sole_author_papers'])}",
        f"- records where two byline entries matched the target name at the same evidence tier: "
        f"{len(prov['ambiguous_pi_papers'])} — {_pmid_list(prov['ambiguous_pi_papers'])}",
        f"- configured name exclusions: {_pmid_list(prov['exclude_names'])}",
        "",
        f"- people found: {prov['n_people']}; strict keying finds {prov['n_strict']}, "
        f"loose keying finds {prov['n_loose']}",
    ]
    return lines


def _roster_body(roster: dict[str, Any], gantt_path: str | Path | None) -> list[str]:
    lines = [
        f"{roster['denominator']} people, after removing the target researcher, consortium entries "
        f"and configured exclusions.",
        "",
        "| person | position label | affiliation signal | appearances | lead slots | "
        "equal-contribution flags | first | last | censoring | notes |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in roster["rows"]:
        censoring = ", ".join(
            label for label, flag in (("left", row["left_censored"]), ("right", row["right_censored"])) if flag
        ) or "none"
        lines.append(
            f"| {row['name']}{row['marker']} | {STRATUM_LABEL[row['stratum']]} | "
            f"{row['affiliation_signal']} | {row['n_appearances']} | {row['n_first_slots']} | "
            f"{row['n_equal_contrib']} | {row['first_year']} | {row['last_year']} | {censoring} | "
            f"{', '.join(row['flags']) or '-'} |"
        )
    lines += [
        "",
        "Rows are ordered by first appearance, then by name. They are never ordered by any count.",
        "",
        "By position label: " + ", ".join(
            f"{STRATUM_LABEL[key]} {value}" for key, value in roster["by_stratum"].items()
        ),
    ]
    if gantt_path:
        lines += ["", f"![Person activity timeline]({Path(gantt_path).name})",
                  f"Timeline rendered by analysis.render_gantt: `{gantt_path}`"]
    else:
        # Markdown cannot hold an inline SVG; an unexplained absence would be worse.
        lines += ["", "The activity timeline is drawn in the HTML report beside this file "
                  "(`advisor_profile_*.html`, Section 2), one row per person in the cohort "
                  "every aggregate below is computed over."]
    return lines


def _first_author_body(slots: dict[str, Any], partition: dict[str, Any]) -> list[str]:
    lines = ["**Paper side — who occupies the lead slot.**", ""]
    if slots["not_computable"]:
        lines.append("not computable: the PI is first author on every corpus paper")
    elif slots["suppressed"]:
        lines += [
            f"Only {slots['denominator']} eligible records, which is below the minimum for an "
            f"aggregate. The records are listed instead:",
            "",
            "| PMID | year | lead author | position label |",
            "|---|---|---|---|",
        ]
        for row in slots["rows"]:
            lines.append(
                f"| {row['pmid']} | {row['year']} | {row['lead_name']} | {STRATUM_LABEL[row['stratum']]} |"
            )
    else:
        for key, count in slots["counts"].items():
            pct = (slots["percentages"] or {}).get(key)
            suffix = f" ({pct}%)" if pct is not None else ""
            lines.append(f"- {STRATUM_LABEL[key]}: {count} of {slots['denominator']} records{suffix}")
    if not slots["not_computable"]:
        # Withheld when the eligible set is empty: the spec requires that case to
        # print its one sentence and no counts at all, including zeros.
        lines += [
            "",
            f"Eligible records exclude {len(slots['dropped_pi_is_lead'])} where the target researcher "
            f"holds the lead slot and {len(slots['dropped_slot0_collective'])} where a consortium does.",
        ]
    lines += [
        "",
        "**Person side — who has ever led a paper.**",
        "",
        f"- holds at least one lead slot: {partition['counts']['holds_lead']} of "
        f"{partition['denominator']}",
        f"- no lead slot, first seen at least {partition['lag_years']} years before the window end: "
        f"{partition['counts']['observed_without_lead']} of {partition['denominator']}",
        f"- no lead slot, first seen inside the trailing {partition['lag_years']} years, so too recent "
        f"to tell: {partition['counts']['too_recent']} of {partition['denominator']}",
        "",
        "This is a count partition, not a rate, and no proportion is computed from it at any sample size.",
    ]
    return lines


def _time_to_lead_body(result: dict[str, Any]) -> list[str]:
    if result["not_computable"]:
        lines = ["no person in this corpus holds a first-author slot"]
    else:
        lines = [f"Years from first appearance to first lead slot, over {result['denominator']} people.", ""]
        for lag, count in result["distribution"].items():
            lines.append(f"- {lag} year(s): {count} of {result['denominator']} people")
        lines.append(f"- at 0 years (debuted in the lead slot): {result['count_at_zero']} of {result['denominator']}")
        if result["suppressed"]:
            lines += ["", f"Below the minimum for a median at n={result['denominator']}; the values are:"]
            lines += [f"- {_fmt_person(item)}: {item['lag_years']} year(s)" for item in result["values"]]
        else:
            lines += ["", f"Median: {_fmt_number(result['median'])} year(s), over {result['denominator']} people."]
    lines += ["", "People with no lead slot yet, printed beside the figure above:"]
    if result["still_without_lead"]:
        lines += [
            f"- {_fmt_person(item)}: observed {item['years_observed']} year(s), no lead slot"
            for item in result["still_without_lead"]
        ]
    else:
        lines.append("- none")
    return lines


def _span_body(result: dict[str, Any], flips: Sequence[dict[str, Any]]) -> list[str]:
    lines = [
        f"Cohort: {result['cohort_denominator']} people. "
        f"Single-appearance people are counted separately ({result['single_appearance_count']}) and are "
        f"never given a span.",
        "",
        "Censoring: " + ", ".join(f"{key} {value}" for key, value in result["buckets"].items()),
        "",
    ]
    if result["suppressed"]:
        lines += [
            f"Only {result['denominator']} uncensored spans, below the minimum for a median. "
            f"The values are:",
        ]
    else:
        low, high = result["iqr"]
        lines += [
            f"Median span: {_fmt_number(result['median'])} year(s) over {result['denominator']} "
            f"uncensored people; IQR {_fmt_number(low)} to {_fmt_number(high)}.",
            "",
            "Per person:",
        ]
    for item in result["values"]:
        span = f"{item['span_years']}"
        if item["same_year"]:
            span = "0 (same year)"
        lines.append(
            f"- {_fmt_person(item)}: span {span} year(s) "
            f"[{item['first_year']}-{item['last_year']}, {item['bucket']}]"
        )
    lines += ["", "People who held a lead slot and later took the senior slot:"]
    if flips:
        lines += [
            f"- {_fmt_person(flip)}: lead slot from {flip['first_lead_year']}, "
            f"senior slot from {flip['first_last_year']}"
            for flip in flips
        ]
    else:
        lines.append("- none observed in this window")
    return lines


def _turnover_body(result: dict[str, Any]) -> list[str]:
    lines = [
        "| year | active | arrivals | latest appearance |",
        "|---|---|---|---|",
    ]
    for row in result["years"]:
        note = " (right-censored — not departures)" if row["departures_right_censored"] else ""
        lines.append(f"| {row['year']} | {row['active']} | {row['arrivals']} | {row['departures']}{note} |")
    lines += ["", f"Counts are over the {result['denominator']} people in the roster."]
    return lines


def _pi_position_body(result: dict[str, Any]) -> list[str]:
    if not result["measured"]:
        return ["Not measured on this corpus; see the caveat below."]
    coverage = result["email_coverage"]
    lines = []
    if result["suppressed"]:
        lines += [
            f"Only {result['denominator']} records, below the minimum for an aggregate. "
            f"Per record:",
            "",
            "| PMID | year | byline position |",
            "|---|---|---|",
        ]
        lines += [f"| {row['pmid']} | {row['year']} | {row['position']} |" for row in result["rows"]]
    else:
        for key, count in result["counts"].items():
            pct = (result["percentages"] or {}).get(key)
            suffix = f" ({pct}%)" if pct is not None else ""
            lines.append(f"- {key}: {count} of {result['denominator']} records{suffix}")
    lines += ["", "Heuristic, reported beside its own coverage:"]
    if result["corresponding"] is None:
        lines.append(
            f"- corresponding-author flag: suppressed. Email coverage is "
            f"{coverage['covered']} of {coverage['denominator']} records, so the flag is False for "
            f"everyone for reasons unrelated to this researcher."
        )
    else:
        lines.append(
            f"- the target researcher's own entry carries the corresponding-author flag on "
            f"{result['corresponding']['count']} of {result['corresponding']['denominator']} records; "
            f"email coverage is {coverage['covered']} of {coverage['denominator']} records"
        )
    return lines


def _equal_contrib_body(result: dict[str, Any]) -> list[str]:
    if result["not_measurable"]:
        return ["not measurable in this corpus"]
    lines = [
        f"{result['count']} of {result['denominator']} records carry the equal-contribution attribute.",
        "",
    ]
    for category, count in result["categories"].items():
        lines.append(f"- {category.replace('_', ' ')}: {count} of {result['count']} flagged records")
    lines += ["", "| PMID | year | flagged group size | includes lead slot | includes senior slot |", "|---|---|---|---|---|"]
    for row in result["papers"]:
        lines.append(
            f"| {row['pmid']} | {row['year']} | {row['group_size']} | "
            f"{row['includes_first']} | {row['includes_last']} |"
        )
    return lines


def _records_body(result: dict[str, Any]) -> list[str]:
    lines = [f"{result['denominator']} records in total.", ""]
    for row in result["years"]:
        notes = []
        if row["partial"]:
            notes.append("PARTIAL")
        if row["indexing_lag"]:
            notes.append("subject to PubMed indexing lag")
        suffix = f"  ({'; '.join(notes)})" if notes else ""
        lines.append(f"- {row['year']}: {row['count']}{suffix}")
    return lines


def _team_size_body(result: dict[str, Any]) -> list[str]:
    lines = []
    if result["suppressed"]:
        lines += [
            f"Only {result['denominator']} records, below the minimum for a median. Author counts: "
            f"{', '.join(str(v) for v in result['values'])}.",
        ]
    else:
        low, high = result["iqr"]
        lines += [
            f"Median {_fmt_number(result['median'])} authors per record over {result['denominator']} "
            f"records; IQR {_fmt_number(low)} to {_fmt_number(high)}; range {result['min']} to "
            f"{result['max']}.",
        ]
    lines.append(
        f"- records with 20 or more authors: {result['large_team_count']} of {result['denominator']} "
        f"— {_pmid_list(result['large_team_pmids'])}"
    )
    subset = result["subset"]
    if subset["suppressed"]:
        lines.append(
            f"- records led by a lead-trainee or support candidate: {subset['denominator']}, below the "
            f"minimum for a separate median"
        )
    else:
        lines.append(
            f"- records led by a lead-trainee or support candidate: median "
            f"{_fmt_number(subset['median'])} authors over {subset['denominator']} records"
        )
    return lines


def _venue_body(result: dict[str, Any]) -> list[str]:
    lines = [f"Journal strings over {result['denominator']} records, exactly as recorded.", ""]
    for name, count in result["repeated"]:
        lines.append(f"- {name}: {count} of {result['denominator']} records")
    if not result["repeated"]:
        lines.append("- no journal string appears more than once")
    lines.append(f"- {result['singleton_count']} journal string(s) appear once")
    if result["missing_journal_count"]:
        lines.append(f"- {result['missing_journal_count']} record(s) carry no journal string")
    return lines


def _affiliation_body(result: dict[str, Any]) -> list[str]:
    lines = [
        f"Affiliation strings appearing on at least {result['min_papers']} of "
        f"{result['denominator']} records, printed verbatim and ungrouped:",
        "",
    ]
    if result["strings"]:
        lines += [f"- `{text}` — {count} records" for text, count in result["strings"]]
    else:
        lines.append(f"- no affiliation string reaches {result['min_papers']} records")
    lines += ["", "Coverage per year (author entries carrying any affiliation string):", ""]
    for row in result["coverage_by_year"]:
        if row["total"] == 0 or row["covered"] == 0:
            lines.append(f"- {row['year']}: no affiliation data")
        else:
            lines.append(f"- {row['year']}: {row['covered']} of {row['total']} author entries")
    return lines


def _titles_body(result: dict[str, Any]) -> list[str]:
    lines = [f"All {result['denominator']} record titles, verbatim, by year.", ""]
    for group in result["years"]:
        lines.append(f"**{group['year']}**")
        lines += [f"- {record['title']} (PMID {record['pmid']})" for record in group["records"]]
        lines.append("")
    return lines


# --- Output ---


def render_markdown(report: dict[str, Any]) -> str:
    """Markdown rendering. Never emits a single overall score, grade or rating."""
    title = f"# Observed publication pattern — {report['author_name'] or '(unnamed researcher)'}"
    if report["refused"]:
        gate = report["gate"]
        observed = "\n".join(f"- {key}: {value}" for key, value in gate["observed"].items())
        return "\n".join([
            title,
            "",
            f"## Report refused — gate {gate['id']} ({gate['name']})",
            "",
            gate["message"],
            "",
            "Observed:",
            observed or "- (none)",
            "",
        ])

    parts = [title, "", f"_Generated {report['generated_at']}._", ""]
    for section in report["sections"]:
        parts += [f"## {section['id']}. {section['title']}", ""]
        parts += section["prose"] + ([""] if section["prose"] else [])
        parts += section["body"] + ([""] if section["body"] else [])
        for text in section["caveats"]:
            parts += [f"> {text}", ""]
    return "\n".join(parts).rstrip() + "\n"


def json_record(report: dict[str, Any]) -> dict[str, Any]:
    """
    The machine-readable half: the same numbers, without the rendered prose.

    `sections` is dropped because it is a view of `metrics`; keeping both would
    let the two drift apart with no way to tell which one is authoritative.
    """
    return {key: value for key, value in report.items() if key != "sections"}


def write_report(report: dict[str, Any], output_dir: str | Path) -> dict[str, str]:
    """Write the Markdown and the JSON side by side. Returns both paths."""
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.fromisoformat(report["generated_at"]).strftime("%Y%m%d_%H%M%S")
    markdown_path = directory / f"advisor_profile_{stamp}.md"
    json_path = directory / f"advisor_profile_{stamp}.json"
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    json_path.write_text(
        json.dumps(json_record(report), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {"markdown": str(markdown_path), "json": str(json_path)}
