# Changelog

Notable changes to pubmed-toolkit. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] — 2026-07-27

`profile` now writes a self-contained HTML report as its primary output. The
Markdown and the JSON are unchanged and still written.

### Added

- **`advisor_profile_<timestamp>.html`**, written beside the `.md` and `.json`.
  One file, no network: system fonts, inline SVG figures, and the SVG XML
  namespace as the only URI in the document. Every section, every caveat and
  every roster row is rendered server-side, so the page is complete with
  JavaScript disabled and complete on paper.
- **Five figures** (`profile/charts.py`, `profile/svg.py`): person activity
  timeline, time to a first-author slot, observed activity span, records per
  year, team size. Each is a pure metric-dict-to-SVG-string function that states
  its own denominator inside the SVG, replaces a suppressed aggregate with a
  plate naming the actual n and the floor, and emits no percent sign at any
  sample size. None of them ranks anyone.
- **`person_roster` rows carry `years`, `lead_years` and `first_date`**, and
  `build_people` people carry `lead_years`. Additive only: no existing key
  changes name, type or value, `SCHEMA_VERSION` stays at 1, and
  `tests/test_profile.py` passes unchanged.
- `tests/test_charts.py` (304), `tests/test_html_report.py` (98),
  `tests/test_gantt.py` (62) and `tests/test_cli_profile.py` (50).

### Fixed

- **The activity timeline plotted every co-author, at 1934 x 21506 px.** A real
  run — Stockwell Brent / Columbia, 10 years, 62 papers — drew all 277 people on
  one axis; 190 of them appear exactly once and rendered as a single dot, and
  reading the image took about 20 screens of scrolling. The spec already
  excludes single-appearance people from every aggregate; the chart contradicted
  it by drawing them anyway. Rows are now the cohort the aggregates are computed
  over — everyone with two or more records who never holds the senior slot — and
  everyone else is counted in a per-year strip along the axis foot and named in
  the roster. Same corpus, same rule: **77 rows at 1100 x 1984 px**.
- **`analyze`'s gantt ordered people by output** within a shared first-appearance
  date, and labelled its equal-contribution legend entry "co-first" for a flag
  that is position-blind. Both corrected; the same corpus now renders at
  1100 x 1939 px instead of 1934 x 21506.

### Changed

- `profile` no longer writes `student_activity_gantt.png` or any other raster.
  `analysis.render_gantt` is unchanged in signature and still serves `analyze`.
  Section 2 of the Markdown names where the timeline is instead of embedding it.

## [0.2.0] — 2026-07-22

The first release fixed nothing it did not first get wrong. Everything below
was found by code review, by running the tool against live APIs, or both — and
each item has a regression test naming it.

### Fixed — correctness

- **Author comparison went blind on non-Latin names.** `norm_author` filtered
  with `[^a-z]+`, so any CJK, Cyrillic or Greek surname reduced to the empty
  string and the first-author check was skipped entirely, without a word. On a
  tool whose stated purpose is disambiguating Chinese names, this was the worst
  bug in the release.
- **Ambiguous name order produced false mismatches.** `Jing WU` is structurally
  identical to `Bray FJ`; the old heuristic read the short all-caps token as
  initials and flagged correct citations as the wrong author. Comparison now
  considers every plausible reading and accepts any overlap.
- **PubMed author search returned ~2% of a Western-named author's papers.**
  The query was always quoted, which suppresses PubMed's term expansion:
  `"Stockwell Brent"[Author]` matched 6 records where the same person has 253.
  Queries now include a wildcarded initials form.
- **Results were silently truncated at `retmax`.** A search matching more
  records than were retrieved reported no problem. It now warns, and narrows
  server-side using the configured affiliation keywords when it can.
- **`@string` macros were compared literally.** `journal = nat` was checked as
  the string `'nat'` against `Nature` and reported as a mismatch. Macros are now
  resolved, including `#` concatenation and the built-in month names.
- **Paren-delimited entries were dropped.** `@article(...)` is legal BibTeX and
  vanished from the bibliography without warning.
- **A dropped TLS handshake was reported as an unfinished check.** Only HTTP
  429/503 were retried, so a transient connection error downgraded a verifiable
  entry to `partial`. Connection-level failures are now retried too.

### Fixed — reporting honesty

- **`verified` no longer means "we asked and something failed".** When CrossRef
  answers and Entrez times out, the bidirectional check never ran; such entries
  are now `partial`, counted separately, and never certified.
- **An unregistered DOI is a finding, not an absence.** A DOI that was never
  registered is the signature of a fabricated citation and is now reported under
  its own heading, rather than filed with textbooks under "not indexed".
- **PMID cleaning rejects instead of salvaging.** Scavenging digits turned
  `PMC3388858` into `3388858` — a real but unrelated PMID that would then be
  "verified" against the wrong paper.
- **A stray brace no longer lets one entry swallow the next**, silently
  inheriting its DOI and PMID.
- Commented-out (`%`) entries are no longer parsed and looked up.

### Added

- Batched identifier resolution: DOIs are ORed into one ESearch and PMIDs
  fetched 200 at a time, so a 500-entry bibliography costs a handful of Entrez
  requests instead of a thousand. NCBI's PMC ID Converter is deliberately not
  used — it only covers PMC, and would silently disable the bidirectional check
  for Lancet, NEJM and JAMA.
- `retmax` configuration option for `fetch`.
- ORCID is used directly as a PubMed search term (`[auid]`) when configured.
- Loud warning when PyMuPDF is missing, instead of silently skipping PDF
  identity validation.

### Changed

- **Dependencies restructured.** `verify` now needs nothing beyond the standard
  library; `requests` is the only hard dependency. PyMuPDF moved to the `fetch`
  extra because it is AGPL-3.0 and an MIT package should not pull copyleft into
  a user's environment without their choosing it. Install `.[fetch]` or `.[all]`
  for the downloader.
- Test suite grew from 42 to 222 assertions, all offline.

### Security / privacy

- Removed a real researcher's ORCID, institution and email address, which had
  been baked into the shipped default configuration and test fixtures.

## [0.1.0] — 2026-07-22

Initial public release. Merged two previously separate local tools — a PubMed
harvester with author disambiguation, and a set of one-off reference-checking
scripts — into one package with a shared HTTP and normalisation layer.

Published and superseded the same day; see 0.2.0 for what it got wrong.

[0.2.0]: https://github.com/AschoofAlpha/pubmed-toolkit/releases/tag/v0.2.0
[0.1.0]: https://github.com/AschoofAlpha/pubmed-toolkit/releases/tag/v0.1.0
