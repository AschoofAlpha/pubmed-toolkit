# Contributing

Bug reports and patches are welcome. This is a small project; there is no
process beyond what is below.

## Running the tests

```bash
pip install -e ".[all]"
python tests/test_verify.py
python tests/test_verify_regressions.py
python tests/test_pubmed_parse.py
python tests/test_search_query.py
python tests/test_identity_filter.py
python tests/test_pdf_validation.py
```

Every test is offline. Canonical records are synthetic fixtures, so the suite
never depends on CrossRef or NCBI being reachable, and it must stay that way —
a test that needs the network is a test that fails on someone else's train.

Lint with `ruff check .` before opening a pull request. CI runs the same on
Python 3.10, 3.11 and 3.12.

## The one rule that matters

**A verifier that reports a wrong answer confidently is worse than one that
reports nothing.**

Most of this codebase is shaped by that. Concretely:

- If a check could not run, say so. Do not fold it into a pass. `partial` exists
  precisely so a network failure is never reported as `verified`.
- Distinguish *no evidence* from *evidence of a problem*. A textbook missing
  from CrossRef and a DOI that was never registered are both "not found" to an
  HTTP client, and they mean opposite things to a reader.
- Prefer a missed detection over a false one. A tool that cries wolf gets
  switched off, and then it catches nothing at all. When a difference is
  genuinely ambiguous — author order, abbreviated pages, consortium bylines —
  accept it and document why.
- Never silently drop input. Truncation, unparseable entries and skipped
  validation all get a warning.

## When fixing a bug

Add a regression test to `tests/test_verify_regressions.py`, in a section named
after the defect, with a comment saying what went wrong and why it mattered.
That file is deliberately a list of everything this project once got wrong; it
is more useful as a record than as a tidy test suite.

## Scope

Open-access sources only. Sci-Hub, LibGen and similar will not be added — not
primarily as a legal question, but because university and hospital networks
block those domains, and a dependency on them makes the tool unusable exactly
where it is most wanted.

Claims in the README must be checkable. If you add a comparison against another
tool, link the evidence.
