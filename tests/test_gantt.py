#!/usr/bin/env python3
"""
Activity-timeline tests: the row-inclusion rule, the ordering rule, and the
figure-height rule from docs/profile-visual-spec.md Section 4.

The defect under test was measured, not hypothetical: one real run drew 277
people on one axis at 1934x21506 px, and 190 of those rows carried a single dot.
The rules asserted here are what stops that recurring — rows are strata A and B,
order never depends on a count, everyone who loses a row is still counted on the
chart face, and height is `24 * n_rows + chrome` with chrome <= 140.

Assertions are logical wherever a logical assertion is available. Pixels are
asserted exactly once, on the saved PNG, because the defect was a pixel size and
a size claim that is never measured is not a fix.

All data is synthetic. Fully offline. matplotlib is optional: without it the
render checks report [SKIP] and the run still exits 0.

Run: python tests/test_gantt.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pubmed_toolkit import analysis  # noqa: E402

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

PI = "Pi Investigator"


def record(pmid: int, pubdate: str, names: list[str], equal: tuple[str, ...] = ()) -> dict:
    """
    One `_authors_parsed.json` record, with the position flags computed exactly
    as `build_author_records` computes them: first is index 0, last is index -1.
    """
    total = len(names)
    return {
        "pmid": str(pmid),
        "title": f"Synthetic record {pmid}",
        "pubdate": pubdate,
        "authors": [
            {
                "name": name,
                "index": index + 1,
                "is_first": index == 0,
                "is_last": index == total - 1,
                "equal_contrib": name in equal,
                "is_corresponding": False,
                "affiliation": "",
            }
            for index, name in enumerate(names)
        ],
    }


def roster_277() -> list[dict]:
    """
    A 277-person roster with the measured corpus's shape: 77 people who carry
    information, 190 who appear exactly once, 10 who hold a senior slot.

    277 = 190 stratum C + 10 stratum D + 70 stratum B + 7 stratum A.
    """
    seniors = [f"Senior Collaborator {index:02d}" for index in range(1, 11)]
    records = []

    # 10 records, 19 single-appearance middle authors each, a different senior
    # author closing each byline: 190 people who will never get a row.
    pmid = 1000
    for offset, senior in enumerate(seniors):
        one_offs = [f"One Off {offset * 19 + index:03d}" for index in range(19)]
        records.append(record(pmid + offset, f"{2015 + offset}-03-01", [PI, *one_offs, senior]))

    # The recurring middle authors: 70 people on two records each -> stratum B.
    recurring = [f"Support Candidate {index:03d}" for index in range(70)]
    records.append(record(1100, "2016-05-01", [PI, *recurring, seniors[0]]))
    records.append(record(1101, "2022-05-01", [PI, *recurring, seniors[0]]))

    # 7 people who front a paper exactly once. One appearance, but the first
    # slot makes them stratum A, so they do get a row.
    for index in range(7):
        records.append(
            record(1200 + index, f"{2017 + index}-07-01",
                   [f"Lead Candidate {index}", PI, seniors[1]])
        )
    return records


def shared_date_roster(extra_by_person: dict[str, int]) -> list[dict]:
    """
    Nine people who all first appear on the same date, with different appearance
    counts. `extra_by_person` sets how many later records each one is on, which
    is the only thing that varies between the two halves of the ordering test.
    """
    anchor = "Tail Anchor"
    names = sorted(extra_by_person)
    records = [record(2000, "2010-01-01", [PI, *names, anchor])]
    pmid = 2001
    for name, extra in sorted(extra_by_person.items()):
        for _ in range(extra):
            records.append(record(pmid, "2013-06-01", [PI, name, anchor]))
            pmid += 1
    return records


def png_size(path: str) -> tuple[int, int]:
    """Width and height straight out of the PNG IHDR chunk; no image library."""
    with open(path, "rb") as handle:
        head = handle.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"not a PNG: {path}")
    return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")


# ============================================================
# 1. The row-inclusion rule
# ============================================================

print("\n=== Row inclusion: strata A and B, and nobody else ===")

layout = analysis._gantt_rows(roster_277(), PI)
names = [row["name"] for row in layout["rows"]]

check("277 people are keyed out of the corpus", layout["n_people"], 277)
check("77 of them get a row", len(layout["rows"]), 77)
check("the 190 single-appearance people are counted, not drawn", layout["omitted"]["C"], 190)
check("the 10 senior collaborators are counted, not drawn", layout["omitted"]["D"], 10)
check("plotted plus omitted accounts for every person keyed",
      len(layout["rows"]) + layout["omitted"]["C"] + layout["omitted"]["D"], layout["n_people"])
check_false("no single-appearance person has a row",
            any(name.startswith("One Off") for name in names))
check_false("no senior collaborator has a row",
            any(name.startswith("Senior Collaborator") for name in names))
check("every row is stratum A or B", sorted({row["stratum"] for row in layout["rows"]}), ["A", "B"])
check("the recurring middle authors are all present",
      sum(1 for name in names if name.startswith("Support Candidate")), 70)

# The edge case a plain "appears twice" filter gets wrong in both directions:
# `_stratum` tests the last-author slot first, so one appearance in the first
# slot is a row and one appearance in the last slot is not.
leads = [row for row in layout["rows"] if row["name"].startswith("Lead Candidate")]
check("a single appearance in the first-author slot still gets a row", len(leads), 7)
check("and it is stratum A, not C", sorted({row["stratum"] for row in leads}), ["A"])

single_senior = analysis._gantt_rows(
    [record(1, "2020-01-01", [PI, "Solo Middle", "Solo Senior"])], PI
)
check("a single appearance in the last-author slot is stratum D, not C",
      (single_senior["omitted"]["D"], single_senior["omitted"]["C"]), (1, 1))
check("and neither gets a row", single_senior["rows"], [])

print("\n=== Row inclusion: the PI and the configured exclusions ===")

excluded = analysis._gantt_rows(
    shared_date_roster({f"Person {index}": 1 for index in range(9)}),
    PI,
    exclude_names={"person 3", "  Person 5  "},
)
excluded_names = [row["name"] for row in excluded["rows"]]
check_false("the PI is never a row", PI in excluded_names)
check_false("an excluded name is not a row even in the wrong case", "Person 3" in excluded_names)
check_false("an excluded name is not a row even with stray whitespace", "Person 5" in excluded_names)
check("the remaining seven people are rows",
      sorted(excluded_names), [f"Person {index}" for index in (0, 1, 2, 4, 6, 7, 8)])
check("exclusions leave the roster count too, not just the rows", excluded["n_people"], 7 + 1)

print("\n=== Row inclusion: records with no usable year ===")

undated = analysis._gantt_rows(
    [record(1, "2020-01-01", [PI, "Recurring Person", "A Senior"]),
     record(2, "2021-01-01", [PI, "Recurring Person", "A Senior"]),
     record(3, "1900-01-01", [PI, "Undatable Person", "A Senior"])],
    PI,
)
check("undated records are counted", undated["n_undated_records"], 1)
check_false("and contribute no person",
            any(row["name"] == "Undatable Person" for row in undated["rows"]))
check("the window comes from the datable records only", undated["window"], (2020, 2021))


# ============================================================
# 2. The ordering rule
# ============================================================

print("\n=== Ordering: first appearance, then name, never a count ===")

counts_a = {"Person 0": 4, "Person 1": 1, "Person 2": 2, "Person 3": 6, "Person 4": 1,
            "Person 5": 3, "Person 6": 5, "Person 7": 1, "Person 8": 2}
# Same nine people, same shared first date, appearance counts moved around.
counts_b = {"Person 0": 1, "Person 1": 6, "Person 2": 5, "Person 3": 1, "Person 4": 2,
            "Person 5": 4, "Person 6": 1, "Person 7": 3, "Person 8": 2}

order_a = [row["name"] for row in analysis._gantt_rows(shared_date_roster(counts_a), PI)["rows"]]
order_b = [row["name"] for row in analysis._gantt_rows(shared_date_roster(counts_b), PI)["rows"]]
totals_a = {row["name"]: row["n_appearances"]
            for row in analysis._gantt_rows(shared_date_roster(counts_a), PI)["rows"]}

check("all nine share a first date and are rows", len(order_a), 9)
check_true("the appearance counts really do differ", len(set(totals_a.values())) > 1)
check("within a shared first date the order is by name",
      order_a, [f"Person {index}" for index in range(9)])
check("permuting the appearance counts does not move a single row", order_b, order_a)

mixed = analysis._gantt_rows(
    [record(3000, "2019-04-01", [PI, "Zoe Later", "A Senior"]),
     record(3001, "2021-04-01", [PI, "Zoe Later", "A Senior"]),
     record(3002, "2012-04-01", [PI, "Adam Earlier", "A Senior"]),
     record(3003, "2013-04-01", [PI, "Adam Earlier", "A Senior"])],
    PI,
)
check("across different first dates the earlier arrival is first",
      [row["name"] for row in mixed["rows"]], ["Adam Earlier", "Zoe Later"])
check("the row order is exactly sorted by (first_date, name)",
      [row["name"] for row in layout["rows"]],
      [row["name"] for row in sorted(layout["rows"], key=lambda r: (r["first_date"], r["name"]))])


# ============================================================
# 3. Omitted people are accounted for on the chart face
# ============================================================

print("\n=== Accounting: the people who lost a row are declared on the figure ===")

face = analysis._gantt_face_text(layout)
check("the face text is three lines, matching the chrome budget", len(face), 3)
check_true("it states the plotted count against the full roster", "77 of 277" in face[0])
check_true("it states why those 77 were chosen",
           "first-author slot" in face[0] and "last-author slot" in face[0])
check_true("it states how many appear once", "190 appear once" in face[1])
check_true("it states how many hold a senior slot", "10 hold a last-author slot" in face[1])
check_true("it says where the omitted names can still be read",
           "_author_paper_matrix.csv" in face[1])
check_true("it discloses the name-string person model", "exact name string" in face[2])
check_true("it discloses that the PI and exclusions are never rows", "exclude_names" in face[2])

undated_face = analysis._gantt_face_text(undated)
check_true("undated records are declared when there are any",
           "1 records carry no usable year" in undated_face[1])
check_false("and not mentioned when there are none",
            "no usable year" in face[1])


# ============================================================
# 4. Censoring stays visible
# ============================================================

print("\n=== Censoring: still publishing is not the same as departed ===")

censoring = analysis._gantt_rows(
    [record(4000, "2010-01-01", [PI, "Early Bird", "A Senior"]),
     record(4001, "2012-01-01", [PI, "Early Bird", "A Senior"]),
     record(4002, "2013-01-01", [PI, "Middle Life", "A Senior"]),
     record(4003, "2016-01-01", [PI, "Middle Life", "A Senior"]),
     record(4004, "2015-01-01", [PI, "Still Here", "A Senior"]),
     record(4005, "2020-01-01", [PI, "Still Here", "A Senior"])],
    PI,
)
by_name = {row["name"]: row for row in censoring["rows"]}
check("the window spans the corpus", censoring["window"], (2010, 2020))
check("someone whose record reaches the window edge is right-censored",
      (by_name["Still Here"]["right_censored"], by_name["Still Here"]["left_censored"]),
      (True, False))
check("someone already publishing at the window start is left-censored",
      (by_name["Early Bird"]["left_censored"], by_name["Early Bird"]["right_censored"]),
      (True, False))
check("someone whose whole span sits inside the window is neither",
      (by_name["Middle Life"]["left_censored"], by_name["Middle Life"]["right_censored"]),
      (False, False))

lead_years = {row["name"]: row["lead_years"] for row in layout["rows"]}
check("a lead-slot year is recorded so the mark can differ from an ordinary year",
      lead_years["Lead Candidate 0"], [2017])
check("a support candidate has no lead-slot year", lead_years["Support Candidate 000"], [])


# ============================================================
# 5. Figure height scales with the row count and stays under the ceiling
# ============================================================

print("\n=== Geometry: height is a function of the row count ===")

check("the chrome budget is within the spec ceiling of 140 px",
      analysis.GANTT_CHROME_PX <= 140, True)
check("the row pitch is the spec's 24 px", analysis.GANTT_ROW_PITCH_PX, 24)

geom_77 = analysis._gantt_geometry(77)
MEASURED_DEFECT_PX = 21506  # the height this fix exists to remove
check("77 rows give 24 * 77 + chrome", geom_77["height_px"], 24 * 77 + analysis.GANTT_CHROME_PX)
check("which is 1988 px", geom_77["height_px"], 1988)
check("the width is fixed", geom_77["width_px"], 1100)
check_true("that is at least a 10x reduction on the measured defect",
           MEASURED_DEFECT_PX / geom_77["height_px"] >= 10)

for n_rows in (1, 9, 77, 277):
    ceiling = 24 * n_rows + 140
    height = analysis._gantt_geometry(n_rows)["height_px"]
    check(f"height at {n_rows} rows stays under the ceiling of {ceiling} px", height <= ceiling, True)
check("height grows by exactly one pitch per row",
      analysis._gantt_geometry(78)["height_px"] - geom_77["height_px"], 24)
# The worst case the rule has to survive: every one of the 277 people qualifying
# for a row. Still an order of magnitude under the measured defect.
check_true("even 277 qualifying rows stay far under the measured 21506 px",
           analysis._gantt_geometry(277)["height_px"] < MEASURED_DEFECT_PX / 3)

rect = geom_77["rect"]
check("the axes rectangle is exactly the row band",
      round(rect[3] * geom_77["height_px"]), 24 * 77)
check_true("and leaves the whole chrome budget outside it",
           abs((1 - rect[3]) * geom_77["height_px"] - analysis.GANTT_CHROME_PX) < 0.5)


# ============================================================
# 6. Rendering (matplotlib only)
# ============================================================

print("\n=== Rendering ===")

if importlib.util.find_spec("matplotlib") is None:
    print("  [SKIP] matplotlib is not installed; the render checks did not run")
else:
    with tempfile.TemporaryDirectory() as tmp:
        records_path = os.path.join(tmp, "_authors_parsed.json")
        with open(records_path, "w", encoding="utf-8") as handle:
            json.dump(roster_277(), handle)

        out = analysis.render_gantt(records_path, tmp, PI)
        check("the timeline is written", out is not None and os.path.exists(out), True)
        check("the saved PNG measures exactly the computed geometry",
              png_size(out), (1100, 1988))
        width, height = png_size(out)
        check_true("its aspect ratio is no longer 1:11", height / width < 2)

        # Two runs, same corpus, same bytes: a figure that changes without its
        # input changing cannot be diffed between profile runs.
        second = os.path.join(tmp, "second")
        os.makedirs(second)
        again = analysis.render_gantt(records_path, second, PI)
        with open(out, "rb") as h1, open(again, "rb") as h2:
            check("two runs over one corpus produce the same image", h1.read() == h2.read(), True)

        empty_path = os.path.join(tmp, "_empty.json")
        with open(empty_path, "w", encoding="utf-8") as handle:
            json.dump([record(9000, "2020-01-01", [PI, "Solo Middle", "Solo Senior"])], handle)
        check("no qualifying row means no figure rather than an empty axis",
              analysis.render_gantt(empty_path, tmp, PI), None)


print("\n" + "=" * 70)
print(f"Summary: {_passed} passed / {_failed} failed / {_passed + _failed} total")
print("=" * 70)
sys.exit(0 if _failed == 0 else 1)
