# Advisor Profile — Metric Specification

Status: specification, not yet implemented.
Applies to: a new `profile` subcommand and a new `pubmed_toolkit/advisor/` package.
Reuses: `analysis.render_gantt`, `pubmed_api.parse_article`, `pubmed_api._name_matches`,
`pubmed_api._affiliation_matches`, `pubmed_api._email_domain_matches`, `config.author_identity`.

---

## 1. Purpose and scope

The report answers one question: **what is it like to be this named researcher's graduate
student**, judged only from what PubMed indexes about their lab's publications.

It is not a literature search tool. It does not score, rank, or compare researchers.
Citation counts, h-index, journal impact factor, quartile, and CAS partition are out of
scope and must never appear in the output or in any intermediate file.

The output is a descriptive profile: counts with their denominators, a timeline, and a
fixed set of caveats. There is no total ordering of people anywhere in it.

### 1.1 The structural limit that governs everything below

PubMed contains only people who published. A student who joined this lab, struggled for
three years, and left without a paper is absent from every number in this report — from
both the numerator and the denominator. Every count here is a count of survivors, and the
size of the missing population is not recoverable from bibliographic metadata.

This is a property of the data source. No statistical treatment repairs it. It is
therefore stated as prose in Section 0 of the rendered report (CAV-00), not as a footnote.

---

## 2. Adjudication summary

Three independent proposals were synthesised. Where they conflicted, one was chosen:

| Conflict | Decision | Reason (one sentence) |
|---|---|---|
| Affiliation match as a cohort-membership criterion | **Rejected**; affiliation becomes a per-person reported attribute | Pre-2014 records carry only the first author's affiliation, so gating membership on it deletes real trainees for a metadata reason rather than a substantive one. |
| Span > 60 months reclassifies a person as senior | **Rejected**; no span cap of any kind | A cap encodes a "PhDs take ≤ N years" assumption and evicts exactly the longest-serving trainees, who are the people a prospective student most wants to see. |
| `is_corresponding` as a seniority criterion | **Rejected**; corroboration only, always printed with coverage | It is computed as `bool(email) or "corresponding" in affiliation` (`pubmed_api.py` L281) and therefore tracks journal formatting policy, not authorship. |
| Person-level lead-author **rate** | **Rejected**; replaced by a three-bucket partition of counts | The denominator is conditioned on having published at all, so any rate is optimistic by an unmeasurable amount and reads as "my personal odds". |
| Co-first **rate** (with or without a coverage gate) | **Rejected**; count plus position breakdown, never a rate | `EqualContrib` is publisher-deposited; a coverage threshold cannot separate "publisher omits the field" from "no co-first authorship", so it is false precision. |
| Papers-per-year trend, slope, or last-3-vs-prior comparison | **Rejected**; integer counts only | Five right-censored integer points do not support a comparison, and the comparison is precisely what gets misread as decline. |
| Span reported in months | **Rejected**; integer years, stated as ±1 year | `_date_iso` fabricates `month=1, day=1` when the month is absent, so month precision is manufactured. |
| Topic / direction stability | **Dropped entirely** | Not computable from parsed fields, and MeSH indexing lag would manufacture a drift signal at the recent end even after adding MeSH parsing. |
| Collaborating-institution breadth, and any internal/external ratio | **Dropped**; replaced by a verbatim affiliation-string listing | Affiliation strings are unnormalised free text with era-dependent coverage, and the ratio degrades into the prestige reading the product excludes. |
| Whether `equal_contrib` counts as "lead", reported both ways | **Rejected**; the lead slot is index 0, full stop | Reporting every lead figure twice doubles the surface area and invites cherry-picking; co-first authorship gets its own section instead. |
| Single-appearance people: named or aggregated | **Named on the timeline, excluded from every aggregate** | Author names are already public record, so the protection that matters is against inference-about-a-person, not against name disclosure. |
| Retmax truncation: annotate or refuse | **Refuse the whole report** | Every count is wrong by an unbounded amount on a truncated corpus, and a banner gets scrolled past. |

Kept by agreement across all three proposals: the mandatory provenance block, the hard
corpus gates, last-author position as the only structural seniority signal, integer counts
with printed denominators, the 1900-date exclusion, the removal of `render_gantt`'s
hardcoded personal names, the ban on composite scores, and the reuse of `render_gantt` as
the primary presentation of per-person activity.

---

## 3. Prerequisites (code changes required before any metric can be computed)

**P1 — Identity-verified corpus without position filtering.** `cli.cmd_fetch` keeps only
papers where `is_first_or_corresponding` returns True, and that function `continue`s past
any author position that yields no role (`pubmed_api.py` L474-480). Middle-author papers
never reach analysis. Measuring the PI's byline position on that corpus is circular.
The `profile` path must build its own corpus: verify identity, record the PI's index,
**filter on nothing else**.

**P2 — Thread per-author identity fields through `build_author_records`.**
`analysis.build_author_records` currently keeps only
`name/index/is_first/is_last/equal_contrib/is_corresponding/affiliation` and discards the
`orcid`, `last`, `fore`, and `initials` that `parse_article` already extracts. Person
keying (Section 6.3) is impossible without them. This is the single highest-value fix
available to this report.

**P3 — `render_gantt` exclusion set must be a parameter.** `analysis.py` L306 hardcodes
a set containing `pi_name`, the empty string and **six personal names left over
from one specific lab** (the names are not reproduced here — they are real people, and
this document is public). Reused unchanged, it silently deletes those six from every
other lab's timeline. New
signature: `render_gantt(author_records_path, output_dir, pi_name="", exclude_names=None)`,
defaulting to `{pi_name, ""}`. The plotting logic is correct and stays.

**P4 — Not required.** `_date_iso`'s 1900 fallback (`analysis.py` L196) is handled by a
report-side filter (Section 6.5). Changing the shared helper is a larger blast radius than
this report needs.

**P5 — Not required, but must be printed.** `is_first_or_corresponding` reads
`cfg.get("require_affiliation", True)` (L447) while both `config.DEFAULT_CONFIG` and
`pubmed_api.AUTHOR_IDENTITY` set it to `False`. A caller passing a partial identity dict
therefore gets strict mode; a caller going through `load_config` gets lenient mode. The
advisor path does not use this flag at all (it uses the evidence tiers of Section 6.1),
but the effective value must appear in the provenance block so the reader can see which
corpus they are looking at.

