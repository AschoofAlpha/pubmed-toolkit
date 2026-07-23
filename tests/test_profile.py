#!/usr/bin/env python3
"""
Advisor profile tests.

Covers every (input -> expected) case listed in docs/profile-metrics-spec.md
Section 11, plus the suppression behaviour that keeps small samples from being
rendered as confident aggregates. Spec test IDs (T01-T62) appear in the labels
so a failure points straight at the rule it violates.

All data is fictional. The only real identifier used is 0000-0002-1825-0097,
ORCID's own published example for the fictional Josiah Carberry, matching
tests/test_identity_filter.py. Where a second, deliberately different ORCID is
needed, 0000-0000-0000-0000 is used: it fails the ORCID checksum and can
therefore never belong to a real person.

Fully offline: synthetic fixtures only, no network, no matplotlib.

Run: python tests/test_profile.py
"""

from __future__ import annotations

import inspect
import json
import os
import sys
import tempfile
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pubmed_toolkit.profile import caveats, metrics, report, roles  # noqa: E402

_passed = 0
_failed = 0


def check(label: str, actual, expected) -> None:
    global _passed, _failed
    ok = actual == expected
    if ok:
        _passed += 1
    else:
        _failed += 1
    detail = "" if ok else f"  (expected {expected!r}, got {actual!r})"
    print(f"  {'[PASS]' if ok else '[FAIL]'} {label}{detail}")


def check_true(label: str, actual) -> None:
    check(label, bool(actual), True)


def check_false(label: str, actual) -> None:
    check(label, bool(actual), False)


# ============================================================
# Fixture builders
# ============================================================

TARGET = "Chen Xiuying"
ORCID = "0000-0002-1825-0097"
# Checksum-invalid, so it can never be a real person's identifier.
OTHER_ORCID = "0000-0000-0000-0000"
INTERNAL = "Department of Hepatobiliary Surgery, Nanhai Medical University, Nanhai"
INTERNAL_VARIANT = "Nanhai Med Univ, Nanhai"
EXTERNAL = "Institute of Applied Physics, Beihai Polytechnic"

IDENTITY = {
    "author_name": TARGET,
    "orcid": ORCID,
    "affiliation_keywords": ["Nanhai Medical University", "Nanhai Med Univ"],
    "email_domains": ["@nanhai-med.example.edu"],
    "require_affiliation_effective": False,
}

FIXED_NOW = datetime(2026, 7, 22, 20, 47, 11)


def author(name, *, affiliation="", email="", orcid="", equal_contrib=False,
           corresponding=None, last=None, fore=None, initials=None):
    """One byline entry in the shape `pubmed_api._author_record` produces."""
    parts = name.split()
    last_value = last if last is not None else (parts[0] if parts else "")
    fore_value = fore if fore is not None else (" ".join(parts[1:]) if len(parts) > 1 else "")
    initials_value = initials if initials is not None else (fore_value[:1] if fore_value else "")
    return {
        "name": name,
        "last": last_value,
        "fore": fore_value,
        "initials": initials_value,
        "affiliation": affiliation,
        "email": email,
        "orcid": orcid,
        "equal_contrib": equal_contrib,
        # Mirrors the real parser: corresponding status is inferred from an email.
        "is_corresponding": bool(email) if corresponding is None else corresponding,
    }


def distinct(prefix, index, given="Person"):
    """
    A name guaranteed not to share a person key with any other `distinct` name.

    The disambiguating digits go in the surname on purpose. Putting them in the
    forename ("Lead Person01", "Lead Person02") produces one loose key and two
    incompatible forenames, which the tool correctly reports as a suspected
    collision — correct behaviour, but it makes a fixture mean something other
    than what it looks like.
    """
    return f"{prefix}{index:02d} {given}"


def collective(name):
    """A <CollectiveName> byline entry: a name with no name parts."""
    return {"name": name, "last": "", "fore": "", "initials": "", "affiliation": "",
            "email": "", "orcid": "", "equal_contrib": False, "is_corresponding": False}


def pi(affiliation=INTERNAL, email="", orcid=ORCID):
    return author(TARGET, affiliation=affiliation, email=email, orcid=orcid)


def paper(pmid, authors, pub_date="2023 Jun", *, title=None, journal="Hepatology Reports",
          doi="", pi_index=None, pi_evidence="orcid", pi_ambiguous=False):
    record = {
        "pmid": str(pmid),
        "title": title if title is not None else f"Study {pmid} of hepatic stellate cell activation",
        "authors": authors,
        "authors_str": ", ".join(a["name"] for a in authors),
        "journal": journal,
        "pub_date": pub_date,
        "pub_year": pub_date.split()[0] if pub_date else "",
        "volume": "", "issue": "", "pages": "", "doi": doi, "pmc_id": "", "abstract": "",
    }
    if pi_index is not None:
        record["pi_index"] = pi_index
        record["pi_evidence"] = pi_evidence
        record["pi_ambiguous"] = pi_ambiguous
    return record


def corpus(papers, **overrides):
    data = {
        "schema_version": 1,
        "generated_at": "2026-07-22T20:47:11",
        "position_filtered": False,
        "query": {
            "term": '"Chen Xiuying"[Author] OR "Chen X*"[Author]',
            "mindate": "2021/07/22", "maxdate": "2026/07/22",
            "years_back": 5, "retmax": 500,
            "esearch_count": len(papers), "pmids_returned": len(papers), "truncated": False,
        },
        "identity": dict(IDENTITY),
        "counts": {
            "fetched": len(papers), "verified": len(papers), "name_only": 0, "rejected": 0,
            "by_evidence": {"orcid": len(papers)},
        },
        "fallback_fired": False,
        "papers": papers,
    }
    data.update(overrides)
    return data


def build_from(data, config=None, gantt=None):
    return report.build_report(data, config or {}, gantt, FIXED_NOW)


def build(papers, config=None, gantt=None, **overrides):
    return build_from(corpus(papers, **overrides), config, gantt)


def section(rep, section_id):
    return next(s for s in rep["sections"] if s["id"] == section_id)


