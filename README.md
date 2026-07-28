# pubmed-toolkit

Decide whether to join a specific researcher's lab, from what PubMed records
about it.

[![CI](https://github.com/AschoofAlpha/pubmed-toolkit/actions/workflows/ci.yml/badge.svg)](https://github.com/AschoofAlpha/pubmed-toolkit/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

English | [简体中文](README.zh-CN.md)

You are choosing a PhD or master's advisor. You have a name, a lab page written
by the lab, and no way to check any of it. `profile` takes that one name and
reports what the publication record actually shows about being their student:
who leads their papers, how long people stay, how long it takes a newcomer to
get a first-author slot — each count printed with the denominator it came from.

It does not score, rank, or compare researchers, and it emits no overall number.
See [What it will not tell you](#what-it-will-not-tell-you), which is the more
important half of the output.

| Command | What it does |
| --- | --- |
| `profile` | **The point of this repo.** One named PI → a factual report on their lab's publication record |
| `fetch` | Builds the corpus `profile` reads: search PubMed → keep only this researcher's papers → optionally race 8 open-access sources for the PDFs |
| `verify` | Unrelated, and honestly so: check a `.bib` against CrossRef and PubMed. It shares the HTTP layer and nothing else |

---

## What this is not

**Not a literature search tool.** There is no topic search, no keyword mode, no
"find me papers about X". The only supported query is one person. If you want
general search, use `metapub`, `pyalex`, or `paperscraper` — they cover more
sources, they are on PyPI, and this tool loses that comparison on every axis.

**Not a ranking tool.** Citation counts, h-index, journal impact factor,
quartile and CAS partition are out of scope. They are not computed, not stored,
and not written to any intermediate file. Section 14 of every report lists what
was deliberately left out and why, so an omission is distinguishable from an
oversight.

The narrow scope is the point. Everything below exists because a prospective
student is asking about one person, and that question has a defensible answer
where "which lab is best" does not.

---

## Why the report looks the way it does

**PubMed only contains people who published.** A student who joined, struggled
for three years, and left without a paper is absent from every number in the
report — from the numerator *and* the denominator. The size of that missing
group cannot be recovered from bibliographic metadata, and no statistical
treatment repairs it. The report says this in prose in Section 0 rather than as
a footnote, because it changes how every later number should be read.

**Searching PubMed by name returns several different people.** Romanised
Chinese names collide heavily: one `"<surname> <givenname>"[Author]` query
routinely spans a clinician, an environmental scientist and a computer vision
researcher who share a name and nothing else. A profile built on that corpus
describes three people at once. This is why `fetch`'s author disambiguation is
load-bearing here rather than a nicety, and why the report refuses to run
without identity evidence configured.

**Small labs produce small denominators.** A median over four people is not a
median. Below the minimum sample size the report prints the underlying rows
instead of an aggregate, and percentages are withheld entirely below n=20.
The thresholds are fixed in the spec and are deliberately not exposed as flags.

---

## Install

```bash
git clone https://github.com/AschoofAlpha/pubmed-toolkit.git
cd pubmed-toolkit

pip install -e ".[fetch]"         # profile + fetch: PDF download and identity validation
pip install -e ".[analysis]"      # + the `analyze` subcommand's raster charts (matplotlib)
pip install -e .                  # verify only — no third-party dependencies
```

Python 3.10+. Not published on PyPI; install from source.

`profile` needs nothing beyond the standard library once a corpus exists,
including its figures: every chart in the HTML report is an SVG string generated
in Python and written into the file. **matplotlib is not used by `profile` at
all.** It is needed only by `analyze`, which draws PNGs. If the drawing module
cannot be imported for any reason, each figure slot is replaced by a stated
`chart unavailable — <package> not installed` placeholder and the rest of the
report — every section, every table, every caveat — is written as normal.

PyMuPDF is deliberately *not* a hard dependency: it is AGPL-3.0, this project is
MIT, and an MIT package should not pull copyleft into your environment without
you choosing it.

---

## `profile` — what the record says about being this person's student

```bash
cp config.example.json config.json   # fill in author_name and author_identity
python -m pubmed_toolkit fetch --config config.json --no-download
python -m pubmed_toolkit profile --config config.json
```

Three files land in the output directory, sharing one timestamp:

| File | Role |
| --- | --- |
| `advisor_profile_<timestamp>.html` | **The report you read.** Every section, five inline figures, every caveat, the whole roster |
| `advisor_profile_<timestamp>.md` | The same sections as plain text, for diffing, grepping and pasting into notes |
| `advisor_profile_<timestamp>.json` | The same numbers without the prose, for anything programmatic |

The Markdown and the JSON are unchanged in content. The HTML is the primary
output because two things do not fit in Markdown: a figure, and 277 rows that a
reader needs to be able to collapse.

```bash
--config PATH          # identity and advisor settings
--output-dir DIR       # defaults to pubmed_results, same as fetch
--papers-json PATH     # defaults to the newest papers_*.json in --output-dir
--pi-name NAME         # overrides config's author_name
--log-level LEVEL
```

Exit code 1 when the report is refused (see [Gates](#gates)), 0 otherwise. A
refused run still writes all three files; each contains the gate, the observed
values and nothing else.

### The HTML report

One file, no network. Opening it from a `file://` URL with the network cable
unplugged renders exactly what it renders online: the fonts are system fonts,
the figures are inline SVG, and the only URI anywhere in the document is the
SVG XML namespace, which no browser fetches. It is safe to keep on a laptop or
a thumb drive, which matters, because it is personal data about named people.

Five figures, one per section that earns one:

| Figure | Section | What it shows |
| --- | --- | --- |
| Person activity timeline | 2 | One row per person in the cohort every aggregate is computed over: everyone with two or more records who never holds the senior slot. Filled square = a year with a first-author record, hollow = a year with records but none in that slot, dashed tail = censored at the window edge |
| Time to a first-author slot | 4 | Two strips on one axis — people who reached one above it, people who have not yet below it. The lower strip is not optional: the upper one alone reads as a promise |
| Observed activity span | 5 | Four lanes by censoring state, so a span truncated by the search window is never mistaken for a short one |
| Records per year | 9 | One column per year in the window, including zero-count years, with partial and indexing-lag bins hatched and labelled |
| Team size | 10 | Authors per record, and separately the records led by a lead-trainee or support candidate |

Text in a figure is real `<text>`: Ctrl+F reaches a person's name inside the
timeline, and a screen reader reads it. Every figure states its own denominator
inside the SVG as well as in the caption, because a chart gets screenshotted and
separated from its caption. Every figure carries its caveats verbatim beneath
it, never behind a disclosure.

**What the page does not do.** No figure ranks anyone. Nothing on the page is
sortable by appearances, lead slots or equal-contribution flags — the roster's
order control offers name and year only, and no count option exists to click,
because one click on `appearances` would turn the roster into a productivity
leaderboard. There is no colour ramp, no threshold band, no red or green, no
"good" region: any shading that separates better from worse is a grade. No
percent sign appears in any figure at any sample size. Below a metric's floor
the median is replaced by a plate stating the actual n and the floor it needed,
and every underlying dot stays — an empty axis reads as a measured zero.

The single-appearance people who have no row on the timeline are not hidden:
they are counted in a per-year strip along its foot, named in the roster table,
and stated in the figure's own caption.

### What is in the report

15 sections, each a count with its denominator and a caveat naming what the
count cannot mean:

| Section | What it answers |
| --- | --- |
| 0 | What this report is and is not — read first |
| 1 | Corpus provenance: the query, the identity evidence, every excluded record |
| 2 | The people, with an activity timeline and a position label per person |
| 3 | Who occupies the first-author slot, on the paper side and the person side |
| 4 | Years from a person's first appearance to their first first-author slot |
| 5 | How long people remain visible in the record, with censoring stated |
| 6 | Group size and turnover per year |
| 7 | Where the PI sits on their own bylines |
| 8 | Shared-authorship flags, and whether they mark shared first or shared senior |
| 9 | Records per year, with the partial and lag-affected bins marked |
| 10 | Authors per record |
| 11 | Journal strings, verbatim and unnormalised — no impact factor, ever |
| 12 | Affiliation strings, verbatim and ungrouped |
| 13 | Every title, by year — you classify the topics, the tool does not |
| 14 | What was deliberately not computed, and why |

Position labels are `lead-trainee candidate`, `support candidate`, `single
appearance` and `senior collaborator`. They are inferences from byline position,
not facts about a person: a PhD student, postdoc, technician, staff scientist,
clinical fellow, rotation student and visiting scholar all produce the same
positional shape, and no PubMed field separates them.

### Gates

Five conditions make the whole report meaningless rather than merely noisy. Each
produces a refusal document containing the gate, the observed values and the
fix, and nothing else. There is no degrade-with-a-warning path, because a
warning gets scrolled past and a missing report does not.

| Gate | Fires when |
| --- | --- |
| G1 truncation | `esearch` matched more records than were retrieved, so every count is wrong by an unbounded amount |
| G2 identity fallback | No paper passed identity verification, so the corpus is every paper by everyone sharing the name |
| G3 weak identity config | No ORCID, affiliation keyword or email domain is configured at all |
| G4 no structured authors | The input has no per-author records — including any attempt to run from `papers_*.xlsx` |
| G5 empty corpus | Nothing survived the record exclusions |

G4 refuses the Excel export by extension, without opening it. `build_author_records`
silently falls back to splitting the author *string* when a record has no PMID
match, which forces `equal_contrib=False`, `is_corresponding=False` and
`affiliation=""` for every author. That converts "unknown" into a confident zero
and is the most dangerous silent failure in the pipeline.

### What it will not tell you

This is a description of a publication record. It is not a description of a
person, and the gap between the two is large:

- **It says nothing about supervision.** Advising style, whether anyone graduated, funding stability, working hours, lab culture, how conflicts get handled, what happened to people who left — none of it is in PubMed. Those are the things you actually want to know, and none of them are here.
- **Everyone who left without publishing is invisible.** They are missing from both sides of every ratio. A lab that loses half its students and publishes well with the other half is indistinguishable from one that keeps everybody.
- **Lab-member classification is imperfect, and unfixably so.** PubMed affiliation coverage is patchy and era-dependent: older records often carry only the first author's affiliation, so affiliation is reported as a per-person attribute rather than used to decide who is in the lab. Co-authors are not lab members, and no field separates them.
- **People are keyed by name string.** Two people with one romanised name merge into one row with an inflated count and an over-long span; one person recorded two ways splits into two short rows. The report prints its strict-keying and loose-keying person counts side by side — that gap is the error bar on every person-level number.
- **Small labs produce small denominators.** Aggregates below the floor are replaced by the rows they were built from. That is not a bug to work around; four data points do not support a median.
- **Every span is a gap between two publication dates,** not time in the lab. The first two to three years of a PhD are invisible by construction, and a paper can appear a year or more after the person has left.
- **No overall score is emitted, by design.** Any weighted index would encode weights this data cannot justify, and would recreate the people-ranking this tool exists to avoid.
- **The PI's own byline position cannot be measured from a `fetch` corpus.** `fetch` keeps only first/last/corresponding-author papers, so that filter — not the data — decides the answer. The report detects this and prints the caveat instead of a number.

Treat the output as personal data about named individuals. Keep it local. Do not
publish it without the consent of the people described.

---

## `fetch` — build the corpus

```bash
python -m pubmed_toolkit fetch --config config.json --no-download
```

`--no-download` skips PDFs, which `profile` does not need. Without it you also
get the PDFs, a per-PDF validation report and a run log.

### Author disambiguation

This is what makes the profile worth reading. A name match alone is not enough;
it must additionally satisfy one of:

| Priority | Signal | Strength |
| --- | --- | --- |
| 1 | ORCID (`<Identifier Source="ORCID">`) | Strongest — globally unique |
| 2 | Email domain | Strong, but PubMed usually omits emails |
| 3 | Affiliation keyword, fuzzy-matched | The workhorse |

Set `require_affiliation: true` for strict mode, where a name match satisfying
none of the three is rejected. List every way the institution appears in PubMed
affiliation strings — abbreviations, affiliated hospitals, translated forms.
PubMed does not normalise them.

On one real run against a common name, this reduced 54 raw PubMed hits to the 10
belonging to the target researcher; ORCID accounted for 6 of the 10 and
affiliation keywords for 4. The other 44 were other people. Your numbers will
differ — this is one data point, not a benchmark.

### PDF download and identity validation

Eight open-access sources are raced in parallel; the first result that passes
identity validation wins and the rest are cancelled. After download, text is
extracted from the PDF and checked against the target DOI and title tokens.
Failures go to `pdfs/suspect/` with the reason recorded in
`pdf_validation_report_*.csv` rather than being reported as successes.

Downloaders that validate at all check the `%PDF` magic bytes — that is format,
not identity. `pdf2doi` does this well but as a separate tool pointed at files
you already have.

### Other subcommands

```bash
python -m pubmed_toolkit download                  # retry PDFs from an existing papers_*.json
python -m pubmed_toolkit analyze --pi-name "..."   # authorship matrix, activity gantt, topic charts
python -m pubmed_toolkit clean-cache --max-age-days 30
```

`analyze` predates `profile` and overlaps with it. It applies no sample-size
floors and attaches no caveats, so prefer `profile` for anything you intend to
act on. Its gantt PNG is the only raster this project draws and the only place
matplotlib is used; it keys people by exact name string, where `profile` keys
them by ORCID and affiliation evidence, so the two timelines will not agree on
who is who.

---

## `verify` — check a bibliography

A separate tool that happens to live in the same repository. It shares the HTTP
and normalisation layer with `fetch` and has nothing to do with advisor
profiles; it is here because it was written against the same PubMed client.

```bash
python -m pubmed_toolkit verify references.bib --email you@example.com
```

Writes a Markdown report and a JSON record of every lookup to `verify_results/`.

```
verified=41  conflicts=2  unregistered=1  mismatch=6  partial=0  not_found=5  error=0  (total 55)
```

| Status | Meaning |
| --- | --- |
| `verified` | Resolved, **every check ran**, and everything agreed |
| `partial` | Resolved and nothing disagreed, but a lookup failed, so at least one check — possibly the DOI/PMID cross-check — never ran |
| `mismatch` | Resolved, but a field disagrees with the canonical record |
| `not_found` | No canonical record and nothing proven wrong. Often legitimate — books, national guidelines and many non-English journals are simply not in CrossRef or PubMed |
| `error` | Nothing resolved and a lookup failed. The verdict is unknown, not negative |

Two findings are counted separately from the statuses, because either can attach
to an entry whose status is something else: **conflicts** (the DOI and the PMID
resolve to different papers) and **unregistered identifiers** (a DOI that was
never registered, or a PMID with no record).

The problem it addresses: with LLMs drafting bibliographies, the interesting
failure is no longer the wholly invented reference — it is the entry stitched
together from two real papers, where the DOI resolves, the PMID resolves, and
they are different articles. An analysis of NeurIPS 2025 found at least 53
accepted papers carrying 100+ hallucinated citations,¹ and ICML 2026
desk-rejected 497 submissions over LLM policy violations.²

### The bidirectional check

For an entry carrying both identifiers, each is resolved independently and the
results must agree in both directions:

```
supplied DOI  --Entrez ESearch-->   PMID'   ==  supplied PMID ?
supplied PMID --Entrez ESummary-->  DOI'    ==  supplied DOI  ?
```

An entry citing Bass 2014's DOI with Dixon 2012's PMID passes any
existence-only check — both identifiers are real and both resolve. Here it is
reported as a `conflict`, which is a stronger finding than any single field
mismatch: at least one identifier was not taken from the paper being cited.

Absence of a resolution is never reported as a conflict. If a DOI cannot be
resolved to a PMID, that is missing evidence, not contradicting evidence.

Three further distinctions are deliberate, and each was a bug first:

- **`partial` is not `verified`.** If CrossRef answers and Entrez times out, the bidirectional check never happened. Certifying that entry would be the exact "succeeded while being wrong" failure this tool exists to catch — and it gets *worse* on large bibliographies, since NCBI returns 429 precisely under load.
- **An unregistered DOI is not "not found".** A citation pointing at nothing is the signature of fabrication; a textbook missing from CrossRef is a coverage gap. They get separate sections so the first is never filed under the second's reassuring heading.
- **`not_found` is not `error`.** One is a finding, the other is a failure to obtain one.

Try it on the worked example, which contains three correct entries and four
deliberately defective ones:

```bash
python -m pubmed_toolkit verify examples/references.example.bib --email you@example.com
```

Useful flags:

```bash
--fail-on-mismatch     # exit 1 when anything is wrong (for CI)
--no-pubmed            # CrossRef only; skips the bidirectional check
--ncbi-api-key KEY     # raises the Entrez rate limit from 3/s to 10/s
--max-workers 6        # concurrent lookups
--timeout 12           # hard per-request timeout, seconds
```

Accepts `.bib` or JSON (`[{"key": ..., "doi": ..., "pmid": ...}, ...]`).

### Avoiding false positives

A verifier that cries wolf gets switched off, so equivalent-but-differently-written
values are treated as agreement: abbreviated page ranges (`202-9` vs `202-209`),
consortium authorship, author ordering, diacritics and journal abbreviations
(`Følling`/`Folling`, `Lancet`/`The Lancet`).

What stays flagged is the case that signals a genuinely bad citation: a named
person absent from the paper's author list, a wrong year or journal, or
identifiers pointing at different works.

---

## Scope

**Open-access sources only:** PMC, Unpaywall, Europe PMC, Semantic Scholar,
CORE, OA Button, bioRxiv/medRxiv, and DOI redirection.

There is no Sci-Hub or LibGen support and none will be added. Papers behind a
paywall with no open-access copy will fail to download — use your institutional
access for those. This keeps the tool usable inside university and hospital
networks, which commonly block those domains.

Respect the rate limits of every API used here. Set a contact email: CrossRef
and NCBI both ask for one and may throttle anonymous traffic.

---

## Tests

1067 assertions, all offline — every canonical record is a synthetic fixture, so
the suite never depends on CrossRef or NCBI being reachable. Plain scripts, no
pytest.

```bash
python tests/test_charts.py             # 304 — every figure, drawn and suppressed, at every degenerate n
python tests/test_profile.py            # 226 — gates, strata, every metric, suppression floors
python tests/test_html_report.py        #  98 — page structure, escaping, what is never collapsed
python tests/test_verify_regressions.py #  96 — every bug found in review or live use
python tests/test_verify.py             #  71 — normalisation, cross-check, BibTeX
python tests/test_gantt.py              #  62 — the analyze timeline: rows, ordering, figure height
python tests/test_bibtex_pmid_sources.py #  50 — where a PMID may legitimately hide in a .bib
python tests/test_cli_profile.py        #  50 — what the subcommand writes to disk, end to end
python tests/test_name_matching.py      #  45 — surname vs initials, CJK names
python tests/test_pubmed_parse.py       #  35 — XML parsing edge cases
python tests/test_search_query.py       #  21 — PubMed query construction
python tests/test_identity_filter.py    #   6 — author disambiguation
python tests/test_pdf_validation.py     #   3 — PDF identity validation
```

The regression suites exist because those areas shipped with real defects. The
search-query tests in particular lock in a recall bug that no unit test could
have caught: the original query was always quoted, which suppresses PubMed's
term expansion, so an author indexed as `Stockwell BR` matched 6 records
instead of 253.

---

## Limitations

Profile-specific limits are in [What it will not tell you](#what-it-will-not-tell-you).
Across the whole toolkit:

- Disambiguation quality depends entirely on your affiliation keyword list. A researcher who changed institutions needs every one of them listed, or their earlier papers silently drop out of the corpus.
- The disambiguation filter has not been benchmarked against a labelled dataset. S2AND provides a suitable harness; no precision/recall numbers are claimed here because none have been measured.
- PubMed rarely includes author emails, so that signal seldom fires in practice.
- The author query is broad by design, so a common surname can exceed `retmax`. The tool narrows server-side using your affiliation keywords and says so; without those keywords it warns rather than silently truncating. A truncated corpus is refused outright by the profile report.
- Two metadata sources only, CrossRef and PubMed. Works indexed only in arXiv, DBLP or the ACL Anthology come back as `not_found`.
- CrossRef holds no individual authors for many consortium papers, so author checking for those relies on PubMed.
- **`verify` throughput is bounded by NCBI's rate limit, not by `--max-workers`.** Identifier resolution is batched — DOIs are ORed into one ESearch and PMIDs fetched 200 at a time — so a 500-entry bibliography costs a few Entrez requests rather than a thousand. What remains serial is CrossRef, one request per entry.
- Batching deliberately does **not** use NCBI's PMC ID Converter, which would resolve DOIs to PMIDs in a single call. It only covers PMC: Lancet, NEJM and JAMA DOIs all return "not found in PMC" while ESearch resolves them correctly, so using it would silently disable the bidirectional check on exactly the clinical literature where it matters most.

---

## Related work

**Advisor and lab evaluation.** Nothing found that reads a publication record
for this question. The adjacent tools answer a different one: OpenAlex, Scopus
and Web of Science rank researchers by citation-derived metrics, which is the
use case excluded here; `scholarly` and `pybliometrics` retrieve those metrics
but perform no per-lab analysis; ORCID and ResearchGate present a self-reported
profile rather than a derived one.

**Harvesting and disambiguation.**

- [pypaperretriever](https://github.com/JosephIsaacTurner/pypaperretriever) — DOI/PMID → PDF via Unpaywall, Entrez and CrossRef
- [paperscraper](https://github.com/jannisborn/paperscraper) — metadata across PubMed, arXiv and the *Rxiv preprint servers
- [metapub](https://github.com/metapub/metapub) — NCBI eutils metadata and article text mining
- [pdf2doi](https://github.com/MicheleCotrufo/pdf2doi) — extract and validate a DOI from a PDF you already have
- [S2AND](https://github.com/allenai/S2AND) — Semantic Scholar's author disambiguation algorithm and evaluation suite
- [pyalex](https://github.com/J535D165/pyalex) — OpenAlex client, with upstream-disambiguated author entities

Author disambiguation exists elsewhere only as a **standalone system** (S2AND,
ReCiter, `beard`) or as an upstream ID you consume (OpenAlex, Semantic Scholar).
Running it inside the harvester is what makes a single-person corpus trustworthy
enough to build a profile on.

**Bibliography checking.** Most tooling stops before comparing anything.
Formatters and linters ([bibtex-tidy](https://github.com/FlamingTempura/bibtex-tidy),
bibclean, [BibLaTeX-Check](https://github.com/Pezmc/BibLatex-Check),
[checkcites](https://github.com/islandoftex/checkcites)) and parsers
(pybtex, [bibtexparser](https://github.com/sciunto-org/python-bibtexparser))
never go online. Metadata syncers ([betterbib](https://github.com/texworld/betterbib),
[rebiber](https://github.com/yuchenlin/rebiber), doi2bib,
[bib-lookup](https://github.com/DeepPSP/bib_lookup)) fetch canonical records and
*overwrite* fields rather than report disagreement. JabRef's integrity check is
entirely local — it validates DOI syntax, and the "semantically wrong DOI" case
was left unimplemented when [issue #1445](https://github.com/JabRef/jabref/issues/1445)
was closed in 2016. The [Zotero DOI Manager](https://github.com/bwiernik/zotero-shortdoi)
plugin confirms a DOI is *registered*, but compares no fields and handles no PMIDs.

Closest prior art, both of which do compare against canonical metadata:

- [VeraCite](https://github.com/Shannon-Whitlock/VeraCite) — reports field-level mismatches against CrossRef, OpenAlex, arXiv and DataCite, and cross-compares multiple sources for the same DOI. It has no PubMed integration and does not use PMIDs.
- [evidentia](https://github.com/kgraph57/evidentia) — resolves each identifier in a text and compares the record against the *cited title, authors and year*, flagging "a fabricated identifier bolted onto a real title". Its check is identifier-vs-text, so it depends on the entry carrying accurate title metadata; the check here is identifier-vs-identifier and works even when the title is absent, wrong, or itself fabricated.
- [sciwrite-lint](https://github.com/authentic-research-partners/sciwrite-lint) — broad manuscript verification including retraction checks; flags conflicting identifiers *within* an entry.

---

## License

MIT. For research use — follow the terms of service and `robots.txt` of every
source you query.

---

¹ GPTZero analysis of 4,841 accepted NeurIPS 2025 papers, reported by
[Fortune, 2026-01-21](https://fortune.com/2026/01/21/neurips-ai-conferences-research-papers-hallucinations/);
failure-mode taxonomy in [arXiv:2602.05930](https://arxiv.org/abs/2602.05930).

² [ICML 2026 Program Chairs, "On Violations of LLM Review Policies", 2026-03-18](https://blog.icml.cc/2026/03/18/on-violations-of-llm-review-policies/).
