"""
The verbatim caveat strings, and the register of what was deliberately not computed.

Sections 8 and 10 of docs/profile-metrics-spec.md. These live as module
constants and are never paraphrased at the call site: they are the part of the
report that says what the numbers cannot mean, and a paraphrase is how that
part quietly weakens.

English only. Translation is out of scope.
"""

from __future__ import annotations

from typing import Any

CAVEATS: dict[str, str] = {
    "CAV-00": (
        "This report describes publication metadata, and nothing else. PubMed contains only people "
        "who published: anyone who joined this lab and left without a paper is absent from every "
        "number below, from both the numerator and the denominator. The size of that missing group "
        "cannot be recovered from this data. The report cannot see advising style, funding, working "
        "hours, whether anyone graduated, lab culture, or what happened to people who left — which "
        "are the things you actually want to know. Do not let the numbers that are here stand in for "
        "the ones that are not."
    ),
    "CAV-01": (
        "{n} further papers matched the name but carried no verifiable identity evidence and were "
        "excluded. That is the upper bound on how much this corpus is missing for identity reasons. "
        "A PI who changed institution inside the window loses their earlier papers this way unless "
        "every institution variant is configured."
    ),
    "CAV-02": (
        "People are identified by name string. Romanised names collide heavily, and the tool has "
        "ORCID and affiliation keywords for the PI only — co-authors have nothing equivalent. Two "
        "people with one name merge into one row with an inflated count and an over-long span; one "
        "person recorded two ways splits into two short rows. Strict keying finds {n_strict} people, "
        "loose keying finds {n_loose}; the gap is the error bar on every count in this section."
    ),
    "CAV-03": (
        "Position labels are inferences from the byline, not facts about a person. A PhD student, "
        "postdoc, technician, staff scientist, clinical fellow, rotation student and visiting scholar "
        "all produce the same positional shape, and no field in PubMed separates them."
    ),
    "CAV-04": (
        "This counts slots on papers, not people. A high trainee-led count can come from three "
        "prolific people in a twenty-person lab. It describes the shape of the lab's output, not your "
        "personal odds."
    ),
    "CAV-05": (
        "Papers where a trainee elsewhere led and this PI was a middle author are in this corpus, but "
        "papers where this PI is absent entirely are not — so this says nothing about the PI's "
        "behaviour outside their own lab."
    ),
    "CAV-06": (
        "Counted only over people who published at least once. Anyone who joined and left without a "
        "paper is in neither bucket. This is not a rate and must not be read as your chance of "
        "leading a paper here."
    ),
    "CAV-07": (
        "Measured on publication dates, which trail the work by roughly one to two years including "
        "review. A median of three years does not mean you publish in year three."
    ),
    "CAV-08": (
        "Computed only over people who reached a first-author slot. The people still without one are "
        "printed beside it for exactly this reason — read both numbers or neither."
    ),
    "CAV-09": (
        "This is the interval between two publication dates, not time in the lab. The period before "
        "someone's first paper — typically the first two to three years of a PhD — is invisible by "
        "construction, and a paper can appear a year or more after the person has left."
    ),
    "CAV-10": (
        "The median covers only people whose whole span fits inside the search window, which biases "
        "it toward short stays: at years_back={years_back} anyone long-tenured is censored at one end "
        "or both. A growing lab looks like it churns people; a lab whose students all left years ago "
        "shows clean, complete, long spans."
    ),
    "CAV-11": (
        "A short span supports \"fast and efficient\" and \"left after a year\" equally well. Nothing "
        "in this data distinguishes them."
    ),
    "CAV-12": (
        "Author count is not headcount. This counts people whose papers happened to come out that "
        "year, so a lab that just doubled shows no change for two years and a lab that emptied last "
        "year still looks full. Co-authors are not lab members and PubMed offers no way to separate "
        "them."
    ),
    "CAV-13": (
        "Not measured. This corpus was built with a first/last/corresponding-author filter, so the "
        "PI's byline position is decided by the filter rather than by the data. Re-fetch with the "
        "profile path, which verifies identity without filtering on position."
    ),
    "CAV-14": (
        "Last-author-equals-senior-author is a biomedical convention, not a rule. In many clinical "
        "departments the division head is last on everything regardless of involvement — which is "
        "precisely the case this count exists to detect and precisely the case it cannot detect."
    ),
    "CAV-15": (
        "Corresponding-author status is inferred from an email address appearing in the affiliation "
        "string; PubMed has no corresponding-author field. It tracks journal formatting policy and "
        "changes over time. Email coverage in this corpus: {covered} of {total} papers."
    ),
    "CAV-16": (
        "PubMed carries the equal-contribution attribute only when the publisher supplies it. Absence "
        "is not evidence of absence: journals that mark co-first authorship with a footnote and "
        "deposit nothing produce a zero here. No rate is computed from this field for that reason."
    ),
    "CAV-17": (
        "The first and last bins are partial: the window starts mid-year, and the most recent 18 "
        "months are undercounted by PubMed indexing lag and by ahead-of-print records with no issue "
        "date yet. Every lab looks like it is winding down at the right-hand edge."
    ),
    "CAV-18": (
        "These are PubMed records, not research papers. Publication type is not parsed, so reviews, "
        "letters, comments and case reports are counted alongside primary research except where a "
        "title made the record identifiable as a correction."
    ),
    "CAV-19": (
        "A small team supports \"you get attention\" and \"there is nobody here to learn from\" "
        "equally. A large one supports \"generous inclusion\" and \"your contribution disappears into "
        "position 14\". The count cannot choose between them."
    ),
    "CAV-20": (
        "Journal names are printed as recorded and are not normalised, so one journal can appear "
        "twice under its full title and its abbreviation. No impact factor, quartile or tier is "
        "shown, computed or stored. Concentration in one venue supports \"deep specialisation\" and "
        "\"a reliable low-bar outlet\" equally."
    ),
    "CAV-21": (
        "These are affiliation strings, not institutions. They are unnormalised free text and are not "
        "counted or grouped. Coverage is strongly time-biased: older PubMed records often carry only "
        "the first author's affiliation, so years are not comparable to each other. An author with "
        "joint appointments has all of them joined into one string, so a shared home institution "
        "hides the external one."
    ),
    "CAV-22": (
        "Titles are printed verbatim and ungrouped. No topic classification is offered: research "
        "direction cannot be measured honestly from the fields this toolkit parses, and stability "
        "would be as easy to read as \"a mined-out vein\" as \"deep expertise\"."
    ),
}