def body_text(rep, section_id):
    return "\n".join(section(rep, section_id)["body"])


def caveat_text(rep, section_id):
    return "\n".join(section(rep, section_id)["caveats"])


def all_body_lines(rep):
    return [line for sec in rep["sections"] for line in sec["body"]]


def person_named(rep, name):
    for row in rep["metrics"]["s2"]["rows"]:
        if row["name"] == name:
            return row
    return None


# ============================================================
# 11.1 Gates and provenance
# ============================================================

print("\n--- gates and provenance (T01-T08) ---")

truncated = corpus([paper(1, [author("Liu Hua"), pi()], pi_index=1)])
truncated["query"]["esearch_count"] = 900
truncated["query"]["pmids_returned"] = 500
rep = build_from(truncated)
check("T01 truncation refuses", rep["gate"]["id"], "G1")
check("T01 exit code is 1", rep["exit_code"], 1)
check("T01 no section rendered", rep["sections"], [])
check_true("T01 refusal names the observed counts", "900" in report.render_markdown(rep))

fallback = corpus([paper(i, [author(distinct("Liu", i, "Hua")), pi()], pi_index=1) for i in range(40)])
fallback["fallback_fired"] = True
rep = build_from(fallback)
check("T02 identity fallback refuses", rep["gate"]["id"], "G2")
check("T02 no section rendered", rep["sections"], [])

weak = corpus([paper(1, [author("Liu Hua"), pi()], pi_index=1)])
weak["identity"] = {"author_name": TARGET, "orcid": "", "affiliation_keywords": [], "email_domains": []}
rep = build_from(weak)
check("T03 weak identity config refuses", rep["gate"]["id"], "G3")

no_authors = corpus([paper(1, [author("Liu Hua"), pi()], pi_index=1), paper(2, [], pi_index=None)])
rep = build_from(no_authors)
check("T04 empty author list refuses", rep["gate"]["id"], "G4")

missing_key = corpus([paper(1, [author("Liu Hua"), pi()], pi_index=1)])
del missing_key["papers"][0]["authors"]
check("T04 absent authors key refuses", build_from(missing_key)["gate"]["id"], "G4")

all_excluded = build([
    paper(1, [author("Liu Hua"), pi()], "", pi_index=1),
    paper(2, [author("Liu Hua"), pi()], "", pi_index=1),
    paper(3, [author("Liu Hua"), pi()], "", pi_index=1),
])
check("T05 corpus emptied by exclusions refuses", all_excluded["gate"]["id"], "G5")

clean = corpus([
    paper(1000 + i, [author(distinct("Trainee", i), affiliation=INTERNAL), pi()],
          f"202{2 + i % 4} Mar", pi_index=1)
    for i in range(25)
])
clean["counts"] = {"fetched": 31, "verified": 25, "name_only": 6, "rejected": 0,
                   "by_evidence": {"orcid": 12, "email": 9, "affiliation": 4}}
clean["query"]["esearch_count"] = 31
clean["query"]["pmids_returned"] = 31
rep = build_from(clean)
check("T06 clean corpus fires no gate", rep["gate"], None)
check_true("T06 provenance prints verified=25", "verified 25" in body_text(rep, 1))
check_true("T06 provenance prints name_only=6", "name_only 6" in body_text(rep, 1))
check("T06 evidence tiers sum to verified", 12 + 9 + 4, rep["provenance"]["counts"]["verified"])
check_true("T06 evidence breakdown rendered", "orcid 12" in body_text(rep, 1))
check_true("T06 CAV-01 rendered with n=6", rep["caveats"]["CAV-01"].startswith("6 further papers"))

unfiltered_unknown = corpus([
    paper(2000 + i, [author(distinct("Trainee", i), affiliation=INTERNAL), pi()], "2023 Mar", pi_index=1)
    for i in range(6)
])
del unfiltered_unknown["position_filtered"]
rep = build_from(unfiltered_unknown)
check("T07 absent position_filtered treated as true", rep["provenance"]["position_filtered"], True)
check_false("T07 section 7 is not measured", rep["metrics"]["s7"]["measured"])
check_true("T07 section 7 carries CAV-13", caveats.CAVEATS["CAV-13"] in caveat_text(rep, 7))
check("T07 every other section still renders", len(rep["sections"]), 15)

rep = report.build_report_from_path("pubmed_results/papers_20260722_120000.xlsx", {}, None, FIXED_NOW)
check("T08 spreadsheet path refuses", rep["gate"]["id"], "G4")
check_true("T08 the spreadsheet was never opened", rep["refused"])


# ============================================================
# 11.2 PI resolution
# ============================================================

print("\n--- PI resolution (T09-T16) ---")

middle_paper = paper(1, [
    author("Liu Hua"), author("Wang Li"), author("Zhao Min"),
    pi(affiliation="", orcid=ORCID),
    author("Sun Qi"), author("Guo Yan"), author("Xu Bo"),
])
resolved = roles.resolve_pi(middle_paper, TARGET, IDENTITY)
check("T09 middle-author paper is verified", resolved["disposition"], "verified")
check("T09 PI index recorded", resolved["pi_index"], 3)
check("T09 evidence is ORCID", resolved["pi_evidence"], "orcid")

bare = paper(2, [author("Liu Hua"), pi(affiliation="", orcid="")])
resolved = roles.resolve_pi(bare, TARGET, IDENTITY)
check("T10 no identity evidence is name_only", resolved["disposition"], "name_only")
check("T10 name_only papers are not verified", resolved["disposition"] == "verified", False)

two_tiers = paper(3, [
    author(TARGET, affiliation=INTERNAL),
    author("Liu Hua"),
    author(TARGET, affiliation="", orcid=ORCID),
])
resolved = roles.resolve_pi(two_tiers, TARGET, IDENTITY)
check("T11 ORCID beats affiliation regardless of index", resolved["pi_index"], 2)
check("T11 evidence recorded as ORCID", resolved["pi_evidence"], "orcid")
check_false("T11 not ambiguous when tiers differ", resolved["pi_ambiguous"])

