# Advisor Profile — Visual Specification

Status: specification, not yet implemented.
Governs: the visual layer of the `profile` subcommand — the replacement for
`analysis.render_gantt`'s PNG, and a self-contained HTML rendering of the report.
Subordinate to: `docs/profile-metrics-spec.md`. Where the two disagree, the metrics spec
wins except at the points amended in Section 10 of this document.

Adjudicated from two independent visual designs. Every conflict resolution is recorded in
Section 1 with its reason. Nothing here invents a metric, a floor, or a denominator.

---

## 1. Adjudication summary

Two designs were submitted. Where they agreed, the agreement is adopted without comment.
Where they conflicted, one was chosen:

| Conflict | Decision | Reason |
|---|---|---|
| Server-side SVG vs client-side rendering from embedded JSON | **Python-emitted inline SVG** | The suppression floors exist once, in Python; a JS renderer is a second implementation of `MIN_N_AGGREGATE` that will eventually drift and render a suppressed median as a number. |
| matplotlib SVG export vs hand-emitted SVG | **Hand-emitted** | `cli._render_timeline` already has to catch `ImportError` for matplotlib (cli.py:391); hand-emitted SVG removes that degradation path entirely, is testable by string assertion under the repo's offline plain-script convention, and gives a per-mark `<title>` hook matplotlib does not. |
| A chart for the S3b lead-slot partition (stacked bar) vs text only | **No chart** | A part-to-whole encoding pre-computes the proportion in ink; the metrics spec dropped "lead-author conversion rate" precisely because that proportion is read as personal odds (CAV-06). More decisively, **C-LAG already renders all three buckets** as dots — a second figure would be a redundant, worse rendering of the same three groups. |
| Time-to-lead: integer histogram vs Wilkinson dot strip | **Dot strip** | Bars of height 1–2 read as a distribution; one dot per person is countable, carries a name for Ctrl+F, and matches the page's other figures. |
| `still_without_lead` at no x position vs at `years_observed` with a censoring tail | **At `years_observed`, right-censored tail** | A right-censored observation has a lower bound, not "no value"; `years_observed` is already in `lead_slot_partition.buckets`, so the honest glyph costs nothing. |
| Span: censoring count bar + complete-only dot strip vs four censored lanes | **Four lanes** | Lanes make censoring the primary structure (the other design's stated goal) while keeping every censored person visible as a dot instead of collapsing them into a count. |
| Team size: histogram with trainee-led overlay vs two dot lanes | **Two lanes** | The two cuts carry different floors (5 and 10) and `team_size.subset` has **no `iqr` key**, so an overlay would imply a comparability the metric cannot supply. |
| A records-and-people-per-year panel (charting S6 roster turnover) | **Records only; S6 is never charted** | `roster_turnover` is computed over **all** people (report.py:253 passes the full roster), so an "active people" row would plot 277 people against a 77-person chart — the original bug in a new costume. CAV-12 independently forbids reading it as headcount. |
| Records per year: bars vs unit columns | **Unit columns**, one square per record | 5 vs 6 becomes one visible square rather than a length difference the eye extends into a slope (R7). |
| Page order: decision-first (the three "about me" figures first, gantt fourth) vs `report.py` section order 0–14 | **`report.py` order, 0–14** | Two renderings of one report must not have two emphases; the caveat-to-section pairing is defined by that order, and a TOC with anchors gives the fast reader the same path without forking the document. |
| Progressive-enhancement JS name filter vs zero JS + Ctrl+F | **Zero JS** | The rolls render complete in the DOM, so find-in-page already solves "is this person in the lab"; a filter introduces a hidden-row state that print and Save-as-PDF capture wrong. |
| Gantt: one figure vs per-cohort-year chunks | **One figure, one shared x axis** | First-appearance ordering produces a diagonal arrival cascade that is the informative property of the R5 sort; chunking restarts the axis and deletes it, and two people in different chunks stop being comparable. |
| Gantt row label: with or without appearance count | **With `n=` count** | Marks are per *year*, not per record, so counting marks gives the wrong number; the label is the only place the true count exists. R5 forbids sorting by a count, not printing one. |
| Gantt: per-appearance marks offset within the year cell vs one mark per year | **One mark per year** | Per-year appearance counts do not exist in `people` (`years` is a `sorted(set(...))`), and recovering them is a third plumbing change; the count lives in the row label instead. |
| Gantt: equal-contribution glyph | **Dropped entirely** | The existing flag is position-blind (analysis.py:333 renders shared *senior* authorship as "co-first" at analysis.py:366); making it position-aware needs a second plumbing change, and CAV-16 says the field's missingness is publisher-dependent, so a per-mark glyph manufactures a visual rate. |
| Per-figure text equivalent: always visible vs collapsed | **Split** — the count summary is always visible in the `<figcaption>`; the per-row data table collapses | Satisfies the drift objection (the numbers are in the DOM beside the SVG) and the length objection (77 rows do not sit open). |

Adopted by agreement, no adjudication needed: cohort A+B as the only row filter; deletion
of the `-len(appearances)` productivity tie-break; integer-year x axes everywhere; stratum
C named but not plotted; stratum D in a separate collapsed panel; no sort controls
anywhere; caveats never collapsed; colour never a sole channel; `@media print` expands
every disclosure; a refused report renders the gate and nothing else.

Caught by one design and kept: the on-chart declaration of excluded-group counts so a
screenshot carries its own selection rule; the ≥50-author truncation annotation on the
team-size axis; the demand that the metrics spec be *amended* rather than silently
diverged from; the per-year count strip for single-appearance people; the `<summary>`
self-describing count as a print fallback; the `not_computable` case keeping its bottom
strip.

---

## 2. The one additive plumbing change

Everything in this document is built from metric shapes that exist today, except three
fields. No new metric function, no new floor, no change to any existing value.

**`roles.build_people`** — add one key to each person dict:

```python
"lead_years": sorted({entry["year"] for entry in first_slots}),
```

`first_slots` is already in scope (roles.py:493).

**`metrics.person_roster`** — copy three fields into each row dict:

```python
"years": list(person["years"]),
"lead_years": list(person["lead_years"]),
"first_date": person["first_date"],
```

`years` and `first_date` already exist on `people`; only `lead_years` is new.
`first_date` is carried so a test can assert the row order without reaching back into
`people`, and so the row is self-describing.

This is additive only — no existing key changes name, type or value — so `SCHEMA_VERSION`
stays at 1 and `tests/test_profile.py` must pass unchanged. Record the added fields in
`CHANGELOG.md`.

Not added, and why: `first_slot_pmids` (one mark covers a whole year, so a per-mark PMID is
not well defined); per-year appearance counts (a third change, and the row label carries the
total); per-year equal-contribution position (see the adjudication above).

---

## 3. Rendering decision: Python-emitted inline SVG

**Decision: every figure is an SVG string generated in Python and written literally into
the HTML. The page contains exactly one `<script>` element, of type
`application/json`, and nothing on the page is drawn by it.**

Reasons, in order of weight:

1. **Suppression is a rendering decision that already lives in Python.** `suppressed`,
   `not_computable`, `MIN_N_AGGREGATE`, `MIN_N_SUBSET_MEDIAN` decide whether a median tick
   is drawn or replaced by a plate. A JS renderer reimplements those floors; a drifted
   second implementation is exactly how a 4-person median eventually ships as a number.
2. **A blank chart is the worst failure available to a disclosure document.** The page must
   open from `file://`, survive being re-saved and mailed, survive a headless Save-as-PDF,
   and survive a strict extension policy. A JS-drawn figure is empty in all four.
3. **SVG `<text>` is real text.** Ctrl+F finds a person's name inside the figure and screen
   readers read it. That is the name-lookup feature and the accessibility path, for free,
   with no filter widget.
4. **Determinism.** Same corpus, byte-identical SVG. Two runs diff cleanly; client-side
   layout depends on browser font metrics.
5. **No build step, no CDN, no vendored library.** A JS chart library must be inlined,
   which is either a build step or a 200 KB paste.

Cost, accepted: markup size. A 77-row timeline is roughly 900–1200 SVG elements at
~100–160 KB — cheaper than the 193 KB JSON the report already writes, and unlike the PNG it
is text, so it diffs and gzips.

Hand-emitted, not matplotlib: matplotlib is an optional extra the CLI already degrades
around (cli.py:391), it path-outlines text unless `svg.fonttype` is forced, and it offers
no hook for per-mark `<title>` or `aria`. Dropping it from the profile path means the
`profile` command stops having a degraded mode.

Implementation layout (files stay under ~800 lines):

```
pubmed_toolkit/profile/svg.py      # primitives: escape, rect, line, text, mark, axis. No domain knowledge.
pubmed_toolkit/profile/charts.py   # the four figures. Pure: metric dict in, figure dict out.
pubmed_toolkit/profile/html.py     # page assembly, sections, disclosures, CSS.
tests/test_profile_charts.py       # plain script, [PASS]/[FAIL], offline, synthetic fixtures.
tests/test_profile_html.py         # structural assertions over the emitted page.
```

Each function in `charts.py` returns:

```python
{"svg": str, "caption": str, "desc": str, "rows": list[dict], "drawn": bool}
```

`caption` is the visible `<figcaption>` text, `desc` the in-SVG `<desc>`, `rows` the
collapsed data table, `drawn` False when a degenerate state replaced the figure with prose.

---

## 4. The gantt fix

### 4.1 Row-inclusion rule

**Exactly the A+B cohort: every person who never held the senior slot and appears at
least twice. One row each. No other row is drawn in the main figure.**

- Rows come from `metrics.person_roster.rows` filtered to `stratum in ("A", "B")` — never
  from `_authors_parsed.json`. The current `render_gantt` groups by raw name string while
  the report groups by ORCID plus loose keying with collision flags, so the two person
  models can disagree, and `stratum` — the thing that selects rows — does not exist in the
  file the chart currently reads.
- This is the population every aggregate in the report is already computed over:
  `lead_slot_partition` and `activity_span` both call `_strata(people, "AB")`. The chart and
  the numbers finally describe the same people. That identity is the whole point of the fix
  and is asserted in Section 11.
- The PI is never a row (`build_people` already skips `pi_person_index`, roles.py:462).
- Names in `advisor.exclude_names` are never rows, and are printed verbatim in provenance.
- People visible only through a ≥50-author record are absent from `people` entirely; that
  absence is stated on the chart face, not left implicit.

### 4.2 Expected row count

`n_rows == s2.by_stratum["A"] + s2.by_stratum["B"] == s5.cohort_denominator`.

On the measured Stockwell corpus that is **77 rows out of 277 people**. Both other counts
are read at render time from `s2.by_stratum`, never hardcoded:
`s2.by_stratum["C"]` single-appearance people (named, not plotted) and
`s2.by_stratum["D"]` senior collaborators (separate collapsed panel).

Note the edge case, because it changes the split: a person with exactly one appearance who
holds the last-author slot on that paper is **stratum D, not C** — `_stratum` tests
last-author first (roles.py:411). "Appears exactly once" and "stratum C" are therefore not
the same set, and the prompt's 190 is the former. The plotted 77 and the total 277 are
unaffected either way. All chart text must say "single appearance" (the report's own
`STRATUM_LABEL["C"]`) and take the number from `s2.by_stratum["C"]`.

### 4.3 Ordering

`(first_date, name)` — byte-identical to `build_people`'s own sort (roles.py:524), so the
timeline row order and the Section 2 roster table row order agree line for line. Fixed in
Python. There is no client-side re-sort and no sort control anywhere on the page.

The current secondary key `-len(appearances[n])` (analysis.py:338) is **deleted outright**.
It ranks people by productivity within a shared first-appearance date, which is a shipping
violation of R5 and a separate bug from the aspect ratio.

Beyond compliance, first-appearance order is also the most useful order for the actual
question: it produces a diagonal arrival cascade in which a reader sees at a glance whether
arrivals continue to the right edge or stop.

### 4.4 What happens to everyone else

Nobody is deleted; the venue changes.

1. **Stratum C — the single-appearance roll.** A dense multi-column text block inside
   Section 2, under `<summary>N people appear once and hold no senior slot (named, not
   plotted)</summary>`. Each entry `Name[?] — <year> — <affiliation_signal>`, grouped under
   year headings, ordered `(first_year, name)` per R5. Every field is already in `s2.rows`.
2. **Stratum C — the per-year count strip.** A one-line strip in the timeline's own axis
   footer, aligned to the same year columns: counts only, no rows, no names, no ranking, so
   the reader can see whether the one-offs cluster in particular years. Derived from
   `s2.rows` where `stratum == "C"` grouped by `first_year` (for stratum C,
   `first_year == last_year`). This is the structural mitigation for the sharpest objection
   to the row filter — that dropping the one-offs makes the lab look more stable than the
   record shows.
3. **Stratum D — the senior-collaborator panel.** A second SVG with the identical row
   encoding and the same year axis, collapsed, titled "Senior collaborators — not your peer
   group". It exists because the A→D flips (`provenance.flips`) live there and are the
   strongest positive datum the corpus can produce. The **flips list itself stays open** in
   Section 5, never collapsed.
4. **Counts on the chart face.** The plotted count, the single-appearance count, the
   senior-collaborator count, the strict/loose keying gap and the hyperauthorship record
   count all appear in the timeline's own subtitle — not only in the surrounding prose. A
   chart whose selection rule lives outside it gets screenshotted and forwarded without it.

### 4.5 Geometry

Row pitch **24 px**, chrome (title, subtitle, axis, legend, C-strip) **≤ 140 px**.

`height = 24 * n_rows + chrome`. At 77 rows: **≤ 1988 px**, against the measured 21506 px —
a **10.8× reduction**. Width fixed at 1100 px content, `overflow-x: auto` on the container.

There is no height cap and no row truncation: dropping rows to fit a page is the original
bug. At larger cohorts the figure is taller and the acceptance check is the formula, not a
constant.

### 4.6 Why this is a bug fix and not a preference

Four defects, not one:

1. It draws 277 rows because it plots every name string, contradicting the spec that
   excludes single-appearance people from every aggregate. 190 of those rows carry exactly
   one dot and no interval — information the roster table already states in one cell — and
   the 77 people who carry information are buried among them.
2. analysis.py:338 sorts ties by appearance count. A productivity leaderboard inside a chart
   whose spec says people are never ordered by any count.
3. It groups by exact `name` string because `build_author_records` discards `orcid`, `last`,
   `fore` and `initials` (analysis.py:216–250; spec P2). So the PNG's row count and Section
   2's `n_people` are two different person counts in one report, with no way to tell which
   is authoritative.
4. It plots on a date axis with `MonthLocator(bymonth=[1,7])` (analysis.py:358) over dates
   from `_date_iso`, which fabricates `month=1, day=1` when the month is absent
   (analysis.py:197–205) — so the existing PNG shows fake January clusters. This is the same
   manufactured precision the metrics spec rejected when it refused to report spans in
   months.

Cohort membership is the only defensible row filter available: it is not a productivity cut
(a ranking) and not a span cap (rejected at metrics spec L41 for evicting the
longest-serving trainees); it is the structural definition the metrics already use.

### 4.7 Disposition of `analysis.render_gantt`

The `profile` command stops calling `_render_timeline` and stops producing
`student_activity_gantt.png`. `render_gantt` stays for the `analyze` command, with two
surgical corrections that need no new data and are user-facing there too:

- delete the `-len(appearances[n])` secondary sort key (analysis.py:338) — R5;
- relabel the `equal_contrib` legend entry (analysis.py:366) from "co-first" to a
  position-neutral wording, because the flag is position-blind (analysis.py:333) and a
  shared *senior* authorship currently renders as co-first.

`build_report(gantt_path=...)` keeps its signature for compatibility; `cmd_profile` stops
passing it, and Section 2 of the Markdown points at the `.html` for the timeline.

---

## 5. Charts

Four figures. Every other section is text or a table, by decision, not by omission —
Section 6 lists what was refused and why.

Universal rules for all four:

- Integer axes only. No sub-year x ticks anywhere (`_date_iso` fabricates the month).
- No colour ramp, no threshold band, no "good" region, no red/green. Any shading that
  separates better from worse is a grade.
- Colour is never the only channel: fill-vs-hollow, arrowhead direction and hatch carry
  every distinction that matters, so all four survive greyscale and print.
- Every figure carries a visible `<figcaption>` containing at least one `k of N`.
- No `%` character appears in any figure, caption or `<desc>` at any n.
- Every figure carries its caveats verbatim from `caveats.CAVEATS`, in a
  `<blockquote class="caveat">` directly beneath it, never collapsed, never a tooltip.
  The HTML builder reads them from the report-level `report["caveats"]` map, not from the
  owning section's list — CAV-09 is needed at Section 2 but first registered at Section 5.

### C-GANTT — Person activity timeline (Section 2)

- **Decision question.** Who recurs in this lab, when were they visible, and did any of them
  get their name in front of a paper?
- **Source.** `metrics.s2.rows` filtered to stratum A+B, using `name`, `marker`, `stratum`,
  `affiliation_signal`, `n_appearances`, `n_first_slots`, `first_year`, `last_year`,
  `left_censored`, `right_censored`, `flags`, plus the added `years`, `lead_years`,
  `first_date`. Legend counts from `metrics.s5.buckets`. Absent-people note from
  `provenance.exclusions["hyperauthorship"]`. Strata counts from `s2.by_stratum`.
- **Encoding.**
  - x = calendar year, one column per year across `[window_start_year, window_end_year]`.
  - y = person, ordered `(first_date, name)`.
  - **Filled square** in each year present in `lead_years` (a year containing at least one
    lead-slot record). **Hollow square** in each year in `years` not in `lead_years`.
    One mark per year; the legend states "a mark means one or more records in that year".
  - A **1 px grey connector** from `first_year` to `last_year`, deliberately weaker than the
    marks, with the legend line "line = interval between first and last record, not presence
    in the lab".
  - **Censoring:** `left_censored` draws an open left arrowhead at the window edge with a
    dashed tail into the margin; `right_censored` the mirror; both draw both. This is the
    survival-plot convention and replaces the current bounded segment, which asserts a start
    and an end the data does not have.
  - The trailing two years sit under a shaded band labelled "PubMed indexing lag", driven off
    `s9.years[*].indexing_lag`, never a hardcoded year.
  - Row label: `Name[?] — n=3 records — <STRATUM_LABEL[stratum]>`. The count is printed
    because marks are per-year; it never enters the sort.
  - Subtitle, on the chart face: plotted count, single-appearance count, senior-collaborator
    count, strict/loose gap, and "k records with ≥50 authors left person-level analysis;
    anyone visible only through them is not on this chart (PMIDs in provenance)".
  - Axis footer: the stratum-C per-year count strip (Section 4.4.2).
- **Empty state.** `n_rows == 0` → no figure. Print "no person in this corpus appears more
  than once and holds no senior slot", plus the single-appearance roll. Never an empty axis
  with tick labels.
- **Suppressed state.** None — the roster has no floor and no aggregate. If the added
  `years`/`lead_years` fields are missing from `s2.rows`, draw connectors only and title the
  figure "spans only — per-appearance detail unavailable". Never draw a connector as if it
  were a mark.
- **Caveats.** `CAV-02`, `CAV-03`, **`CAV-09`**. CAV-09 is repeated here from Section 5
  because the connector encodes elapsed publication interval, and this figure is where a
  reader forms the tenure belief CAV-09 exists to deny.
- **How it misleads.** (a) A long row reads as "stayed a long time and was valued", but it is
  the interval between two publication dates: pre-first-paper years are invisible and a paper
  can appear after the person left. Mitigated by the connector's visual weakness, the legend
  wording, and CAV-09 under the figure. (b) A person present in 2019 and 2024 only gets a
  five-year connector implying continuous presence; the two hollow squares are the truth and
  the line is the lie — which is why it is a hairline. (c) Rows with more marks read as better
  people: mitigated by constant mark size, no count in the sort, no count-derived colour.
  (d) The right edge makes everyone look departed: mitigated by the dashed censoring tails and
  the shaded lag band; strip them and this becomes the most misreadable object in the report.
  (e) It cannot show anyone who joined and never published — that is CAV-00, and it is why
  CAV-00 is Section 0 and sits above this figure on the page.

### C-LAG — Time to a first-author slot (Section 4)

- **Decision question.** How long before someone here fronts a paper — and how many never did?
- **Source.** `metrics.s4` (`values[{name, marker, lag_years}]`, `count_at_zero`, `median`,
  `denominator`, `suppressed`, `not_computable`, `still_without_lead`) and
  `metrics.s3b.buckets.too_recent` (`name`, `years_observed`) with `s3b.lag_years`.
- **Encoding.** Two strips on one shared integer x axis, inseparable.
  - x = integer years between first record and first lead record. The axis title says exactly
    that, never "years to first paper".
  - **Top strip:** one solid dot per stratum-A person at their `lag_years`, stacked vertically
    within the integer bin so the count is countable rather than area-estimated. The lag-0 bin
    is annotated in place: "debuted in the lead slot: k of |A|" — the distribution is
    zero-inflated and a median alone deletes that fact.
  - **Bottom strip:** one hollow dot with a right-pointing tail per person in
    `still_without_lead`, at their `years_observed`. The tail means "at least this long, still
    none" — the correct right-censored glyph. This strip is not optional, not collapsible, and
    never separable from the axis.
  - **`too_recent`:** grey dots inside a shaded zone spanning `x < s3b.lag_years`, labelled
    "too recent to tell". These dots sit at small x by construction and will be read as fast
    leads if not zoned; the zone is load-bearing, not decoration.
  - A vertical bracket rule spans both strips, so a screenshot that crops the bottom strip is
    visibly cut.
  - Median: one thin tick labelled "median N years over |A| people". One tick. No box, no
    whisker.
  - Chart-face denominators: `|A|`, the observed-without-lead count, the too-recent count, the
    A+B cohort size, and "N single-appearance people are in neither strip".
- **Empty state.** `not_computable` (`|A| == 0`) → the top strip is replaced by the report's
  own sentence, verbatim: `no person in this corpus holds a first-author slot`. **The bottom
  strip still renders**, because "nobody led" and "k people have gone N years without leading"
  are different facts and the second survives.
- **Suppressed state.** `s4.suppressed` (`|A| < 5`) → the median tick is not drawn and is
  replaced, at the position it would have occupied, by a plate reading "median not computed —
  n=4, floor 5". **The dots stay**: below the floor the raw values *are* the metric.
- **Caveats.** `CAV-06`, `CAV-07`, `CAV-08`. CAV-06 travels here from Section 3 because this
  figure renders the S3b partition.
- **How it misleads.** The top strip alone reads as "I will lead a paper in about a year" —
  the exact misreading CAV-08 exists to prevent, which is why the bottom strip shares the
  axis. The lag is measured between two publication dates, so it omits the two-to-three
  pre-publication years (CAV-07) — hence the axis names records, not time in the lab. Everyone
  who left without ever leading and appeared once is stratum C and is in neither strip; that is
  stated on the chart face, because a distribution whose absentees are invisible is a
  survivorship plot.
- **Note.** This figure renders all three `lead_slot_partition` buckets: stratum A as the top
  strip, `observed_without_lead` as the bottom strip, `too_recent` as the zoned dots. Those
  three groups are exactly the A+B cohort, and `holds_lead` is exactly stratum A
  (metrics.py:187). That is why S3b gets no separate figure, and why the dot counts must sum
  to `s3b.denominator` (Section 11, item 20).

### C-SPAN — Observed activity span (Section 5)

- **Decision question.** Between someone's first and last record here, how much time passes —
  and how much of that is even observable?
- **Source.** `metrics.s5` (`values[{name, marker, span_years, first_year, last_year, bucket,
  same_year}]`, `complete_values`, `median`, `iqr`, `suppressed`, `buckets`,
  `cohort_denominator`, `denominator`, `single_appearance_count`).
- **Encoding.** Four horizontal lanes on one integer `span_years` axis, one lane per censoring
  bucket, each labelled with its own count ("complete 12", "right-censored 33", …).
  - One dot per person. Complete-lane dots are solid and terminal.
  - Left / right / both lanes draw the dot with a directional tail meaning "at least this
    long". The tail is the whole point: a right-censored span is not a short stay.
  - `same_year` dots sit at x=0 with a distinct glyph labelled "two or more records in one
    calendar year", never sharing a glyph with the visual idea of a single record.
  - The median + IQR bracket is drawn **only over the complete lane and is horizontally
    confined to it**. The physical restriction is the encoding that stops the median being
    read as the cohort's. Label: "median 3 years, IQR 2–5, over 12 of 77 people — complete
    spans only".
  - Chart-face denominators: cohort size, all four bucket counts, and "N single-appearance
    people have no span by construction".
  - All dots one colour, no ordering within a lane other than by span. Nothing may encode
    short-versus-long as better-versus-worse.
- **Empty state.** `cohort_denominator == 0` → prose plus the stratum-C count. Never a
  zero-height axis.
- **Suppressed state.** `s5.suppressed` (complete < 5) → no bracket at all; a plate reading
  "median not computed — 4 complete spans, floor 5" occupies the complete lane. Every dot in
  every lane still renders, so the figure never degrades to an empty frame.
- **Caveats.** `CAV-09`, `CAV-10`, `CAV-11`.
- **How it misleads.** "Median 3 years" will be read as "people stay 3 years", wrong twice: it
  is a publication interval, not tenure (CAV-09), and it is computed only over people whose
  whole span fits inside the window, which biases it short (CAV-10) — a 30-year lab with
  6-year trainees shows a *short* median assembled from the few stays that happened to fit,
  while a lab that emptied out five years ago shows long, clean, complete spans. The layout,
  not the prose, is the mitigation: "median 2.0 years" is physically unreadable without
  "43 of 77 censored" beside it, and the bracket cannot escape its lane. CAV-11 is why there
  is no colour ramp: a short span supports "fast and efficient" and "left after a year"
  equally.

### C-YEAR — Records per year (Section 9)

- **Decision question.** Is the lab still producing, or coasting on older output?
- **Source.** `metrics.s9` (`years[{year, count, partial, indexing_lag}]`, `denominator`).
- **Encoding.** Unit columns: one small square per record, stacked in its year's column.
  - x = every year in `[window_start_year, window_end_year]`, **including zero-count years** —
    an omitted row reads as "no data", a visible empty column reads as "zero", and they are
    different.
  - `partial` bins get a diagonal hatch and a "PARTIAL" label under the tick. `indexing_lag`
    bins sit inside a shaded band labelled "PubMed indexing lag — undercounted". Both are
    driven off the flags, never off a hardcoded year, and both are at the point of display per
    R4.
  - No connecting line, no fitted anything, no year-over-year label, no smoothing, no area
    fill (R7).
  - Axis title reads "PubMed records", never "papers" or "research articles"; the legend notes
    that reviews, letters and case reports are included (CAV-18).
  - Panel title is a flat noun phrase — "Records per year" — never anything containing a
    direction word.
  - Chart-face denominator: "N records, YYYY–YYYY, window `mindate` to `maxdate`".
- **Empty state.** No floor exists for this metric and none is invented. Zero-count years
  render as an empty labelled column with a `0` tick. One narrow guard, derived from flags
  rather than a magic number: **if every bin carries `partial` or `indexing_lag`, print the
  counts as a text line instead of drawing** — a figure where all of the ink is annotated as
  wrong is not a figure. A truncated corpus never reaches here; gate G1 refuses the report
  first.
- **Suppressed state.** `s9.suppressed` is False by construction. Nothing to suppress.
- **Caveats.** `CAV-17`, `CAV-18`.
- **How it misleads.** This is the most dangerous figure in the set and it is included only
  because omitting it is worse — the reader will otherwise eyeball raw PubMed with no caveat
  at all. The eye fits a trend across a left-to-right integer series whether or not one is
  drawn, and the right edge always dips, so every lab reads as winding down (CAV-17).
  Mitigations are structural: unit squares instead of bars, no connecting line, sparse
  gridlines so there is nothing to read a slope against, hatched and shaded end bins from the
  flags, and a direction-free title. Strip the hatching and this figure is indefensible.
  Second, unfixable at the chart: "records" is not "research output" — publication type is not
  parsed, so a year padded with three commentaries looks identical to a year with three primary
  papers. The axis title and legend carry that; nothing else can.

### C-TEAM — Team size (Section 10)

- **Decision question.** Will I be one of twenty names on a paper, or one of four?
- **Source.** `metrics.s10` (`values`, `median`, `iqr`, `min`, `max`, `large_team_count`,
  `large_team_pmids`, `denominator`, `suppressed`, `subset{denominator, values, median,
  suppressed}`) plus `provenance.exclusions["hyperauthorship"]`.
- **Encoding.** Two lanes on one integer author-count axis, same dot vocabulary as C-LAG and
  C-SPAN so the page has one visual grammar.
  - **Main lane:** one dot per record, stacked in integer bins. Records with ≥20 authors stay
    in the same lane but are outlined, and the axis carries "records with 20+ authors: k of N"
    — the metrics spec wants them reported separately, not used as a cut-off, so they get an
    annotation rather than a bin of their own.
  - **Right-edge annotation, mandatory:** "records with ≥50 authors are excluded from this
    chart (k of them; PMIDs in provenance)". `apply_record_exclusions` moves every ≥50-author
    record into `records_only` (roles.py:277), so `kept` — and therefore this figure's `max` —
    is capped below 50 by construction. Without this line the figure literally cannot show the
    consortium papers that are exactly the "one of twenty" fear it was drawn to answer, and it
    actively understates its own subject. This is a provenance-derived sentence, not a CAV
    string; it must not be styled as a caveat.
  - **Subset lane**, thinner, below: the records led by a stratum-A or -B person, its own dots,
    its own n. Two lanes make the two different floors visible (main 5, subset 10), which is
    otherwise the least intuitive suppression rule in the report.
  - Median tick + IQR bracket above the main lane, labelled "median N over M records".
    **The subset lane gets a median tick only and never an IQR band** — `team_size.subset`
    carries no `iqr` key, and inventing one would be a computed statistic this spec is not
    entitled to add.
  - No bin is coloured as good or bad; no shading, no ideal region.
- **Empty state.** `denominator == 0` is unreachable (G5 refuses first). Nothing else.
- **Suppressed state.** `s10.suppressed` (N < 5) → no bracket; a plate "median not computed —
  n=4, floor 5"; the dots stay. `s10.subset.suppressed` (< 10) → the lane **still draws its
  dots** and prints "median not computed — 7 records led by a lead-trainee or support
  candidate, floor 10". The lane is never omitted and never collapsed to zero height: an absent
  lane reads as "no trainee-led papers", a different and much worse claim than "too few to
  summarise".
- **Caveats.** `CAV-19`.
- **How it misleads.** CAV-19 is the symmetric failure and nothing may take a side: the same
  count supports "you get attention" and "there is nobody here to learn from", "generous
  inclusion" and "your contribution disappears into position 14". The sharper failure is
  structural and in no caveat — the ≥50 exclusion clips the right tail, so the visible maximum
  is a truncation artifact rather than the real maximum byline. Third, team size on this PI's
  papers is not lab headcount (CAV-12): co-authors include people who were never in the lab,
  and PubMed offers no way to separate them.

---

## 6. Refused figures

Refused on principle. Each stays as text or a table in its existing section.

| Refused | Reason |
|---|---|
| Any figure for S3b, the lead-slot partition | A part-to-whole encoding pre-computes the proportion in ink; the denominator is conditioned on having published at all (CAV-06). C-LAG already renders all three buckets on an axis that adds information instead. |
| Pie, donut, 100% stacked bar, icon array / unit dot matrix of the cohort | All four are rate encodings. The icon array is worse than the others: the idiom was invented to communicate individual risk ("2 in 10 people like you"), which is precisely the personal-odds reading spec 7.3 exists to block. The same three counts printed as "k of n" are fine. |
| S3a first-author slots by stratum as its own bar chart | Five bars add nothing over five printed numbers with denominators, duplicate C-LAG's message at the paper level, and invite the "trainee-led share" reading the spec bans the word "share" to prevent. One text line under Section 3. |
| S6 roster turnover (active / arrivals / departures per year) | `roster_turnover` is computed over all 277 people, so charting it beside a 77-person figure recreates the population mismatch this whole document exists to fix. CAV-12 says author count is not headcount, and the departures column is right-censored nonsense for the last two years. Arrival information already survives as the gantt's diagonal cascade. Stays a table. |
| S8 equal-contribution counts | The denominator is "papers where the publisher happened to deposit the field" (CAV-16), so bars manufacture a rate visually even when the axis says count. |
| S11 venue frequency | The moment a reader recognises the journal names a frequency chart becomes a prestige ranking — the DORA line spec 7.11 refuses to cross. Table only, verbatim. |
| S12 affiliation strings, and any coverage-over-time line | Unnormalised free text; plotting implies they are categories and measures string variance. A coverage line reads as "collaboration over time" when it is metadata coverage. |
| S13 word cloud, keyword chart, topic×year heatmap | Spec 7.13 and CAV-22 forbid keyword extraction outright; a cloud additionally sizes words by frequency, which is a ranking; the dropped `render_topic_charts` buckets are one specific lab's subject areas. |
| Any line, sparkline, area, cumulative curve, trend line, LOESS, fitted slope | R7. A cumulative curve is monotone by construction so it always reads as growth or plateau; the right two bins of any yearly series are censored, so a fit is dominated by an indexing artifact. |
| Violin, KDE, density curve, box plot for lag / span / team size | Smoothing 6 integers manufactures a shape the sample cannot support. A box hides n, asserts a continuous distribution, and has no way to show censoring — a right-censored span inside a box becomes an ordinary short observation, which is the exact lie this report exists to avoid. |
| Horizontal bar chart of people sorted by bar length ("top contributors") | A leaderboard, and a leaderboard is a ranking of people. R5. |
| Radar / spider chart across metric dimensions | The enclosed area is a composite score with arbitrary weights. R6 bans it by name. |
| Gauge, bullet chart, speedometer, traffic light, letter-grade badge | Literally a grade dial. R6. |
| Co-authorship network graph with node size or centrality | Node size ranks people and centrality implies importance; every edge means only "appeared on the same byline", which is not a relationship. |
| Treemap or waffle of venues | Area encodes weight, and a weighted venue display is one lookup away from the impact-factor read. |
| A stat-tile / KPI / "at a glance" row in the header | Denominators must be visible (R1), but big numbers in boxes are the visual grammar of a scorecard and read as a grade even when every individual number is innocent. Rendered as prose plus a definition list. |
| Embedding the existing PNG via `<img>` | Reimports the 1934×21506 problem into a page built to fix it. |
| A "show all people" toggle that adds the stratum-C rows to the gantt | A toggle with a 21506 px drop, and the plotted population would stop matching the population every aggregate is computed over — which is the original bug. |

Refused interactions:

| Refused | Reason |
|---|---|
| Sortable table columns | The single most important rejection on the page. One click on `appearances` or `lead slots` turns the roster into a productivity leaderboard. No sort control ships at any column; headers are plain `<th>`. |
| Filter by stratum or by year | It lets a reader delete the single-appearance people and look at a cleaner, more flattering lab. The strata are already separated into labelled panels, which is disclosure rather than removal. |
| A JS name-filter over the rolls | Same objection in miniature, plus a hidden-row state that print and Save-as-PDF capture wrong. Ctrl+F over real SVG and DOM text does the job with no state. |
| "Highlight this person across all charts" / brushing / linked highlighting | Converts a descriptive profile into a person-comparison tool, and manufactures exactly the cross-metric inference the report refuses — select the long spans, see their team sizes, conclude something causal about six people. |
| Zoom / pan on the timeline | A mouse dependency and a viewport state the printed page cannot reproduce; the axis is ~11 integer columns and already fits. |
| Multi-lab comparison mode | To be useful it needs a common scale across PIs, and a common scale across PIs is a ranking. Three labs means three files open side by side. |
| Client-side rendering from the embedded JSON | Section 3. |
| Dark-mode toggle, animated counters, transitions, progress rings | Stylesheet forks and state, zero contribution to the decision, and dark mode puts the hatch and tail contrast budget at risk. |

---

## 7. HTML structure

One self-contained `.html`, written beside the `.md` and `.json` by `write_report`.
No build step, no CDN, no network, opens from `file://`.

### 7.1 Page flow

1. `<header>`: fixed title `Observed publication pattern — <name>`, the generated timestamp,
   a skip-to-content link. No hero number, no stat row, no badge.
2. `<nav>`: table of contents, 15 entries, anchor links. Sticky on wide viewports, static in
   print.
3. Sections **0–14, in `report.py`'s exact order and with its exact titles**, so the HTML is
   not a friendlier second document with different emphasis:

   | § | Title | Figure | Caveats (never collapsed) |
   |---|---|---|---|
   | 0 | What this report is and is not | — | CAV-00, first content on the page |
   | 1 | Corpus provenance | — | CAV-01, CAV-02 |
   | 2 | People and activity timeline | **C-GANTT** | CAV-02, CAV-03, CAV-09 |
   | 3 | First-author slots | — (text) | CAV-04, CAV-05, CAV-06 |
   | 4 | Time to a first-author slot | **C-LAG** | CAV-06, CAV-07, CAV-08 |
   | 5 | Observed activity span | **C-SPAN** | CAV-09, CAV-10, CAV-11 |
   | 6 | Group size and turnover | — (table) | CAV-12 |
   | 7 | The PI's own byline position | — | CAV-13 (conditional), CAV-14, CAV-15 |
   | 8 | Shared-authorship flags | — | CAV-16 |
   | 9 | Records per year | **C-YEAR** | CAV-17, CAV-18 |
   | 10 | Team size | **C-TEAM** | CAV-19 |
   | 11 | Venues | — (table) | CAV-20 |
   | 12 | Affiliation strings | — (table) | CAV-21 |
   | 13 | Titles by year | — | CAV-22 |
   | 14 | What was deliberately not computed | — | — |

4. `<script type="application/json" id="report-data">` carrying `json_record(report)`, for
   copy-out and provenance only, labelled in the surrounding markup as **not** the render
   source.

Layout: prose column ~78ch; figures full-width to 1100 px. Each figure is
`<figure>` → `<svg>` → `<figcaption>` (denominators, floors, suppression state) →
`<blockquote class="caveat">` per caveat → `<details>` data table.

**If `report["refused"]` is True the page renders the gate id, name, message and observed
values and nothing else** — no charts, no partial sections, no header stats. This mirrors
`render_markdown`'s refusal branch exactly.

### 7.2 Collapsed by default

- Section 1 exclusion PMID lists (the one-line counts stay visible; only the PMID strings
  collapse).
- Section 2 roster table, all `s2.denominator` rows.
- Section 2 single-appearance roll.
- Section 2 senior-collaborator (stratum D) panel.
- Per-figure "Data table for this figure (N rows)" blocks.
- Section 13 titles by year — the largest block on the page and a reading exercise, not a
  scanning one.
- Section 14, the dropped-metrics register.

Every `<summary>` is self-describing and carries its own count — "Full roster table — 277
rows", "190 people appear once (named, not plotted)" — so a reader who never expands it
still learns the true magnitude, and a print engine that fails to expand it still leaves an
accurate statement rather than a silent absence.

### 7.3 Never collapsed, stated as the inverse rule

- CAV-00, and **any** CAV-* attached to a rendered number, verbatim from `caveats.py`.
- Any suppression plate.
- Any per-row list that *replaced* a suppressed aggregate — below the floor those rows are
  the metric, not backup detail.
- The A→D flips list (Section 5): the strongest positive datum the corpus produces, and
  burying it wastes it.
- The figures themselves.

A caveat behind a toggle is a caveat nobody reads, and the caveats are the product.

### 7.4 Interactions

The complete list. There are four, and none of them is JavaScript.

1. Native `<details>` / `<summary>` disclosures. Real tab order, Enter toggles, expandable in
   print.
2. Find-in-page over figure text — free, because chart labels are real `<text>` nodes. This is
   the "look up one person" feature; no search box is built.
3. Anchor links per section plus a `:target` highlight.
4. `overflow-x: auto` with `tabindex="0"` and a visible label on each figure container, so a
   keyboard user can scroll a wide figure without a mouse.

Native SVG `<title>` on each mark and each row group carries per-mark detail (year, name,
stratum label). Because `<title>` tooltips are mouse-only, **every fact they show also exists
in the per-figure data table and the roster table** — that duplication is the condition for
keeping them at all.

### 7.5 Keyboard and screen reader

- One `<h1>`; sequential `<h2>`/`<h3>` matching the section numbering; skip-to-content link;
  `:focus-visible` outlines kept.
- Every control is a native focusable element. No `tabindex` greater than 0, no ARIA widget
  pattern, no hover-only or drag affordance.
- Each `<svg>` carries `role="img"` and `aria-labelledby` pointing at an in-SVG `<title>` and
  `<desc>`. The `<desc>` states, in words, the denominators **and the suppression state** —
  "77 of 277 people plotted; median not computed, 4 complete spans below the floor of 5" — so
  a screen-reader user receives the same suppression signal a sighted user gets from the plate.
- Text contrast ≥ 4.5:1, non-text marks ≥ 3:1. Sizes in rem; prose reflows to 320 px without
  horizontal scroll.
- Nothing animates, so `prefers-reduced-motion` needs no branch.
- Two prohibitions are enforced in the markup, not by convention: no sort control exists at
  any table header, and no element anywhere renders a composite score, grade, rating, or
  percentage of an individual person.

### 7.6 Print

- `@page { margin: 15mm }`.
- `@media print` force-expands disclosures:
  `details > *:not(summary) { display: block !important }`. Engine support is inconsistent,
  which is why every `<summary>` carries its own count as the fallback.
- `break-inside: avoid` on `figure`, on each caveat block, and on table rows;
  `break-after: avoid` on `h2`; `thead { display: table-header-group }` so headers repeat.
- The timeline figure is forced onto its own page.
- The sticky TOC becomes static. No ink-heavy background fills. Hatches print as hatches.
- Every encoding is redundant with shape or pattern, so the greyscale print carries the same
  facts as the screen.

---

## 8. Colour, shape and pattern vocabulary

One vocabulary across all four figures, so a mark means the same thing everywhere.

| Meaning | Shape | Fill | Also encoded by |
|---|---|---|---|
| Year with ≥1 lead-slot record | square | filled | — |
| Year with records, none in the lead slot | square | hollow | — |
| Person / record observation (C-LAG, C-SPAN, C-TEAM) | circle | filled | — |
| Right-censored observation ("at least this long") | circle | hollow | right-pointing tail |
| Left-censored | — | — | left arrowhead + dashed tail into the margin |
| Too recent to tell | circle | grey | shaded zone with its own label |
| Two or more records in one calendar year | open circle at x=0 | — | its own label |
| Record with ≥20 authors | circle | filled | heavier outline + axis annotation |
| Partial or indexing-lagged year bin | — | — | diagonal hatch + shaded band + text label |
| First / last interval | 1 px hairline | — | legend line disclaiming presence |

No hue carries a distinction on its own. There is no colour ramp anywhere on the page.

---

## 9. Degenerate and suppressed states, consolidated

| Figure | Empty / not computable | Suppressed |
|---|---|---|
| C-GANTT | `n_rows == 0` → prose "no person in this corpus appears more than once and holds no senior slot" + the single-appearance roll. Never an empty axis. | n/a (no floor). Missing `years`/`lead_years` → connectors only, titled "spans only — per-appearance detail unavailable". |
| C-LAG | `s4.not_computable` → top strip replaced by the report's verbatim sentence; **bottom strip still renders**. | `s4.suppressed` → no median tick; plate "median not computed — n=k, floor 5" in its place; **all dots stay**. |
| C-SPAN | `s5.cohort_denominator == 0` → prose + stratum-C count. Never a zero-height axis. | `s5.suppressed` → no bracket; plate in the complete lane; **all dots in all four lanes stay**. |
| C-YEAR | Every bin flagged `partial` or `indexing_lag` → counts as a text line instead of a figure. Zero-count years always draw as empty labelled columns. | Never suppresses by construction. |
| C-TEAM | Unreachable (G5 refuses first). | `s10.suppressed` → no bracket, plate, dots stay. `subset.suppressed` → lane still draws dots + its own denominator + "median not computed — n=k, floor 10". Lane never omitted. |

The rule underneath all of them: **a floor removes the aggregate, never the data.** Below the
floor the rows are the metric.

---

## 10. Amendments required to `docs/profile-metrics-spec.md`

These are spec amendments, not silent divergences. Make them explicitly in the same commit.

1. **L50** (adjudication table, "Single-appearance people: named or aggregated"). Change
   "Named on the timeline, excluded from every aggregate" to "**Named beside the timeline,
   never plotted on it, excluded from every aggregate**". The recorded reason — "author names
   are already public record, so the protection that matters is against
   inference-about-a-person, not against name disclosure" — justifies *naming*, not
   *plotting*, and survives intact when the names move to an adjacent list.
2. **L264** (Section 6.4 strata table, stratum C row). Change "Named on the Gantt only" to
   "**Named in the single-appearance roll and the per-year count strip; never given a
   timeline row**".
3. **L355 and L363** (Section 7.1). L355's "the Gantt produced by `analysis.render_gantt`
   with `exclude_names` from config (P3)" becomes the SVG timeline in this document, fed from
   `person_roster`. L363's "The Gantt is the primary presentation" stands — the timeline
   remains Section 2's primary presentation and the per-person evidence layer for Sections 4
   and 5 — but the sentence should name the SVG and state the A+B row filter, so the
   population it describes is unambiguous.
4. **Section 12 (implementation layout)** gains `svg.py`, `charts.py`, `html.py` and the two
   new test files.

Also record in `CHANGELOG.md`: the added `lead_years` / `years` / `first_date` fields, the
new `.html` output, and the two `render_gantt` corrections.

---

## 11. Acceptance checklist

Each item is checkable by looking at the output or by an assertion in a plain test script.
No item is satisfied by reading the source and agreeing with it.

**Geometry and row selection**

1. A `profile` run produces no file named `student_activity_gantt.png`, and no raster image
   of any kind.
2. The timeline SVG's `height` attribute equals `24 * n_rows + chrome` with `chrome ≤ 140`.
   At `n_rows = 77` the height is ≤ 1988 px — at least a 10× reduction from the measured
   21506 px.
3. `n_rows` in the timeline equals `metrics.s5.cohort_denominator`, and equals
   `metrics.s2.by_stratum["A"] + metrics.s2.by_stratum["B"]`. Asserted as an equality between
   the emitted figure and the metric dict, never against a constant.
4. No timeline row exists for any person whose `stratum` is `"C"` or `"D"`, and no row's name
   equals `provenance.author_name` or any entry of `provenance.exclude_names`.
5. `sum(s2.by_stratum.values()) == s2.denominator`.
6. The sequence of row-label names in the timeline SVG is byte-identical to the sequence of
   names in the Section 2 roster table, and both equal `sorted(rows, key=(first_date, name))`
   restricted to A+B.
7. Fed a 9-person fixture with appearance counts `[5,1,3,…]` and shared first-appearance
   dates, the row order does not change when the counts are permuted (R5; extends T61).
8. The single-appearance roll contains exactly `s2.by_stratum["C"]` names, and
   `s5.single_appearance_count` equals that number.
9. The stratum-C per-year strip's counts sum to `s2.by_stratum["C"]`.

**Chart integrity**

10. Every `<figure>` has a `<figcaption>` containing at least one substring matching
    `\d+ of \d+`.
11. No `%` character appears inside any `<svg>`, `<figcaption>` or `<desc>` at any n.
12. Every `<svg>` has `role="img"` and an `aria-labelledby` whose targets are an in-SVG
    `<title>` and `<desc>`; the `<desc>` contains the same denominators as the `<figcaption>`
    and, when a floor fired, the words "not computed".
13. The timeline subtitle contains all five declared counts (plotted, single-appearance,
    senior-collaborator, strict/loose gap, ≥50-author records) and none of them appears as a
    literal in the source — each is traceable to `s2.by_stratum`, `provenance.n_strict`,
    `provenance.n_loose` or `provenance.exclusions["hyperauthorship"]`.
14. C-YEAR draws one column per year in `[window_start_year, window_end_year]` inclusive,
    including zero-count years, and contains no `<polyline>`, no `<path>` with more than one
    line segment connecting column tops, and no element whose id or class contains `trend`,
    `slope` or `fit`.
15. Every C-YEAR column whose `partial` or `indexing_lag` flag is set carries both a hatch
    pattern reference and a visible text label.
16. C-TEAM contains the ≥50-author exclusion sentence with the count taken from
    `len(provenance.exclusions["hyperauthorship"])`, and the subset lane contains no IQR
    bracket element under any input.
17. With `s4.suppressed` True the SVG contains "median not computed" and zero median-tick
    elements; with it False, exactly one.
18. With `s4.not_computable` True the figure contains the string
    `no person in this corpus holds a first-author slot` byte-identical to
    `report._time_to_lead_body`'s wording, and the bottom strip still contains one dot per
    entry of `s4.still_without_lead`.
19. With `s5.suppressed` True, C-SPAN contains zero median/IQR bracket elements and the same
    total dot count as when it is False.
20. The total dot count in C-LAG (top strip + bottom strip + too-recent zone) equals
    `s3b.denominator`, which equals the timeline row count.

**Caveats and prohibitions**

21. Every CAV-* string on the page is byte-identical to the corresponding
    `caveats.CAVEATS[...]` after formatting; no paraphrase, no truncation.
22. No CAV-* string appears anywhere inside a `<details>` element.
23. Each figure's caveat block contains exactly its assigned ids: C-GANTT → CAV-02, CAV-03,
    CAV-09; C-LAG → CAV-06, CAV-07, CAV-08; C-SPAN → CAV-09, CAV-10, CAV-11; C-YEAR →
    CAV-17, CAV-18; C-TEAM → CAV-19.
24. CAV-00 is the first content after the header, before any figure and before provenance.
25. The page contains zero `<button>` elements, zero `onclick`/`on*` attributes, zero
    `data-sort` attributes, and no `<th>` containing an interactive child.
26. The page contains exactly one `<script>` element and its `type` is `application/json`.
27. A text scan of the whole page finds no `h-index`, `impact factor`, `citation count`,
    `score`, `grade`, `rank`, `rating` or `percentile` applied to a named person, and no `%`
    on any per-person row (extends T60 from the metrics spec to the HTML output).

**Environment**

28. Opening the `.html` from a `file://` URL with JavaScript disabled shows all four figures,
    every caveat, every roll and every table.
29. Printing to PDF from that state produces a document containing the single-appearance
    names, the titles list and Section 14 — nothing that is collapsed on screen is absent from
    the print.
30. Ctrl+F for an arbitrary cohort member's name matches inside the timeline SVG.
31. Every `<summary>`, anchor and figure container is reachable by Tab; no element has
    `tabindex` greater than 0.

**Regression and hygiene**

32. `python tests/test_profile.py` passes unchanged after the plumbing change — the added
    fields alter no existing key.
33. `person_roster` rows contain `years`, `lead_years` and `first_date`; `build_people`
    people contain `lead_years`.
34. Two runs over the same corpus produce byte-identical `.html`.
35. `ruff check .` is clean at line-length 110 with rules `E,F,W,I,UP,B`; every new file is
    under 800 lines.
36. With a G1-refusing corpus the `.html` contains the gate id, name, message and observed
    values, and zero `<svg>` elements.