def caveat(caveat_id: str, **fields: Any) -> str:
    """Formatted caveat text. Missing fields raise rather than render a hole."""
    return CAVEATS[caveat_id].format(**fields)


# Section 10 of the spec, rendered verbatim as report Section 14. It is part of
# the deliverable: a reader who cannot see what was deliberately left out has no
# way to tell a considered omission from an oversight.
DROPPED_REGISTER: tuple[tuple[str, str], ...] = (
    (
        "Research direction stability / topic drift",
        "parse_article extracts no MeSH and no keywords. Adding MeSH would not fix it: MeSH indexing "
        "lags publication by months, so the newest year is systematically under-indexed and the "
        "pipeline would manufacture a drift signal that is pure artifact. Title-word overlap measures "
        "house style. Replaced by Section 13, titles by year.",
    ),
    (
        "render_topic_charts",
        "Reads an externally produced _topic_extraction.json that this toolkit never writes, and its "
        "BUCKET_NAMES are one specific lab's subject areas. Out of scope for the profile report.",
    ),
    (
        "Count of collaborating institutions",
        "Affiliation strings are unnormalised; counting them measures string variance, not "
        "collaboration. It is also a prestige proxy, which is the ranking use-case this product "
        "excludes. Replaced by Section 12.",
    ),
    (
        "External-affiliation dependency ratio",
        "Same denominator problem plus era-dependent coverage, and joint appointments are space-joined "
        "into one string so external ties disappear. Any trend in it is a metadata trend that reads as "
        "a scientific one.",
    ),
    (
        "Lead-author conversion rate",
        "The denominator is conditioned on having published, so the rate is optimistic by an "
        "unmeasurable amount and is read as personal odds. Replaced by the three-bucket partition in "
        "Section 3.",
    ),
    (
        "Co-first authorship rate",
        "EqualContrib is publisher-deposited with unknown, journal-dependent missingness. Replaced by "
        "a count and a position breakdown in Section 8.",
    ),
    (
        "Mean first-author papers per trainee",
        "A ratio of two undercounted quantities, dominated by the single most productive person, that "
        "reads as a productivity score for a named individual.",
    ),
    (
        "Corresponding-author rate as a headline",
        "An email-presence proxy. Reported only beside its own coverage rate, never alone.",
    ),
    (
        "Citation counts, h-index, citations per paper, field-normalised impact",
        "efetch returns none of it, and citation ranking is out of scope.",
    ),
    (
        "Journal Impact Factor, quartile, tier, CAS partition",
        "Journal-level proxies for individual paper quality. Prohibited even if a table were available "
        "locally.",
    ),
    (
        "Any composite score, weighted index, grade, or star rating",
        "Encodes weights the data cannot justify and recreates the people-ranking this tool excludes.",
    ),
    (
        "Graduation rate, time to degree, attrition, \"students who left\"",
        "The denominator — everyone who joined — is structurally unobservable. Stated as prose in "
        "CAV-00, never approximated with a number.",
    ),
    (
        "Authorship \"fairness\" or \"credit generosity\" scores",
        "Require knowing contribution, which is in no field at any level.",
    ),
    (
        "Trends, fitted slopes, year-over-year percentage change",
        "Five right-censored integer points do not support a slope. 3 papers to 5 is not \"+67%\".",
    ),
    (
        "Any distinction between PhD student, master's student, postdoc, staff scientist, technician, "
        "clinical fellow, visiting scholar",
        "No field supports it.",
    ),
    (
        "Span-based seniority reclassification",
        "A span cap encodes an assumption about degree length and evicts the longest-serving trainees, "
        "who are the most informative people in the corpus.",
    ),
    (
        "Affiliation-gated cohort membership",
        "Pre-2014 records carry only the first author's affiliation, so the gate deletes real trainees "
        "for a data-coverage reason.",
    ),
)