same_tier = paper(4, [
    author(TARGET, affiliation=INTERNAL),
    author("Liu Hua"),
    author(TARGET, affiliation=INTERNAL_VARIANT),
])
resolved = roles.resolve_pi(same_tier, TARGET, IDENTITY)
check("T12 tie breaks to the lowest index", resolved["pi_index"], 0)
check_true("T12 tie is flagged ambiguous", resolved["pi_ambiguous"])

sole_other = build([
    paper(1, [author("Liu Hua", affiliation=INTERNAL)], "2023 Feb", pi_index=None),
    paper(2, [author("Wang Li"), pi()], "2023 Mar", pi_index=1),
])
check("T13 sole author lands in the senior stratum", person_named(sole_other, "Liu Hua")["stratum"], "D")
check("T13 sole-author record is logged by PMID",
      sole_other["provenance"]["sole_author_papers"], ["1"])

sole_pi = build([
    paper(1, [pi()], "2023 Feb", pi_index=0),
    paper(2, [author("Wang Li"), pi()], "2023 Mar", pi_index=1),
])
check("T14 sole PI paper leaves the eligible set",
      sole_pi["metrics"]["s3a"]["dropped_pi_is_lead"], ["1"])
check("T14 PI byline position is sole", sole_pi["metrics"]["s7"]["counts"]["sole"], 1)

trailing_group = build([
    paper(1, [author("Wang Li"), pi(), author("Zhao Min"), collective("Nanhai Liver Study Group")],
          "2023 Mar", pi_index=1),
    paper(2, [author("Wang Li"), pi()], "2024 Mar", pi_index=1),
])
check("T15 person at n-2 becomes senior once the consortium is removed",
      person_named(trailing_group, "Zhao Min")["stratum"], "D")
check("T15 the consortium is not a person", person_named(trailing_group, "Nanhai Liver Study Group"), None)

leading_group = build([
    paper(1, [collective("Nanhai Liver Study Group"), author("Wang Li"), pi()], "2023 Mar", pi_index=2),
    paper(2, [author("Zhao Min"), pi()], "2024 Mar", pi_index=1),
])
check("T16 consortium in the lead slot leaves the eligible set",
      leading_group["metrics"]["s3a"]["dropped_slot0_collective"], ["1"])
check("T16 consortium lead slot is counted separately",
      leading_group["provenance"]["slot0_collective_pmids"], ["1"])
check("T16 nobody is credited with that lead slot",
      person_named(leading_group, "Wang Li")["n_first_slots"], 0)


# ============================================================
# 11.3 Record exclusions
# ============================================================

print("\n--- record exclusions (T17-T23) ---")

undated = build([
    paper(1, [author("Liu Hua"), pi()], "", pi_index=1),
    paper(2, [author("Liu Hua"), pi()], "2023 Mar", pi_index=1),
    paper(3, [author("Liu Hua"), pi()], "2024 Mar", pi_index=1),
])
check("T17 undated record excluded", undated["provenance"]["exclusions"]["unparseable_date"], ["1"])
check("T17 no fabricated century-long span", person_named(undated, "Liu Hua")["first_year"], 2023)

corrections = build([
    paper(1, [author("Liu Hua"), pi()], "2023 Mar", pi_index=1,
          title="Correction to: Hepatic stellate cell activation"),
    paper(2, [author("Liu Hua"), pi()], "2024 Mar", pi_index=1,
          title="Corrective surgery outcomes in biliary atresia"),
])
check("T18 correction record excluded",
      corrections["provenance"]["exclusions"]["correction_or_comment"], ["1"])
check("T19 word-anchored regex spares 'Corrective'", corrections["provenance"]["corpus_size"], 1)

hyper_authors = [author(distinct("Consort", i, "Member")) for i in range(60)]
hyper = build([
    paper(1, [*hyper_authors, pi(), author("Tail Person")], "2023 Mar", pi_index=60),
    paper(2, [author("Liu Hua"), pi()], "2024 Mar", pi_index=1),
    paper(3, [author("Wang Li"), pi()], "2025 Mar", pi_index=1),
])
check("T20 hyperauthorship record excluded and listed",
      hyper["provenance"]["exclusions"]["hyperauthorship"], ["1"])
check("T20 its authors leave person-level analysis", person_named(hyper, "Consort Member00"), None)
check("T20 it leaves the team-size denominator", hyper["metrics"]["s10"]["denominator"], 2)
check("T20 it leaves the eligible set", hyper["metrics"]["s3a"]["denominator"], 2)
check("T20 it still counts in records per year", hyper["metrics"]["s9"]["denominator"], 3)

large_team = build([
    paper(1, [author("Lead Person"), pi(), *[author(distinct("Team", i, "Member")) for i in range(20)]],
          "2023 Mar", pi_index=1),
    *[paper(10 + i, [author("Liu Hua"), pi()], "2024 Mar", pi_index=1) for i in range(4)],
])
check("T21 a 22-author record is retained", large_team["provenance"]["corpus_size"], 5)
check("T21 counted on the 20-or-more line", large_team["metrics"]["s10"]["large_team_count"], 1)

doi_dupes = build([
    paper(200, [author("Liu Hua"), pi()], "2023 Mar", pi_index=1, doi="10.1234/ABC.001"),
    paper(100, [author("Liu Hua"), pi()], "2023 Apr", pi_index=1, doi="10.1234/abc.001"),
    paper(300, [author("Wang Li"), pi()], "2024 Mar", pi_index=1),
])
check("T22 duplicate DOI keeps the lower PMID",
      doi_dupes["provenance"]["exclusions"]["duplicate_doi"], ["200"])
check("T22 one record survives the DOI pair", doi_dupes["provenance"]["corpus_size"], 2)

title_dupes = build([
    paper(1, [author("Liu Hua"), pi()], "2023 Mar", pi_index=1, doi="10.1/a",
          title="Hepatic stellate cell activation in fibrosis"),
    paper(2, [author("Liu Hua"), pi()], "2023 Sep", pi_index=1, doi="10.1/b",
          title="Hepatic stellate cell activation in fibrosis."),
])
check("T23 identical titles are both retained", title_dupes["provenance"]["corpus_size"], 2)
check("T23 identical titles are flagged, not merged",
      title_dupes["provenance"]["title_duplicates"], [["1", "2"]])