**Naming note.** The package is `pubmed_toolkit/advisor/`, not `pubmed_toolkit/profile/`.
`profile` is a standard-library module name; a submodule with that name is legal under
absolute imports but is a trap for anyone reading the import list.

---

## 4. Data contract

The report reads exactly one file, written by the `profile` fetch stage.

`<output_dir>/advisor_corpus_<YYYYmmdd_HHMMSS>.json`:

```json
{
  "schema_version": 1,
  "generated_at": "2026-07-22T20:47:11",
  "position_filtered": false,
  "query": {
    "term": "<verbatim esearch term from build_search_query>",
    "mindate": "2021/07/22",
    "maxdate": "2026/07/22",
    "years_back": 5,
    "retmax": 500,
    "esearch_count": 137,
    "pmids_returned": 137,
    "truncated": false
  },
  "identity": {
    "author_name": "...",
    "orcid": "...",
    "affiliation_keywords": ["..."],
    "email_domains": ["..."],
    "require_affiliation_effective": false
  },
  "counts": {
    "fetched": 137,
    "verified": 41,
    "name_only": 6,
    "rejected": 90,
    "by_evidence": {"orcid": 12, "email": 9, "affiliation": 20}
  },
  "fallback_fired": false,
  "papers": [
    { "...parse_article output...": null, "pi_index": 3, "pi_evidence": "orcid",
      "pi_ambiguous": false }
  ]
}
```

Rules:

- `papers` contains **only** `verified` papers (Section 6.1). `name_only` papers are
  counted, never stored, never analysed.
- `position_filtered` is `false` for corpora built by the `profile` path. A legacy
  `papers_*.json` produced by `cmd_fetch` has no such file; if the report is pointed at
  one, it must treat `position_filtered` as `true` (Section 7.7 suppression).
- The report must refuse to run from `papers_*.xlsx`. `build_author_records` falls back to
  `_split_author_names(authors_str)` when the JSON lacks a PMID, which forces
  `equal_contrib=False`, `is_corresponding=False`, `affiliation=""` for every author with
  no warning. That path converts "unknown" into a confident zero and is the most dangerous
  silent failure in the pipeline.

---

## 5. Gates

Gates are evaluated before any section renders. A fired gate produces a refusal document
containing the gate name, the observed values, and the fix — and nothing else. Exit code 1.

| Gate | Condition | Behaviour |
|---|---|---|
| **G1 truncation** | `query.esearch_count > query.pmids_returned` | Refuse the entire report. Message: `"esearch matched {count} records but only {returned} were retrieved. Every count in this report would be wrong by an unbounded amount. Raise retmax, reduce years_back, or add affiliation_keywords, then re-fetch."` |
| **G2 identity fallback** | `fallback_fired == true`, i.e. zero papers passed verification and the pipeline kept everything | Refuse the entire report. Message: `"No paper passed identity verification. The corpus is 'every paper by anyone sharing this name' and describes several different researchers. Configure orcid, affiliation_keywords, or email_domains and re-fetch."` |
| **G3 weak identity config** | `orcid` empty AND `affiliation_keywords` empty AND `email_domains` empty | Refuse the entire report. Message: `"No identity evidence is configured, so the corpus is a name match only. For any common surname this blends several people. Set at least one of orcid / affiliation_keywords / email_domains."` |
| **G4 no structured authors** | any paper in `papers` lacks a non-empty `authors` list of dicts | Refuse the entire report. Message: `"Corpus lacks structured author records. Run the profile fetch stage; the report cannot be built from the Excel export."` |
| **G5 empty corpus** | `len(papers) == 0` after the record exclusions of Section 6.5 | Refuse the entire report. Message: `"0 papers remain after exclusions. Nothing can be reported."` |

There is no "degrade with a warning" path for G1–G5. A warning gets scrolled past; a
missing report does not.

---

## 6. Classification rules

### 6.1 PI

For each fetched paper, iterate `paper["authors"]` in index order and collect every author
where `_name_matches(author, target_name.lower().split())` is True. For each such author
compute an evidence tier:

| Tier | Condition | Rank |
|---|---|---|
| `orcid` | `identity.orcid` non-empty and `author["orcid"].lower() == identity.orcid.lower()` | 3 |
| `email` | `_email_domain_matches(author["email"], identity.email_domains)` | 2 |
| `affiliation` | `_affiliation_matches(author["affiliation"], identity.affiliation_keywords)[0]` | 1 |
| `name_only` | name matched, none of the above | 0 |

- The PI is the name-matching author with the **highest tier**. Ties are broken by lowest
  index, and the paper is marked `pi_ambiguous: true`.
- Paper disposition: highest tier ≥ 1 → `verified`, stored, `pi_index` recorded.
  Highest tier == 0 → `name_only`, counted in the provenance block, **not stored**.
  No name match → `rejected`.
- Byline position is **never** part of this decision. That is the whole point of P1.

The `name_only` count is a sensitivity band: it is the maximum number of papers the report
could be missing because the PI's affiliation string was empty or their institution
variant was not configured. It appears in the provenance block with CAV-01.

### 6.2 Removals applied before anyone is classified

Applied in this order, per paper:

1. **CollectiveName entries.** An author entry with `last == "" and fore == "" and
   initials == "" and name != ""` is a consortium, not a person. Remove it from the author
   list for all person-level purposes. This must run **before** the last-author test, or a
   trailing consortium entry pushes a real trainee into the last slot and mislabels them
   as a senior collaborator.
2. **The PI**, at `pi_index`.
3. **Configured exclusions**, `config["advisor"]["exclude_names"]` (default `[]`), matched
   case-insensitively against `name`. This is the replacement for `render_gantt`'s
   hardcoded set (P3).
4. **Empty names.**

### 6.3 Person keys

Author entries are grouped into people by this deterministic procedure:

```
key_orcid(a)  = a["orcid"].strip()                        # when non-empty
key_strict(a) = (a["last"].lower(), a["fore"].lower())
key_loose(a)  = (a["last"].lower(), (a["fore"] or a["initials"])[:1].lower())
```

1. Every entry with a non-empty ORCID joins the group for that ORCID. ORCID groups are
   final and are never merged with each other.
2. Every entry without an ORCID joins the group for its `key_loose`.
3. A loose group merges into an ORCID group when that ORCID group contains at least one
   entry with the same `key_loose` **and** no other ORCID group shares that `key_loose`.
   If two ORCID groups share a `key_loose`, all involved groups stay separate and every
   one of them is flagged `collision_confirmed` — two different ORCIDs under one name
   string is the only positive collision test PubMed affords.
