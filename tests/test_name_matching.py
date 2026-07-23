#!/usr/bin/env python3
"""
Author-name parsing and comparison tests.

Two defects found by live testing are pinned here:

  * A name that normalises to nothing disabled the first-author check without
    leaving a trace, so a bibliography could be reported clean on the strength
    of a comparison that never happened.
  * 'Given SURNAME' bylines ('Jing WU') parsed the given name as the surname.

Both are about the same risk in opposite directions: a check that silently does
not run, and a check that runs on the wrong token. No network access — every
canonical record here is a synthetic fixture.

Run: python tests/test_name_matching.py
"""

from __future__ import annotations

import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pubmed_toolkit.verify.checks import compare_fields  # noqa: E402
from pubmed_toolkit.verify.models import Reference  # noqa: E402
from pubmed_toolkit.verify.normalize import (  # noqa: E402
    norm_author,
    surname_candidates,
    surname_of,
    surnames_agree,
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


class LogCapture(logging.Handler):
    """Collects formatted warnings so a skipped check can be asserted on."""

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


_verify_log = logging.getLogger("pubmed_toolkit.verify")
_verify_log.setLevel(logging.WARNING)


def compare_with_log(ref: Reference, meta: dict) -> tuple[int, list[str]]:
    """Run compare_fields and return (issue count, warnings it emitted)."""
    capture = LogCapture()
    _verify_log.addHandler(capture)
    try:
        issues = compare_fields(ref, meta, "pubmed")
    finally:
        _verify_log.removeHandler(capture)
    return len(issues), capture.messages


# ======================================================================
print("\n--- surname_of: the seven formats that must all work at once ---")
# ======================================================================
# 'Bass AJ' and 'Jing WU' have the same shape, so these cases can only be
# satisfied together, never one rule at a time.
check("PubMed, one initial", surname_of("Bray F"), "bray")
check("PubMed, two initials", surname_of("Bass AJ"), "bass")
check("comma format", surname_of("Bray, Freddie"), "bray")
check("western order", surname_of("Freddie Bray"), "bray")
check("given name first, surname in caps", surname_of("Jing WU"), "wu")
check("two-letter caps surname", surname_of("Yi LI"), "li")
check("apostrophe survives", surname_of("O'Brien M"), "obrien")


# ======================================================================
print("\n--- surname_of: the shape rules the seven cases rest on ---")
# ======================================================================
check("long caps token is a surname, not initials", surname_of("Maria GARCIA"), "garcia")
check("dotted initials are still initials", surname_of("Bass A.J."), "bass")
check("comma with caps surname", surname_of("WU, Jing"), "wu")
check("three initials stay initials", surname_of("Bray FJK"), "bray")
# An unrecognised short all-caps token keeps the PubMed reading: that format is
# what this toolkit ingests by the thousand, so it is the safer default.
check("unknown caps token defaults to initials", surname_of("Smith QZ"), "smith")
check("empty input", surname_of(""), "")
check("single token", surname_of("Bray"), "bray")


# ======================================================================
print("\n--- surname_of: the case that is genuinely undecidable ---")
# ======================================================================
# 'Smith MA' is Ma the surname or M.A. the initials, and nothing in the string
# says which. The lookup commits to the surname reading and is wrong here — but
# comparison never depends on that guess, so the wrong guess cannot become a
# false mismatch. This is the reason surname_of must not be used for checking.
check("undecidable byline is guessed wrong", surname_of("Smith MA"), "ma")
check("...but the comparison still agrees", surnames_agree("Smith MA", "Smith M"), True)
check("...and compare_fields reports nothing",
      len(compare_fields(Reference(key="k", first_author="Smith MA"),
                         {"first_author": "Smith M"}, "pubmed")), 0)


# ======================================================================
print("\n--- comparison keeps every reading, whatever surname_of guessed ---")
# ======================================================================
check("caps surname matches PubMed style", surnames_agree("Jing WU", "Wu J"), True)
check("initials match a bare family name", surnames_agree("Bass AJ", "Bass"), True)
check("a real disagreement is still a disagreement",
      surnames_agree("Bray AJ", "Bass AJ"), False)
check("initials are not offered as a surname reading",
      surname_candidates("Bass AJ"), {"bass", "bassaj"})
# A capitalised surname outside the lookup table stays a candidate as long as it
# is pronounceable, so an incomplete table costs a missed check, never a false
# alarm. 'MU' is not in the table; 'AJ' could not be a syllable in any case.
check("unlisted caps surname survives as a candidate",
      surnames_agree("Jing MU", "Mu J"), True)
check("the surname_of guess is never dropped", surnames_agree("MU J", "Mu Jing"), True)


# ======================================================================
print("\n--- compare_fields: shared initials are not a shared author ---")
# ======================================================================
# The regression that matters most: 'Bray AJ' and 'Bass AJ' differ only in the
# surname. Nothing added for the caps-surname format may let that pass.
count, _ = compare_with_log(Reference(key="k", first_author="Bray AJ"), {"first_author": "Bass AJ"})
check("same initials, different surname -> mismatch", count, 1)

issues = compare_fields(Reference(key="k", first_author="Bray AJ"),
                        {"first_author": "Bass AJ"}, "pubmed")
check("the mismatch is on first_author", issues[0].field, "first_author")
check("and carries the supplied value", issues[0].supplied, "Bray AJ")

count, _ = compare_with_log(Reference(key="k", first_author="Bass AJ"), {"first_author": "Bass AJ"})
check("identical bylines agree", count, 0)
count, _ = compare_with_log(Reference(key="k", first_author="Jing WU"), {"first_author": "Wu J"})
check("caps-surname byline agrees with PubMed order", count, 0)
count, _ = compare_with_log(Reference(key="k", first_author="Jing WU"), {"first_author": "Zhang Q"})
check("wrong author still flagged despite permissive matching", count, 1)


# ======================================================================
print("\n--- non-Latin names are compared, not dropped ---")
# ======================================================================
check("CJK name survives normalisation", norm_author("李四"), "李四")
check("identical CJK names agree", surnames_agree("李四", "李四"), True)
check("different CJK names disagree", surnames_agree("李四", "王五"), False)
# A single CJK character is a complete surname, so it must stay a candidate even
# though a single Latin letter is only ever an initial.
check("spaced CJK name matches the solid form", surnames_agree("李 四", "李四"), True)
check("spaced CJK name matches its own surname", surnames_agree("李 四", "李"), True)
check("a single Latin letter is never a candidate",
      "f" in surname_candidates("Bray F"), False)

count, _ = compare_with_log(Reference(key="k", first_author="李四"), {"first_author": "王五"})
check("CJK mismatch is reported", count, 1)
count, _ = compare_with_log(Reference(key="k", first_author="李四"), {"first_author": "李四"})
check("CJK match is not reported", count, 0)


# ======================================================================
print("\n--- an uncomparable name is skipped out loud, never silently ---")
# ======================================================================
# What is left after the fix above: a byline that carries no letters at all.
# It cannot be compared, and the old code let that read as agreement.
count, warnings = compare_with_log(Reference(key="k", first_author="???"),
                                   {"first_author": "Bass AJ"})
check("unnormalisable name raises no false mismatch", count, 0)
check("...and says the check was skipped", len(warnings), 1)
check("...naming the field", "first-author check skipped" in warnings[0], True)
check("...and the entry", "k" in warnings[0], True)

count, warnings = compare_with_log(Reference(key="k", first_author="Bass AJ"),
                                   {"first_author": "--"})
check("an uncomparable canonical name is skipped too", count, 0)
check("...and is also announced", len(warnings), 1)

count, warnings = compare_with_log(Reference(key="k", first_author="Bass AJ"),
                                   {"first_author": "Bass AJ"})
check("a normal comparison stays quiet", warnings, [])
count, warnings = compare_with_log(Reference(key="k", first_author="Bray AJ"),
                                   {"first_author": "Bass AJ"})
check("a real mismatch is not reported as a skip", warnings, [])


# ======================================================================
print("\n" + "=" * 70)
print(f"Summary: {_passed} passed / {_failed} failed / {_passed + _failed} total")
print("=" * 70)
sys.exit(0 if _failed == 0 else 1)