# ============================================================
# 11.4 Person keys
# ============================================================

print("\n--- person keys (T24-T31) ---")


def two_author_corpus(names_by_paper, **kw):
    """One paper per entry; each listed person is a middle author, the PI is last."""
    papers = []
    for index, (names, date) in enumerate(names_by_paper):
        entries = [author(distinct("Lead", index)), *names, pi()]
        papers.append(paper(500 + index, entries, date, pi_index=len(entries) - 1))
    return build(papers, **kw)


prefix_merge = two_author_corpus([
    ([author("Wang Wei")], "2022 Mar"),
    ([author("Wang Weiwei")], "2023 Mar"),
])
merged = person_named(prefix_merge, "Wang Weiwei") or person_named(prefix_merge, "Wang Wei")
check("T24 prefix-compatible forenames merge", merged["n_appearances"], 2)
check("T24 the merge is flagged benign drift", merged["flags"], ["drift_benign"])
check_true("T24 CAV-02 is rendered", caveats.CAVEATS["CAV-02"][:40] in caveat_text(prefix_merge, 2))

suspected = two_author_corpus([
    ([author("Wang Wei")], "2022 Mar"),
    ([author("Wang Wenjie")], "2023 Mar"),
])
row = person_named(suspected, "Wang Wei") or person_named(suspected, "Wang Wenjie")
check("T25 incompatible forenames flag a suspected collision", row["flags"], ["collision_suspected"])
check("T25 every derived value carries the uncertainty marker", row["marker"], "[?]")

initials_only = two_author_corpus([
    ([author("Zhang Wei")], "2022 Mar"),
    ([author("Zhang W", fore="", initials="W")], "2023 Mar"),
])
row = person_named(initials_only, "Zhang Wei")
check("T26 initials merge into the full forename", row["n_appearances"], 2)
check("T26 the merge is flagged benign drift", row["flags"], ["drift_benign"])

incomplete = two_author_corpus([
    ([author("Zhang", fore="", initials="")], "2022 Mar"),
    ([author("Zhang Wei")], "2023 Mar"),
])
check("T27 a nameless-forename entry stays separate",
      person_named(incomplete, "Zhang")["flags"], ["incomplete_name"])
check("T27 it is not merged into Zhang Wei", person_named(incomplete, "Zhang Wei")["n_appearances"], 1)

two_orcids = two_author_corpus([
    ([author("Li Ming", orcid=ORCID)], "2022 Mar"),
    ([author("Li Ming", orcid=OTHER_ORCID)], "2023 Mar"),
])
li_rows = [r for r in two_orcids["metrics"]["s2"]["rows"] if r["name"] == "Li Ming"]
check("T28 two ORCIDs under one name stay two people", len(li_rows), 2)
check_true("T28 both are flagged as a confirmed collision",
           all(r["flags"] == ["collision_confirmed"] for r in li_rows))

orcid_partial = two_author_corpus([
    ([author("Li Ming", orcid=ORCID)], "2022 Mar"),
    ([author("Li Ming")], "2023 Mar"),
])
check("T29 an ORCID-less entry joins its unique ORCID group",
      person_named(orcid_partial, "Li Ming")["n_appearances"], 2)

orcid_clash = two_author_corpus([
    ([author("Li Ming", orcid=ORCID)], "2022 Mar"),
    ([author("Li Ming", orcid=OTHER_ORCID)], "2023 Mar"),
    ([author("Li Ming")], "2024 Mar"),
])
clash_rows = [r for r in orcid_clash["metrics"]["s2"]["rows"] if r["name"] == "Li Ming"]
check("T30 a contested loose key merges into nothing", len(clash_rows), 3)
check_true("T30 all three groups are flagged",
           all(r["flags"] == ["collision_confirmed"] for r in clash_rows))

budget = two_author_corpus([
    ([author("Liu Hua")], "2022 Mar"),
    ([author("Liu Huan")], "2023 Mar"),
    ([author("Sun Qi")], "2024 Mar"),
])
check("T31 loose keying finds fewer people than strict", budget["provenance"]["n_loose"], 5)
check("T31 strict keying splits the drifted name", budget["provenance"]["n_strict"], 6)
check_true("T31 the ambiguity budget is printed",
           "strict keying finds 6, loose keying finds 5" in body_text(budget, 1))
check_true("T31 it is printed with zero collision flags",
           all("collision" not in flag
               for row in budget["metrics"]["s2"]["rows"] for flag in row["flags"]))


# ============================================================
# 11.5 Strata
# ============================================================

print("\n--- strata (T32-T39) ---")

strata_corpus = build([
    paper(1, [author("Lead One"), author("Support One"), author("Senior One"), pi()], "2022 Mar", pi_index=3),
    paper(2, [author("Lead One"), author("Support One"), pi(), author("Senior One")], "2023 Mar", pi_index=2),
    paper(3, [author("Other Lead"), author("Support One"), author("Senior One"), pi()], "2024 Mar", pi_index=3),
    paper(4, [author("Third Lead"), author("Solo Person"), author("Senior One"), pi()], "2025 Mar", pi_index=3),
])
check("T32 one senior slot in four papers is enough", person_named(strata_corpus, "Senior One")["stratum"], "D")
check_true("T32 senior collaborators leave the lead-slot partition",
           all(e["name"] != "Senior One"
               for bucket in strata_corpus["metrics"]["s3b"]["buckets"].values() for e in bucket))
check_true("T32 they leave the time-to-lead cohort",
           all(e["name"] != "Senior One" for e in strata_corpus["metrics"]["s4"]["values"]))
check_true("T32 they leave the span cohort",
           all(e["name"] != "Senior One" for e in strata_corpus["metrics"]["s5"]["values"]))