4. Within each non-ORCID loose group, collect the distinct `key_strict` values.
   Two forenames are *prefix-compatible* if one is empty, or one is a case-insensitive
   prefix of the other. If every pair is prefix-compatible the group is `drift_benign`;
   otherwise it is `collision_suspected` and every derived value for that person is
   rendered with a `[?]` marker.
5. An entry with `last` non-empty but both `fore` and `initials` empty forms its own group
   and is flagged `incomplete_name`. These are counted and reported, not silently merged.

**Ambiguity budget.** The provenance block prints `n_people` under strict keying and under
loose keying. Strict keying splits one person across name-format drift; loose keying merges
distinct people. The gap between the two numbers is the honest error bar on every
person-level count, and it is printed whether or not any collision was flagged.

Known unresolvable case: `Wang Wei` and `Wang Weiwei` are prefix-compatible and therefore
merge as `drift_benign`, even though they may be two people. This is stated in CAV-02 and
covered by test T24.

### 6.4 Strata

Every person (post-6.2, post-6.3) receives exactly one stratum. First match wins.

| Stratum | Rule | Used for |
|---|---|---|
| **D — senior collaborator** | Holds the last-author slot on ≥ 1 corpus paper (last index of the post-CollectiveName author list) | Counted and named; excluded from every trainee metric |
| **A — lead-trainee candidate** | Never last author; holds ≥ 1 first-author slot (index 0) | Span, time-to-lead, lead-holder partition, Gantt |
| **B — support candidate** | Never last author; no first-author slot; ≥ 2 appearances | Span, roster, Gantt; counted separately in the lead-holder partition |
| **C — single appearance** | Never last author; exactly 1 appearance | Named on the Gantt only; excluded from every median, ratio and partition |

Rules that follow from this:

- Last-author position is the only structural seniority signal in PubMed metadata, and
  first-author position is the only structural "did the work" signal. Everything else a
  reader might reach for — span, appearance count, affiliation — is a *consequence* the
  report measures, never a criterion, because using a consequence as a criterion bakes the
  conclusion into the definition.
- A single-author paper makes that author simultaneously first and last. If it is the PI
  the paper leaves E (Section 7.3) by construction. If it is anyone else, the last-author
  test puts them in stratum D. That is wrong for the rare sole-author trainee paper; the
  case must be logged by PMID rather than silently applied (T13).
- A person who takes a last-author slot partway through the window flips from A to D. The
  flip is **reported explicitly by name and year** — "people trained here go on to run
  their own groups" is the strongest positive datum this corpus can produce, and burying
  it inside a stratum reassignment wastes it (T27).
- The output must never use the bare word "student" about a named person. The permitted
  labels are exactly: `lead-trainee candidate`, `support candidate`, `single appearance`,
  `senior collaborator`. No field in PubMed separates a PhD student from a postdoc,
  technician, staff scientist, clinical fellow, rotation student, or visiting scholar.

### 6.5 Record-level exclusions

Applied to the corpus before any metric. Each exclusion is counted and its PMIDs listed in
the provenance block.

| Exclusion | Rule | Reason |
|---|---|---|
| Unparseable date | `_date_iso(pub_date)` starts with `"1900-"` | The 1900 fallback is not an early date; one such record gives a person a ~125-year span and destroys every median. |
| Correction / comment record | `re.match(r"(?i)^\s*(correction|corrigendum|erratum|author correction|publisher correction|retraction|retracted|comment on|reply to|response to|editorial)\b", title)` | `parse_article` extracts no `PublicationType`, so this title regex is the only available separator. It is a lower bound and is labelled as one. |
| Empty author list | `len(authors) == 0` | Nothing to classify. |
| Hyperauthorship | `len(authors_after_collectivename_removal) >= 50` | Consortium and multicentre papers are a structurally different kind of authorship. Excluded from **all** person-level analysis and from the team-size median; still counted in records-per-year and listed by PMID. |
| Duplicate PMID | exact | — |
| Duplicate DOI | identical non-empty lowercased `doi` | Same DOI is the same work by definition; keep the lowest PMID. |

Title-normalised duplicates (lowercase, strip non-alphanumerics) are **flagged and
counted, never merged** — a preprint and its journal version carry different DOIs, but so
do genuinely distinct papers with similar titles, and merging on a non-identifier is a
guess.

### 6.6 "External collaborator" — why there is no such stratum

The tool does not classify anyone as an external collaborator, because the classification
is not observable. `_author_record` space-joins every `AffiliationInfo` node into one
string (`pubmed_api.py` L275), so a dual-appointment author whose blob contains the home
institution reads as internal; affiliation coverage is era- and publisher-dependent; and
the strings are unnormalised free text in mixed languages.

Instead every person carries a descriptive attribute, computed over that person's
appearances only:

| `affiliation_signal` | Rule |
|---|---|
| `internal` | ≥ 1 appearance with a non-empty affiliation string matching any `identity.affiliation_keywords` via `_affiliation_matches` |
| `external` | ≥ 1 appearance with a non-empty affiliation string, none of which match |
| `unknown` | every appearance has an empty affiliation string |

`affiliation_signal` is displayed beside each person and is **never** used to assign a
stratum, gate a cohort, or compute a ratio. `unknown` is a first-class value, printed as
`unknown`, never folded into `external`.

---

## 7. Metrics

Global rendering rules, enforced everywhere:

- **R1** Every number prints its denominator inline: `7 of 23 papers`, never `30%` alone.
- **R2** A percentage may be rendered only when its denominator ≥ 20. For denominators
  5–19, counts with the denominator only. Below 5, the aggregate is suppressed and the
  underlying rows are printed instead.
- **R3** No percentage is ever computed for an individual person. `Person A: 33% first
  author` on three papers is noise dressed as precision.
- **R4** Every censoring boundary is annotated where it is displayed — the window start,
  the partial current year, the 18-month indexing lag — not in a footnote.
- **R5** People are sorted by first appearance date, then by name. Never by any count.
  Sorting by count builds a leaderboard, and a leaderboard is a ranking of people.
- **R6** No composite score, weighted index, letter grade, or star rating. If the report
  contains one number that summarises the person, it has failed.
- **R7** No trend line, fitted slope, year-over-year change, or growth rate anywhere.

Each metric below states: question, formula, denominator, minimum n, suppression
behaviour, and the caveat ID that must be printed with it.

### 7.1 S2 — Person roster and activity timeline

