# Changelog

Notable changes to pubmed-toolkit. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