check("T33 two lead slots and never senior is stratum A",
      person_named(strata_corpus, "Lead One")["stratum"], "A")
check("T34 three appearances with no lead slot is stratum B",
      person_named(strata_corpus, "Support One")["stratum"], "B")
check("T35 a single appearance is stratum C", person_named(strata_corpus, "Solo Person")["stratum"], "C")
check_true("T35 single-appearance people are still on the roster",
           person_named(strata_corpus, "Solo Person") is not None)
check_true("T35 they are absent from the lead-slot partition",
           all(e["name"] != "Solo Person"
               for bucket in strata_corpus["metrics"]["s3b"]["buckets"].values() for e in bucket))
check_true("T35 they are absent from the span cohort",
           all(e["name"] != "Solo Person" for e in strata_corpus["metrics"]["s5"]["values"]))

co_pi = build([
    paper(600 + i, [author(distinct("Lead", i)), author("Co Investigator"), pi()],
          f"202{1 + i} Mar", pi_index=2)
    for i in range(6)
])
row = person_named(co_pi, "Co Investigator")
check("T36 a never-senior co-investigator stays a support candidate", row["stratum"], "B")
check("T36 six appearances do not promote anyone", row["n_appearances"], 6)
check_true("T36 CAV-03 accompanies the roster", caveats.CAVEATS["CAV-03"] in caveat_text(co_pi, 2))

flip = build([
    paper(1, [author("Rising Person"), pi()], "2021 Mar", pi_index=1),
    paper(2, [author("Rising Person"), pi()], "2022 Mar", pi_index=1),
    paper(3, [author("New Lead"), pi(), author("Rising Person")], "2025 Mar", pi_index=1),
])
check("T37 taking a senior slot reassigns the stratum", person_named(flip, "Rising Person")["stratum"], "D")
check("T37 the flip is reported by name and year", flip["provenance"]["flips"],
      [{"name": "Rising Person", "marker": "", "first_lead_year": 2021, "first_last_year": 2025}])
check_true("T37 section 5 names the person and both years",
           "Rising Person" in body_text(flip, 5) and "2025" in body_text(flip, 5))

excluded_cfg = build(
    [
        paper(1, [author("Lead One"), author("Blocked Person"), pi()], "2022 Mar", pi_index=2),
        paper(2, [author("Lead One"), author("Blocked Person"), pi()], "2023 Mar", pi_index=2),
    ],
    config={"advisor": {"exclude_names": ["Blocked Person"]}},
)
check("T38 configured exclusions leave the roster", person_named(excluded_cfg, "Blocked Person"), None)
check_true("T38 they leave every metric section",
           all("Blocked Person" not in line
               for sec in excluded_cfg["sections"] if sec["id"] != 1
               for line in sec["body"]))
check_true("T38 the exclusion itself is disclosed in provenance",
           "configured name exclusions: Blocked Person" in body_text(excluded_cfg, 1))

default_exclusions = roles.default_gantt_exclude_names(TARGET)
check("T39 the default timeline exclusion set is the PI and the empty name",
      default_exclusions, {TARGET, ""})
# The exact-equality assertion above already proves that no leftover name
# survives, whatever it was. Listing the six real people who used to be
# hardcoded would republish exactly the personal data this fix removes.
check("T39 no third-party name survives in the default set",
      default_exclusions - {TARGET, ""}, set())
check("T39 configured names are added to it",
      roles.default_gantt_exclude_names(TARGET, {"exclude_names": ["Blocked Person"]}),
      {TARGET, "", "Blocked Person"})


# ============================================================
# 11.6 Metrics
# ============================================================

print("\n--- metrics (T40-T62) ---")

# |E| = 23 with exactly 9 lead slots held by stratum-A people.
e23 = []
for i in range(8):
    e23.append(paper(700 + i, [author(distinct("Lead", i)), pi()], "2022 Mar", pi_index=1))
for i in range(14):
    e23.append(paper(720 + i, [author("Senior One"), pi()], "2023 Mar", pi_index=1))
e23.append(paper(740, [author("Other Lead"), pi(), author("Senior One")], "2024 Mar", pi_index=1))
rep23 = build(e23)
slots = rep23["metrics"]["s3a"]
check("T40 the eligible set is 23 records", slots["denominator"], 23)
check("T40 nine lead slots are held by lead-trainee candidates", slots["counts"]["A"], 9)
check("T40 a percentage is permitted at n>=20", slots["percentages"]["A"], 39)
check_true("T40 rendered as a count with its denominator and percentage",
           "9 of 23 records (39%)" in body_text(rep23, 3))
check_true("T40 the word 'share' does not appear", "share" not in body_text(rep23, 3).lower())

e12 = [paper(800 + i, [author(distinct("Lead", i)), pi()], "2023 Mar", pi_index=1) for i in range(12)]
rep12 = build(e12)
check("T41 the eligible set is 12 records", rep12["metrics"]["s3a"]["denominator"], 12)
check("T41 no percentage is computed below n=20", rep12["metrics"]["s3a"]["percentages"], None)
check_true("T41 no percentage is rendered", "%" not in body_text(rep12, 3))

e3 = [paper(850 + i, [author(distinct("Lead", i)), pi()], "2023 Mar", pi_index=1) for i in range(3)]
rep3 = build(e3)
check_true("T42 the aggregate is suppressed below n=5", rep3["metrics"]["s3a"]["suppressed"])
check_true("T42 the records are printed instead", "| 850 | 2023 |" in body_text(rep3, 3))

pi_leads = build([paper(870 + i, [pi(), author(distinct("Support", i))], "2023 Mar", pi_index=0)
                  for i in range(14)])
check_true("T43 an empty eligible set is not computable", pi_leads["metrics"]["s3a"]["not_computable"])
check_true("T43 the exact sentence is printed",
           "not computable: the PI is first author on every corpus paper" in body_text(pi_leads, 3))
# The person-side partition below always prints its three buckets including
# zeros, by design; the "no zeros" rule applies to the paper-side counts.
check_true("T43 no zero slot counts are emitted",
           not any(line.startswith("- lead-trainee candidate:") or line.startswith("- senior collaborator:")
                   for line in section(pi_leads, 3)["body"]))