- **Question.** Who recurs in this lab's output, and when were they visible?
- **Formula.** One row per person from Section 6.3/6.4. Columns: name, stratum,
  `affiliation_signal`, `n_appearances`, `n_first_slots`, `n_equal_contrib_flagged`,
  `first_year`, `last_year`, `left_censored`, `right_censored`, collision flag.
  Sorted per R5. Rendered as a table **and** as the Gantt produced by
  `analysis.render_gantt` with `exclude_names` from config (P3).
- **Denominator.** `n_people`, printed under both strict and loose keying.
- **Minimum n.** None; this is the raw roster.
- **Suppression.** Per R3, no per-row percentage. Rows flagged `collision_suspected` or
  `collision_confirmed` carry `[?]` on every derived value.
- **Caveats.** CAV-02, CAV-03.

The Gantt is the primary presentation. Collapsing a timeline to a median deletes exactly
the truncation that made the picture safe to read.

### 7.2 S3a — First-author slot accounting (paper side)

- **Question.** On this lab's papers, who occupies the first-author slot?
- **Eligible set E.** Corpus papers surviving Section 6.5, minus papers whose slot-0 entry
  is a CollectiveName, minus papers where `pi_index == 0`.
- **Formula.** Label the slot-0 author of each paper in E with its stratum from Section
  6.4 and report counts for: `A`, `B`, `C`, `D`, `unclassified`. Counts sum to `|E|`.
- **Denominator.** `|E|`, always printed.
- **Minimum n.** `|E| ≥ 5` for aggregate counts; `|E| ≥ 20` before any percentage (R2);
  `|E| == 0` prints `not computable: the PI is first author on every corpus paper` and
  nothing else.
- **Suppression.** `|E| < 5` → print the paper-by-paper table instead of any aggregate.
- **Caveats.** CAV-04, CAV-05.

The word "share" is banned from this section's output. A share implies a well-defined
population of students; no such population is observable.

### 7.3 S3b — Lead-slot holders (person side)

- **Question.** Among the people visible in this lab's output, who has ever led a paper?
- **Formula.** Partition strata A + B (C and D excluded) into exactly three buckets:
  1. `holds ≥ 1 first-author slot` (stratum A by definition);
  2. `no first-author slot, first appearance ≥ lag_years before window end`;
  3. `no first-author slot, first appearance within the trailing lag_years` — too recent
     to tell.
  `lag_years` default 3, configurable. Print as `k of n`, never as a percentage, never as
  a rate, never described as odds.
- **Denominator.** `|A| + |B|`, printed.
- **Minimum n.** None for the partition (it is a count partition, not a ratio). A
  percentage is forbidden here regardless of n, because the denominator is conditioned on
  having published at all.
- **Suppression.** None; the three buckets are always printed, including zeros.
- **Caveats.** CAV-06.

Bucket 3 exists so that a lab which just expanded does not read as exploitative. Excluding
those people instead of bucketing them would change `n` silently.

### 7.4 S4 — Time from first appearance to first lead slot

- **Question.** How long before someone here has a paper with their name in front?
- **Formula.** For each person in stratum A:
  `lag_years(p) = first_lead_year(p) − first_appearance_year(p)`, integer, ≥ 0.
  Print the full distribution including the count at 0, plus the median.
  Adjacent and mandatory: the stratum-B count from bucket 2 of S3b, with each person's
  elapsed years — these are the censored "not yet" cases.
- **Denominator.** `|A|`, printed.
- **Minimum n.** Median requires `|A| ≥ 5`; below that print the raw per-person values
  and no median.
- **Suppression.** `|A| == 0` prints `no person in this corpus holds a first-author slot`.
- **Caveats.** CAV-07, CAV-08.

The distribution is heavily zero-inflated: many people debut as first author. Reporting
only a median hides that, which is why the count at 0 is mandatory.

### 7.5 S5 — Observed activity span

- **Question.** Between a person's first and last appearance, how much time passes?
- **Formula.** Per person in strata A + B:
  `span_years = last_year − first_year`, integer.
  Censoring flags: `left_censored` when `first_year <= window_start_year`;
  `right_censored` when `last_year >= current_year − 1`.
  Partition into `complete` (neither flag), `left_censored`, `right_censored`,
  `both_censored`, and report each count. Median and IQR over the `complete` bucket only.
- **Denominator.** `|complete|`, printed beside the median. `|A| + |B|` printed as the
  cohort size. Stratum C is reported as its own count and is never given a span.
- **Minimum n.** Median and IQR require `|complete| ≥ 5`; below that print the raw values
  and no median. Never a mean, at any n.
- **Suppression.** Two appearances in the same year give `span_years = 0`; printed as
  `0 (same year)`, never conflated with a single appearance.
- **Caveats.** CAV-09, CAV-10, CAV-11.

At `years_back = 5` every long-tenured person is structurally censored, so the `complete`
subset is biased toward short stays. That is stated in CAV-10, not implied.

### 7.6 S6 — Roster size and turnover per year

- **Question.** How many people are around, and is the group growing or emptying?
- **Formula.** For each year y in `[window_start_year, current_year]`:
  `active(y)` = distinct people (strata A+B+C+D, post-exclusions) with ≥ 1 appearance
  dated y; `arrivals(y)` = those whose earliest appearance is y; `departures(y)` = those
  whose latest appearance is y. Years with zero papers print `0`, never omitted.
  `departures` for the final two years are marked `right-censored — not departures`.
- **Denominator.** None; these are counts.
- **Minimum n.** None. Per R7, no derived figure of any kind is computed from this series.
- **Suppression.** None.
- **Caveats.** CAV-12.

### 7.7 S7 — PI byline position

- **Question.** Does the PI take the senior slot and let someone else lead, or are they
  still leading papers themselves?
- **Precondition.** `corpus.position_filtered == false`. If it is `true` or the field is
  absent, the whole section is replaced by CAV-13 and no counts are printed. This is
  non-negotiable: on a role-filtered corpus the filter *is* the metric.
- **Formula.** Over corpus papers, classify `pi_index` after CollectiveName removal:
  `first` (index 0), `last` (final index), `sole` (only author), `middle` (otherwise).
  Report the four counts summing to N. Separately and clearly labelled as a heuristic:
  how often the PI's own entry carries `is_corresponding`, printed **beside** the
  corpus-wide email coverage rate (fraction of papers where any author carries an email).