partition_corpus = build([
    paper(1, [author("LeadA1 Person"), author("SupportB1 Person"), author("SupportB2 Person"),
              author("SupportB3 Person"), pi()], "2022 Mar", pi_index=4),
    paper(2, [author("LeadA2 Person"), author("SupportB1 Person"), author("SupportB2 Person"),
              author("SupportB3 Person"), pi()], "2023 Mar", pi_index=4),
    paper(3, [author("LeadA3 Person"), author("SupportB4 Person"), author("SupportB5 Person"), pi()],
          "2025 Mar", pi_index=3),
    paper(4, [author("LeadA4 Person"), author("SupportB4 Person"), author("SupportB5 Person"), pi()],
          "2025 Jun", pi_index=3),
])
partition = partition_corpus["metrics"]["s3b"]
check("T44 the partition denominator is A plus B", partition["denominator"], 9)
check("T44 lead-slot holders", partition["counts"]["holds_lead"], 4)
check("T44 observed without a lead slot", partition["counts"]["observed_without_lead"], 3)
check("T44 too recent to tell", partition["counts"]["too_recent"], 2)
check("T44 no percentage exists at any n", partition["percentages"], None)
check_true("T44 CAV-06 accompanies the partition",
           caveats.CAVEATS["CAV-06"] in caveat_text(partition_corpus, 3))

lag_corpus = build([
    paper(1, [author("ZeroA Person"), pi()], "2022 Mar", pi_index=1),
    paper(2, [author("ZeroB Person"), pi()], "2022 Mar", pi_index=1),
    paper(3, [author("ZeroC Person"), pi()], "2022 Mar", pi_index=1),
    paper(4, [pi(), author("LagOne Person"), author("FillerA Person")], "2022 Mar", pi_index=0),
    paper(5, [author("LagOne Person"), pi()], "2023 Mar", pi_index=1),
    paper(6, [pi(), author("LagTwo Person"), author("LagFour Person"), author("FillerB Person")],
          "2021 Mar", pi_index=0),
    paper(7, [author("LagTwo Person"), pi()], "2023 Mar", pi_index=1),
    paper(8, [author("LagFour Person"), pi()], "2025 Mar", pi_index=1),
])
lag = lag_corpus["metrics"]["s4"]
check("T45 six people reached a lead slot", lag["denominator"], 6)
check("T45 the lag values", sorted(item["lag_years"] for item in lag["values"]), [0, 0, 0, 1, 2, 4])
check("T45 the median is computed at n=6", lag["median"], 0.5)
check("T45 the count at lag zero is explicit", lag["count_at_zero"], 3)
check_true("T45 the zero count is rendered",
           "at 0 years (debuted in the lead slot): 3 of 6" in body_text(lag_corpus, 4))

lag3 = build([paper(900 + i, [author(distinct("Lead", i)), pi()], "2023 Mar", pi_index=1)
              for i in range(3)])
check_true("T46 the median is suppressed at n=3", lag3["metrics"]["s4"]["suppressed"])
check("T46 no median is produced", lag3["metrics"]["s4"]["median"], None)
check_true("T46 the raw values are printed", "Lead00 Person: 0 year(s)" in body_text(lag3, 4))


def span_corpus(spec, config=None):
    """One paper per (person, year); the person leads, the PI closes the byline."""
    papers = []
    counter = 0
    for name, years in spec:
        for year in years:
            counter += 1
            papers.append(paper(1000 + counter, [author(name), pi()], f"{year} Mar", pi_index=1))
    return build(papers, config=config)


spans47 = span_corpus([
    ("CompleteOne Person", [2022, 2023]),
    ("CompleteTwo Person", [2022, 2024]),
    ("CompleteThree Person", [2023, 2024]),
    ("CompleteFour Person", [2022, 2022]),
    ("CensoredOne Person", [2023, 2025]),
    ("CensoredTwo Person", [2023, 2026]),
    ("CensoredThree Person", [2024, 2025]),
    ("CensoredFour Person", [2024, 2026]),
    ("CensoredFive Person", [2022, 2025]),
])
span47 = spans47["metrics"]["s5"]
check("T47 four spans are uncensored", span47["buckets"]["complete"], 4)
check("T47 five spans are right-censored", span47["buckets"]["right_censored"], 5)
check("T47 no median below n=5", span47["median"], None)
check_true("T47 the aggregate is suppressed", span47["suppressed"])
check_true("T47 the raw values are printed", "CompleteOne Person: span 1 year(s)" in body_text(spans47, 5))
check_true("T47 the censoring counts are printed", "right_censored 5" in body_text(spans47, 5))

spans48 = span_corpus([
    ("CompleteOne Person", [2022, 2023]),
    ("CompleteTwo Person", [2022, 2024]),
    ("CompleteThree Person", [2023, 2024]),
    ("CompleteFour Person", [2022, 2022]),
    ("CompleteFive Person", [2023, 2023]),
    ("CompleteSix Person", [2022, 2024]),
])
span48 = spans48["metrics"]["s5"]
check("T48 six uncensored spans", span48["denominator"], 6)
check("T48 the median is computed", span48["median"], 1.0)
check_true("T48 an IQR is computed", span48["iqr"] is not None)
check_true("T48 no arithmetic mean appears in section 5",
           "mean" not in (body_text(spans48, 5) + caveat_text(spans48, 5)).lower())
check_true("T48 no metric key is a mean",
           not any("mean" in key for key in spans48["metrics"]["s5"]))

check("T49 two records in one year give a zero span",
      person_named(spans48, "CompleteFour Person")["first_year"],
      person_named(spans48, "CompleteFour Person")["last_year"])
check_true("T49 it is rendered as a same-year zero, not as a single appearance",
           "CompleteFour Person: span 0 (same year)" in body_text(spans48, 5))
check("T49 a single-appearance person is not in the span cohort",
      person_named(strata_corpus, "Solo Person")["stratum"], "C")

censoring = span_corpus([
    ("EdgeStart Person", [2021, 2023]),
    ("EdgeEnd Person", [2023, 2026]),
])
check_true("T50 first appearance at the window start is left-censored",
           person_named(censoring, "EdgeStart Person")["left_censored"])
check_true("T51 last appearance in the current year is right-censored",
           person_named(censoring, "EdgeEnd Person")["right_censored"])
check("T50/T51 neither is in the uncensored bucket",
      censoring["metrics"]["s5"]["buckets"]["complete"], 0)

gap_years = build([
    paper(1, [author("Liu Hua"), pi()], "2022 Mar", pi_index=1),
    paper(2, [author("Liu Hua"), pi()], "2024 Mar", pi_index=1),
])
years9 = {row["year"]: row for row in gap_years["metrics"]["s9"]["years"]}
check("T52 an empty year is a zero, not an omitted row", years9[2023]["count"], 0)
check_true("T52 the zero is rendered", "- 2023: 0" in body_text(gap_years, 9))
check_true("T53 the first bin is marked partial", years9[2021]["partial"])
check_true("T53 the last bin is marked partial", years9[2026]["partial"])
check_true("T53 PARTIAL is rendered at the point of display",
           "- 2021: 0  (PARTIAL)" in body_text(gap_years, 9))
check_true("T53 CAV-17 is rendered", caveats.CAVEATS["CAV-17"] in caveat_text(gap_years, 9))

no_equal = build([paper(1, [author("Liu Hua"), pi()], "2023 Mar", pi_index=1)])
check_true("T54 an absent attribute is not measurable", no_equal["metrics"]["s8"]["not_measurable"])
check("T54 the exact sentence is printed", body_text(no_equal, 8), "not measurable in this corpus")
check_true("T54 no zero percentage is emitted", "0%" not in body_text(no_equal, 8))
check_true("T54 'no co-first' is never claimed", "no co-first" not in body_text(no_equal, 8).lower())

shared_first = build([
    paper(1, [author("Liu Hua", equal_contrib=True), author("Wang Li", equal_contrib=True),
              author("Zhao Min"), pi()], "2023 Mar", pi_index=3),
])
check("T55a a flagged group including slot 0 is shared first",
      shared_first["metrics"]["s8"]["categories"]["shared_first"], 1)
check("T55a the flagged group size is reported",
      shared_first["metrics"]["s8"]["papers"][0]["group_size"], 2)

shared_middle = build([
    paper(1, [author("Liu Hua"), author("Wang Li"),
              author("Zhao Min", equal_contrib=True), author("Sun Qi", equal_contrib=True),
              pi()], "2023 Mar", pi_index=4),
])
check("T55b a flagged group short of the final index is not co-first",
      shared_middle["metrics"]["s8"]["categories"]["shared_first"], 0)
check("T55b nor is it shared senior authorship",
      shared_middle["metrics"]["s8"]["categories"]["shared_senior"], 0)
check("T55b it is neither", shared_middle["metrics"]["s8"]["categories"]["other"], 1)

shared_senior_tail = build([
    paper(1, [author("Liu Hua"), author("Wang Li"),
              author("Zhao Min", equal_contrib=True), author("Sun Qi", equal_contrib=True)],
          "2023 Mar", pi_index=None),
])
check("T55b the final two indices are shared senior authorship",
      shared_senior_tail["metrics"]["s8"]["categories"]["shared_senior"], 1)
check("T55b and are not counted as co-first",
      shared_senior_tail["metrics"]["s8"]["categories"]["shared_first"], 0)

no_email = build([paper(1000 + i, [author(distinct("Lead", i)), pi(email="")], "2023 Mar", pi_index=1)
                  for i in range(6)])
check("T56 the corresponding-author figure is suppressed", no_email["metrics"]["s7"]["corresponding"], None)
check("T56 email coverage is zero of N", no_email["metrics"]["s7"]["email_coverage"],
      {"covered": 0, "denominator": 6})
check_true("T56 CAV-15 prints the coverage", "0 of 6 papers" in caveat_text(no_email, 7))

venues = build([
    *[paper(1100 + i, [author(distinct("Lead", i)), pi()], "2023 Mar", pi_index=1,
            journal="J Hepatol") for i in range(2)],
    *[paper(1110 + i, [author(distinct("Other", i)), pi()], "2024 Mar", pi_index=1,
            journal="Journal of Hepatology") for i in range(3)],
])
check("T57 abbreviation and full title stay separate rows",
      venues["metrics"]["s11"]["repeated"], [("Journal of Hepatology", 3), ("J Hepatol", 2)])
check_true("T57 both are rendered verbatim",
           "J Hepatol: 2 of 5" in body_text(venues, 11) and "Journal of Hepatology: 3 of 5" in body_text(venues, 11))
check_true("T57 CAV-20 is rendered", caveats.CAVEATS["CAV-20"] in caveat_text(venues, 11))

affil = build([
    *[paper(1200 + i, [author(distinct("Lead", i), affiliation=INTERNAL), pi()], "2023 Mar", pi_index=1)
      for i in range(4)],
    *[paper(1210 + i, [author(distinct("Other", i), affiliation=EXTERNAL), pi()], "2022 Mar", pi_index=1)
      for i in range(2)],
    paper(1220, [author("Blank Person"), pi(affiliation="")], "2024 Mar", pi_index=1),
])
check("T58 only strings on three or more records are listed",
      [text for text, _ in affil["metrics"]["s12"]["strings"]], [INTERNAL])
check_true("T58 per-year coverage is printed beside it",
           "2023: 8 of 8 author entries" in body_text(affil, 12))
check_true("T59 a year with no affiliation data says so", "- 2024: no affiliation data" in body_text(affil, 12))
check_true("T59 it is not rendered as an empty list with a zero rate",
           "2024: 0 of" not in body_text(affil, 12))