- **Denominator.** N = corpus size, printed. Percentages need N ≥ 20 (R2).
- **Minimum n.** N ≥ 5 for the counts; below that print the per-paper table.
- **Suppression.** As above, plus: the corresponding-author figure is suppressed entirely
  when email coverage is 0, because it is then False for everyone for reasons that have
  nothing to do with the PI.
- **Caveats.** CAV-14, CAV-15.

### 7.8 S8 — Co-first authorship flag occurrences

- **Question.** Does this lab's PubMed record ever mark shared authorship, and where?
- **Formula.** `A` = corpus papers with ≥ 1 author carrying `equal_contrib == True`.
  Report `|A| of N papers` plus the PMID list. Within A, break down by position: does the
  flagged group include index 0 (shared **first**), the final index (shared **senior**),
  or neither. Report the size of each flagged group.
- **Denominator.** N = corpus size.
- **Minimum n.** None — but a rate is forbidden at every n.
- **Suppression.** `|A| == 0` prints exactly `not measurable in this corpus`, never `0%`
  and never `no co-first authorship`.
- **Caveats.** CAV-16.

The position breakdown also fixes a real display bug: `analysis._author_role_label` renders
`cF` for `equal_contrib` regardless of position, so a shared *senior* authorship currently
displays as co-first.

### 7.9 S9 — PubMed records per calendar year

- **Question.** Is the lab still producing, or coasting on older output?
- **Formula.** Integer count of corpus records per `pub_year` across
  `[window_start_year, current_year]`. The first and last bins are labelled `PARTIAL` at
  the point of display. The most recent 18 months are labelled
  `subject to PubMed indexing lag` at the point of display.
- **Denominator.** None; counts.
- **Minimum n.** None.
- **Suppression.** G1 already refuses the report on truncation, so no additional gate.
- **Caveats.** CAV-17, CAV-18.

The section header must say **records**, not **papers** or **research articles**:
`PublicationType` is not parsed, so reviews, letters and case reports are indistinguishable
from primary research beyond the title-regex exclusion of Section 6.5.

### 7.10 S10 — Team size per record

- **Question.** How many co-authors will I share a byline with?
- **Formula.** `n_authors` per record after CollectiveName removal. Report median, IQR,
  min–max, and N. Report the count of records with ≥ 20 authors separately (records with
  ≥ 50 are already excluded by Section 6.5 and are listed there). Additionally, the same
  median over the subset of records whose slot-0 author is in stratum A or B.
- **Denominator.** N = corpus size for the main figure; `|E_AB|` for the subset.
- **Minimum n.** Main median requires N ≥ 5; the subset median requires `|E_AB| ≥ 10`.
- **Suppression.** Below those thresholds, print raw values, no median. Never a mean.
- **Caveats.** CAV-19.

### 7.11 S11 — Venue repetition

- **Question.** Where does this lab's work land, and does it have a home journal?
- **Formula.** Exact-string frequency of `paper["journal"]`. Print every journal with
  count ≥ 2 verbatim, plus `k journals appear once`.
- **Denominator.** N = corpus size.
- **Minimum n.** None.
- **Suppression.** None.
- **Caveats.** CAV-20.
- **Hard prohibition.** No impact factor, quartile, tier, or CAS partition is joined in,
  computed, stored, or displayed — not even if a table were available locally. This is the
  DORA line and the report does not cross it.

### 7.12 S12 — Affiliation strings, verbatim

- **Question.** Which institutions appear on this lab's bylines?
- **Formula.** Every distinct affiliation string appearing on ≥ 3 corpus papers, printed
  verbatim and ungrouped, with its paper count. Beside it, per year, the affiliation
  coverage rate: `author entries with a non-empty affiliation / all author entries`.
- **Denominator.** Per-year author-entry counts, printed.
- **Minimum n.** Strings on < 3 papers are not listed.
- **Suppression.** If coverage for a year is 0, print `no affiliation data` for that year
  rather than an empty list.
- **Caveats.** CAV-21.

No count of "distinct institutions" is emitted. `Fujian Medical University`,
`Fujian Med Univ`, and `The First Affiliated Hospital of Fujian Medical University` are
three strings for one organisation; counting them measures string variance. A human
resolves those entities instantly, so the report supplies the strings and stops.

### 7.13 S13 — Titles grouped by year

- **Question.** What has this lab actually worked on?
- **Formula.** Print every corpus record's title, grouped by `pub_year`, ascending, with
  PMID. No clustering, no bucketing, no keyword extraction, no similarity measure.
- **Denominator.** N = corpus size.
- **Minimum n.** None.
- **Suppression.** None.
- **Caveats.** CAV-22.

This is deliberately a non-metric. It replaces the dropped topic-stability metric
(Section 9) and hands the judgement to the reader.

---

## 8. Caveat strings (verbatim)

These are the exact strings to render. They belong in
`pubmed_toolkit/advisor/caveats.py` as module constants and must not be paraphrased at the
call site. English only; translation is out of scope for this spec.