# T60: the DORA and no-composite-score prohibitions, asserted as a text scan of
# the computed half of the report. The caveats and the dropped-metric register
# name these same quantities in order to rule them out, so they are excluded
# from the scan by construction rather than by a keyword exception.
FORBIDDEN = ["h-index", "impact factor", "citation", "score", "grade", "rank"]
scan_report = build(e23 + [paper(1300, [author("Liu Hua", affiliation=INTERNAL), pi()], "2024 Mar", pi_index=1)],
                    gantt="pubmed_results/student_activity_gantt.png")
scan_text = "\n".join(all_body_lines(scan_report)).lower()
for token in FORBIDDEN:
    check(f"T60 '{token}' never appears in a computed value", token in scan_text, False)
percent_sections = {sec["id"] for sec in scan_report["sections"] if any("%" in line for line in sec["body"])}
check("T60 percentages appear only where R2 permits them", percent_sections - {3, 7}, set())
check_true("T60 no per-person row carries a percentage",
           not any("%" in line for line in section(scan_report, 2)["body"]))
check_true("T60 the banned word 'student' appears only in the supplied image path",
           all("student" not in line.lower() or ".png" in line
               for line in all_body_lines(scan_report)))

# The most prolific person appears last in time, so ordering by first
# appearance and ordering by count give different answers.
order_corpus = build([
    paper(1, [author("Zeta Person"), pi()], "2024 Mar", pi_index=1),
    paper(2, [author("Zeta Person"), pi()], "2025 Mar", pi_index=1),
    paper(3, [author("Zeta Person"), pi()], "2026 Mar", pi_index=1),
    paper(4, [author("Alpha Person"), pi()], "2022 Mar", pi_index=1),
    paper(5, [author("Beta Person"), pi()], "2023 Mar", pi_index=1),
])
rows61 = order_corpus["metrics"]["s2"]["rows"]
names = [row["name"] for row in rows61]
check("T61 rows are ordered by first appearance then name",
      names, ["Alpha Person", "Beta Person", "Zeta Person"])
check("T61 the ordering is not by appearance count",
      names == [row["name"] for row in sorted(rows61, key=lambda r: -r["n_appearances"])], False)
check("T61 the most prolific person is not promoted to the top", names.index("Zeta Person"), 2)

check("T62 section 0 comes first", scan_report["sections"][0]["id"], 0)
check("T62 section 0 is CAV-00 verbatim", scan_report["sections"][0]["prose"], [caveats.CAVEATS["CAV-00"]])
markdown = report.render_markdown(scan_report)
check_true("T62 CAV-00 precedes the provenance block",
           markdown.index(caveats.CAVEATS["CAV-00"]) < markdown.index("Corpus provenance"))


# ============================================================
# Contract checks the spec implies but does not number
# ============================================================

print("\n--- module contract ---")

check_true("no metric draws a chart", "matplotlib" not in inspect.getsource(report))
check_true("no metric touches the network",
           all(token not in inspect.getsource(metrics) for token in ("requests", "urllib", "open(")))
check_true("the supplied timeline image is referenced, not drawn",
           "![Person activity timeline](student_activity_gantt.png)" in markdown)
check_true("no overall score, grade or rating is emitted",
           not any(word in markdown.lower().split() for word in ("grade:", "rating:", "overall")))

for key, result in scan_report["metrics"].items():
    denominator = result.get("denominator", result.get("cohort_denominator"))
    check_true(f"{key} returns a denominator", denominator is not None)
    check_true(f"{key} returns a suppression flag", "suppressed" in result)

with tempfile.TemporaryDirectory() as tmp:
    paths = report.write_report(scan_report, tmp)
    check_true("markdown is written", os.path.exists(paths["markdown"]))
    check_true("json is written", os.path.exists(paths["json"]))
    with open(paths["json"], encoding="utf-8") as handle:
        record = json.load(handle)
    # A JSON round trip turns tuples into lists and integer dict keys into
    # strings, so the comparison is against the serialised form.
    check_true("the json record carries the same metrics",
               record["metrics"] == json.loads(json.dumps(scan_report["metrics"])))
    check_true("the json record omits the rendered sections", "sections" not in record)
    check("the json record repeats the denominators",
          record["metrics"]["s3a"]["denominator"], scan_report["metrics"]["s3a"]["denominator"])

    refusal_paths = report.write_report(
        report.build_report(truncated, {}, None, FIXED_NOW), tmp
    )
    with open(refusal_paths["markdown"], encoding="utf-8") as handle:
        refusal_markdown = handle.read()
    check_true("a refusal document names its gate", "gate G1" in refusal_markdown)
    check_true("a refusal document renders no section",
               "Corpus provenance" not in refusal_markdown)

check("suppressed aggregates return None, not a number",
      (rep3["metrics"]["s3a"]["percentages"], lag3["metrics"]["s4"]["median"],
       span47["median"], span47["iqr"]),
      (None, None, None, None))
small_team = build([paper(1400 + i, [author(distinct("Lead", i)), pi()], "2023 Mar", pi_index=1)
                    for i in range(3)])
check("the team-size median is suppressed below n=5", small_team["metrics"]["s10"]["median"], None)
# The trainee-led subset carries a higher floor than the main figure, so it can
# be suppressed while the corpus-wide median still renders.
mixed_leads = build(
    [paper(1500 + i, [pi(), author(distinct("Support", i))], "2023 Mar", pi_index=0) for i in range(5)]
    + [paper(1600 + i, [author(distinct("Lead", i)), pi()], "2024 Mar", pi_index=1) for i in range(3)]
)
check("the corpus-wide team-size median renders at n=8", mixed_leads["metrics"]["s10"]["median"], 2.0)
check("the trainee-led subset median needs its own higher floor",
      mixed_leads["metrics"]["s10"]["subset"]["median"], None)
check("the subset still reports its denominator",
      mixed_leads["metrics"]["s10"]["subset"]["denominator"], 3)
check("percent() refuses to compute below n=20", metrics.percent(3, 19), None)
check("percent() computes at n=20", metrics.percent(5, 20), 25)


print("\n" + "=" * 70)
print(f"Summary: {_passed} passed / {_failed} failed / {_passed + _failed} total")
print("=" * 70)
sys.exit(0 if _failed == 0 else 1)