| ID | Text |
|---|---|
| CAV-00 | `This report describes publication metadata, and nothing else. PubMed contains only people who published: anyone who joined this lab and left without a paper is absent from every number below, from both the numerator and the denominator. The size of that missing group cannot be recovered from this data. The report cannot see advising style, funding, working hours, whether anyone graduated, lab culture, or what happened to people who left — which are the things you actually want to know. Do not let the numbers that are here stand in for the ones that are not.` |
| CAV-01 | `{n} further papers matched the name but carried no verifiable identity evidence and were excluded. That is the upper bound on how much this corpus is missing for identity reasons. A PI who changed institution inside the window loses their earlier papers this way unless every institution variant is configured.` |
| CAV-02 | `People are identified by name string. Romanised names collide heavily, and the tool has ORCID and affiliation keywords for the PI only — co-authors have nothing equivalent. Two people with one name merge into one row with an inflated count and an over-long span; one person recorded two ways splits into two short rows. Strict keying finds {n_strict} people, loose keying finds {n_loose}; the gap is the error bar on every count in this section.` |
| CAV-03 | `Position labels are inferences from the byline, not facts about a person. A PhD student, postdoc, technician, staff scientist, clinical fellow, rotation student and visiting scholar all produce the same positional shape, and no field in PubMed separates them.` |
| CAV-04 | `This counts slots on papers, not people. A high trainee-led count can come from three prolific people in a twenty-person lab. It describes the shape of the lab's output, not your personal odds.` |
| CAV-05 | `Papers where a trainee elsewhere led and this PI was a middle author are in this corpus, but papers where this PI is absent entirely are not — so this says nothing about the PI's behaviour outside their own lab.` |
| CAV-06 | `Counted only over people who published at least once. Anyone who joined and left without a paper is in neither bucket. This is not a rate and must not be read as your chance of leading a paper here.` |
| CAV-07 | `Measured on publication dates, which trail the work by roughly one to two years including review. A median of three years does not mean you publish in year three.` |
| CAV-08 | `Computed only over people who reached a first-author slot. The people still without one are printed beside it for exactly this reason — read both numbers or neither.` |
| CAV-09 | `This is the interval between two publication dates, not time in the lab. The period before someone's first paper — typically the first two to three years of a PhD — is invisible by construction, and a paper can appear a year or more after the person has left.` |
| CAV-10 | `The median covers only people whose whole span fits inside the search window, which biases it toward short stays: at years_back={years_back} anyone long-tenured is censored at one end or both. A growing lab looks like it churns people; a lab whose students all left years ago shows clean, complete, long spans.` |
| CAV-11 | `A short span supports "fast and efficient" and "left after a year" equally well. Nothing in this data distinguishes them.` |
| CAV-12 | `Author count is not headcount. This counts people whose papers happened to come out that year, so a lab that just doubled shows no change for two years and a lab that emptied last year still looks full. Co-authors are not lab members and PubMed offers no way to separate them.` |
| CAV-13 | `Not measured. This corpus was built with a first/last/corresponding-author filter, so the PI's byline position is decided by the filter rather than by the data. Re-fetch with the profile path, which verifies identity without filtering on position.` |
| CAV-14 | `Last-author-equals-senior-author is a biomedical convention, not a rule. In many clinical departments the division head is last on everything regardless of involvement — which is precisely the case this count exists to detect and precisely the case it cannot detect.` |
| CAV-15 | `Corresponding-author status is inferred from an email address appearing in the affiliation string; PubMed has no corresponding-author field. It tracks journal formatting policy and changes over time. Email coverage in this corpus: {covered} of {total} papers.` |
| CAV-16 | `PubMed carries the equal-contribution attribute only when the publisher supplies it. Absence is not evidence of absence: journals that mark co-first authorship with a footnote and deposit nothing produce a zero here. No rate is computed from this field for that reason.` |
| CAV-17 | `The first and last bins are partial: the window starts mid-year, and the most recent 18 months are undercounted by PubMed indexing lag and by ahead-of-print records with no issue date yet. Every lab looks like it is winding down at the right-hand edge.` |
| CAV-18 | `These are PubMed records, not research papers. Publication type is not parsed, so reviews, letters, comments and case reports are counted alongside primary research except where a title made the record identifiable as a correction.` |
| CAV-19 | `A small team supports "you get attention" and "there is nobody here to learn from" equally. A large one supports "generous inclusion" and "your contribution disappears into position 14". The count cannot choose between them.` |
| CAV-20 | `Journal names are printed as recorded and are not normalised, so one journal can appear twice under its full title and its abbreviation. No impact factor, quartile or tier is shown, computed or stored. Concentration in one venue supports "deep specialisation" and "a reliable low-bar outlet" equally.` |
| CAV-21 | `These are affiliation strings, not institutions. They are unnormalised free text and are not counted or grouped. Coverage is strongly time-biased: older PubMed records often carry only the first author's affiliation, so years are not comparable to each other. An author with joint appointments has all of them joined into one string, so a shared home institution hides the external one.` |
| CAV-22 | `Titles are printed verbatim and ungrouped. No topic classification is offered: research direction cannot be measured honestly from the fields this toolkit parses, and stability would be as easy to read as "a mined-out vein" as "deep expertise".` |

---

## 9. Report section order

Rendered to `<output_dir>/advisor_profile_<timestamp>.md`, plus the Gantt PNG.
Title wording is fixed: `Observed publication pattern — <author_name>`. Never "profile
score", "assessment", "rating", or "evaluation".

| # | Section | Contents |
|---|---|---|
| 0 | What this report is and is not | CAV-00 verbatim. Nothing else. Always first. |
| 1 | Corpus provenance | Verbatim esearch term; mindate/maxdate/years_back; retmax, esearch count, PMIDs returned, truncation flag; fetched / verified / name_only / rejected, and verified broken out by evidence tier; effective `require_affiliation`; every Section 6.5 exclusion with its count and PMIDs; title-duplicate flag count; strict vs loose person counts; the fallback flag. CAV-01, CAV-02. |
| 2 | People and activity timeline | S2 roster table + `render_gantt` PNG. CAV-02, CAV-03. |
| 3 | First-author slots | S3a paper-side counts, then S3b person-side partition. CAV-04, CAV-05, CAV-06. |
| 4 | Time to a first-author slot | S4. CAV-07, CAV-08. |
| 5 | Observed activity span | S5, plus the stratum A→D flip list. CAV-09, CAV-10, CAV-11. |
| 6 | Group size and turnover | S6. CAV-12. |
| 7 | The PI's own byline position | S7 or CAV-13. CAV-14, CAV-15. |
| 8 | Shared-authorship flags | S8. CAV-16. |
| 9 | Records per year | S9. CAV-17, CAV-18. |
| 10 | Team size | S10. CAV-19. |
| 11 | Venues | S11. CAV-20. |
| 12 | Affiliation strings | S12. CAV-21. |
| 13 | Titles by year | S13. CAV-22. |
| 14 | What was deliberately not computed | Section 10 of this spec, rendered verbatim. |

Section 0 precedes provenance because the limits reframe every number that follows; the
provenance block determines whether those numbers render at all, and its gates fire before
any section is built.

---

## 10. Dropped metrics register (rendered as report Section 14)

| Dropped | Reason |
|---|---|
| Research direction stability / topic drift | `parse_article` extracts no MeSH and no keywords. Adding MeSH would not fix it: MeSH indexing lags publication by months, so the newest year is systematically under-indexed and the pipeline would manufacture a drift signal that is pure artifact. Title-word overlap measures house style. Replaced by Section 13, titles by year. |
| `render_topic_charts` | Reads an externally produced `_topic_extraction.json` that this toolkit never writes, and its `BUCKET_NAMES` are one specific lab's subject areas. Out of scope for the profile report. |
| Count of collaborating institutions | Affiliation strings are unnormalised; counting them measures string variance, not collaboration. It is also a prestige proxy, which is the ranking use-case this product excludes. Replaced by Section 12. |
| External-affiliation dependency ratio | Same denominator problem plus era-dependent coverage, and joint appointments are space-joined into one string so external ties disappear. Any trend in it is a metadata trend that reads as a scientific one. |
| Lead-author conversion **rate** | The denominator is conditioned on having published, so the rate is optimistic by an unmeasurable amount and is read as personal odds. Replaced by the three-bucket partition in Section 3. |
| Co-first authorship **rate** | `EqualContrib` is publisher-deposited with unknown, journal-dependent missingness. Replaced by a count and a position breakdown in Section 8. |
| Mean first-author papers per trainee | A ratio of two undercounted quantities, dominated by the single most productive person, that reads as a productivity score for a named individual. |
| Corresponding-author rate as a headline | An email-presence proxy. Reported only beside its own coverage rate, never alone. |
| Citation counts, h-index, citations per paper, field-normalised impact | `efetch` returns none of it, and citation ranking is out of scope. |
| Journal Impact Factor, quartile, tier, CAS partition | Journal-level proxies for individual paper quality. Prohibited even if a table were available locally. |
| Any composite score, weighted index, grade, or star rating | Encodes weights the data cannot justify and recreates the people-ranking this tool excludes. |
| Graduation rate, time to degree, attrition, "students who left" | The denominator — everyone who joined — is structurally unobservable. Stated as prose in CAV-00, never approximated with a number. |
| Authorship "fairness" or "credit generosity" scores | Require knowing contribution, which is in no field at any level. |
| Trends, fitted slopes, year-over-year percentage change | Five right-censored integer points do not support a slope. 3 papers to 5 is not "+67%". |
| Any distinction between PhD student, master's student, postdoc, staff scientist, technician, clinical fellow, visiting scholar | No field supports it. |
| Span-based seniority reclassification | A span cap encodes an assumption about degree length and evicts the longest-serving trainees, who are the most informative people in the corpus. |
| Affiliation-gated cohort membership | Pre-2014 records carry only the first author's affiliation, so the gate deletes real trainees for a data-coverage reason. |

---

## 11. Test cases

Plain scripts printing `[PASS]`/`[FAIL]`, exiting non-zero on failure, run as
`python tests/test_advisor_*.py`. Fully offline, synthetic fixtures only. No pytest.
Fictional names and institutions only; if an ORCID is needed use `0000-0002-1825-0097`
(ORCID's own published example identifier), matching `tests/test_identity_filter.py`.

### 11.1 Gates and provenance (`tests/test_advisor_gates.py`)

| ID | Input situation | Expected output |
|---|---|---|
| T01 | `esearch_count=900`, `pmids_returned=500` | G1 fires; refusal document only; exit 1; no section rendered |
| T02 | `fallback_fired=true`, 40 papers all role `待确认` | G2 fires; refusal only; exit 1 |
| T03 | identity has empty orcid, empty affiliation_keywords, empty email_domains | G3 fires; refusal only; exit 1 |
| T04 | one paper's `authors` is `[]` at load time / absent key | G4 fires; refusal only; exit 1 |
| T05 | corpus of 3 papers, all three excluded by Section 6.5 | G5 fires; refusal only; exit 1 |
| T06 | clean corpus, 25 verified, 6 name_only | no gate fires; provenance prints `verified=25`, `name_only=6`, evidence-tier breakdown summing to 25; CAV-01 rendered with `{n}=6` |
| T07 | corpus JSON lacks the `position_filtered` key | treated as `true`; Section 7 replaced by CAV-13; all other sections render |
| T08 | report pointed at a `papers_*.xlsx` path | G4 refusal; the Excel path is never read |

### 11.2 PI resolution (`tests/test_advisor_corpus.py`)

| ID | Input situation | Expected output |
|---|---|---|
| T09 | PI at index 3 of 7, ORCID matches | paper `verified`, `pi_index=3`, `pi_evidence="orcid"`, retained (this is the paper `cmd_fetch` would have dropped) |
| T10 | PI name matches, affiliation empty, no ORCID, no email | paper classified `name_only`, excluded from `papers`, counted in provenance |
| T11 | two authors both match the PI name, one at tier `affiliation`, one at tier `orcid` | ORCID author wins regardless of index; `pi_ambiguous=false` |
| T12 | two authors both match the PI name at the same tier | lowest index chosen; `pi_ambiguous=true`; paper listed in provenance |
| T13 | single-author paper, author is not the PI | author lands in stratum D by the last-author rule; PMID logged in a `sole-author paper` list, not silently applied |
| T14 | single-author paper, author is the PI | paper leaves E; `pi_position="sole"` in Section 7 |
| T15 | trailing author entry is a CollectiveName; real person at index n−2 | CollectiveName removed first; the person at n−2 becomes last author and is stratum D — assert the consortium is not classified as a person |
| T16 | CollectiveName at index 0 | paper excluded from E; counted separately; not counted as a person holding a lead slot |

### 11.3 Record exclusions (`tests/test_advisor_corpus.py`)

| ID | Input situation | Expected output |
|---|---|---|
| T17 | `pub_date` is `""` so `_date_iso` yields `1900-01-01` | record excluded, counted, PMID listed; no person receives a ~125-year span |
| T18 | title `"Correction to: Hepatic stellate cell activation"` | record excluded by the title regex, counted, listed |
| T19 | title `"Corrective surgery outcomes in ..."` | **not** excluded — the regex is word-anchored and must not fire on `Corrective` |
| T20 | paper with 62 authors | excluded from person-level analysis, team-size median, and E; still counted in records-per-year; PMID listed |
| T21 | paper with 22 authors | retained everywhere; counted in the `≥ 20 authors` line of Section 10 |
| T22 | two records, same non-empty DOI, different PMIDs | deduped to the lower PMID; count reported |
| T23 | two records, different DOIs, identical normalised titles | both retained; flagged and counted; not merged |

### 11.4 Person keys (`tests/test_advisor_people.py`)

| ID | Input situation | Expected output |
|---|---|---|
| T24 | `Wang Wei` and `Wang Weiwei`, no ORCIDs | merged as `drift_benign` (prefix-compatible); documented false-merge; assert CAV-02 is rendered |
| T25 | `Wang Wei` and `Wang Wenjie`, no ORCIDs | one loose group, flagged `collision_suspected`; every derived value carries `[?]` |
| T26 | `Zhang Wei` and `Zhang W` on different papers | merged as `drift_benign` into one person with 2 appearances |
| T27 | `Zhang` with empty fore and empty initials | own group, flagged `incomplete_name`, counted in provenance, not merged into any `Zhang X` |
| T28 | two authors, same name string, two different ORCIDs | two separate people; both flagged `collision_confirmed`; no merge |
| T29 | same person, ORCID on one paper, absent on the other, no other `key_loose` clash | loose group merges into the ORCID group; one person, 2 appearances |
| T30 | ORCID absent on one entry; two ORCID groups share that `key_loose` | no merge; all three groups flagged `collision_confirmed` |
| T31 | 12 people under loose keying, 15 under strict | provenance prints both; ambiguity budget rendered even with zero collision flags |

### 11.5 Strata (`tests/test_advisor_people.py`)

| ID | Input situation | Expected output |
|---|---|---|
| T32 | person is last author on 1 of 4 papers | stratum D; excluded from S3b, S4, S5 |
| T33 | person never last, first author on 2 papers | stratum A |
| T34 | person never last, never first, 3 appearances | stratum B |
| T35 | person never last, 1 appearance | stratum C; named on the Gantt; absent from every median, ratio and partition |
| T36 | co-PI who is never last author (PI always is), 6 appearances, no lead slot | stratum B — assert the tool does **not** relabel them senior by span or by count, and that CAV-03 accompanies the table |
| T37 | person is first author in 2021-2022, last author in 2025 | stratum D, and the A→D flip is reported by name and year in Section 5 |
| T38 | name appears in `config.advisor.exclude_names` | absent from the roster, the Gantt, and every metric |
| T39 | `render_gantt` called with default `exclude_names` | only the PI name and `""` are excluded — assert none of the six previously hardcoded personal names appear in the exclusion set |

### 11.6 Metrics (`tests/test_advisor_metrics.py`)

| ID | Input situation | Expected output |
|---|---|---|
| T40 | `|E| = 23`, 9 slot-0 authors in stratum A | percentage permitted (≥ 20); rendered as `9 of 23 (39%)`; the word "share" absent from the output |
| T41 | `|E| = 12` | counts with denominator only; no percentage anywhere in the section |
| T42 | `|E| = 3` | aggregate suppressed; paper-by-paper table printed |
| T43 | PI is first author on all 14 papers, so `|E| = 0` | `not computable: the PI is first author on every corpus paper`; no zeros emitted |
| T44 | 4 people in A, 3 in B with ≥ 3 years observed, 2 in B first seen 1 year ago | three buckets printed as `4 / 3 / 2 of 9`; no percentage at any n; CAV-06 present |
| T45 | 6 people in A, lags `[0,0,0,1,2,4]` | median printed with `|A|=6`; the count at lag 0 printed explicitly as 3 |
| T46 | 3 people in A | raw lag values printed; no median |
| T47 | spans: 4 complete, 5 right-censored | no median (complete n=4 < 5); raw values printed; censoring counts printed |
| T48 | spans: 6 complete | median and IQR printed with `n=6`; assert no mean appears anywhere in the output |
| T49 | person with 2 papers in the same year | `span 0 (same year)`; distinct from a stratum-C row |
| T50 | person's `first_year == window_start_year` | `left_censored=true`; excluded from the complete bucket |
| T51 | person's `last_year == current_year` | `right_censored=true`; excluded from the complete bucket |
| T52 | year 2023 has zero corpus records | Section 9 prints `2023: 0`, not an omitted row |
| T53 | window starts mid-2021; report run in 2026 | 2021 and 2026 bins labelled `PARTIAL`; CAV-17 rendered |
| T54 | corpus has zero `equal_contrib` flags | `not measurable in this corpus`; assert `0%` and `no co-first` never appear |
| T55a | one paper flags `equal_contrib` on authors at index 0 and 1 | counted as shared **first**, group size 2 |
| T55b | one paper flags `equal_contrib` on the final two indices only | counted as shared **senior**, not as co-first (the bug `_author_role_label` currently has) |
| T56 | no author in the corpus carries an email | S7's corresponding-author figure suppressed; CAV-15 prints `0 of N` coverage |
| T57 | journal recorded as `J Hepatol` on 2 papers and `Journal of Hepatology` on 3 | two separate rows, verbatim; no normalisation; CAV-20 present |
| T58 | affiliation strings: 4 papers carry one variant, 2 carry another | only the 4-paper string listed (≥ 3 threshold); per-year coverage rate printed beside it |
| T59 | a year where every author entry has an empty affiliation | `no affiliation data` for that year; not rendered as coverage 0% with an empty list |
| T60 | any corpus | assert the rendered markdown contains no `h-index`, `impact factor`, `citation`, `score`, `grade`, `rank`, or `%` on a per-person row (R3, R6, and the DORA prohibition, asserted as a text scan of the output) |
| T61 | roster of 9 people with paper counts `[5,1,3,...]` | rows ordered by first appearance date then name; assert the ordering is not by count (R5) |
| T62 | any corpus | assert Section 0 is CAV-00 verbatim and appears before the provenance block |

---

## 12. Implementation layout

```
pubmed_toolkit/advisor/__init__.py     # public API: build_corpus, render_report
pubmed_toolkit/advisor/corpus.py       # PI resolution, gates, record exclusions, corpus I/O
pubmed_toolkit/advisor/people.py       # person keys, strata, affiliation_signal
pubmed_toolkit/advisor/metrics.py      # S3a..S13, pure functions over the corpus dict
pubmed_toolkit/advisor/caveats.py      # the CAV-* strings, module constants
pubmed_toolkit/advisor/report.py       # section ordering, suppression logic, markdown out
tests/test_advisor_gates.py
tests/test_advisor_corpus.py
tests/test_advisor_people.py
tests/test_advisor_metrics.py
```

CLI: `pubmed-toolkit profile --author "..." [--config ...] [--from-corpus PATH]`.
Without `--from-corpus` it fetches and writes `advisor_corpus_<ts>.json`, then renders.
With it, it renders only — the report must be reproducible offline from the corpus file.

New config block, merged by `config._deep_merge` like the existing `author_identity`:

```json
"advisor": {
  "exclude_names": [],
  "lag_years": 3
}
```

Style: comments explain why, never what; every non-obvious decision carries a short reason;
type hints on all signatures; Python 3.10+; ruff clean at line-length 110 with `E,F,W,I,UP,B`.
Metric functions in `metrics.py` take plain dicts and return plain dicts — no file I/O, no
matplotlib import — so every test case above runs offline against synthetic fixtures.
