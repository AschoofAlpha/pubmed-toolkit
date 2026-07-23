#!/usr/bin/env python3
"""
Regression tests for defects found in code review.

Every test here corresponds to a bug that shipped. They are kept separate from
test_verify.py so the list of things that once went wrong stays legible.

Run: python tests/test_verify_regressions.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from urllib.error import URLError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pubmed_toolkit.verify.bibtex import (  # noqa: E402
    _clean_identifier,
    _read_pmid,
    load_json_refs,
    parse_bibtex,
)
from pubmed_toolkit.verify.checks import (  # noqa: E402
    compare_fields,
    cross_check_identifiers,
    decide_status,
)
from pubmed_toolkit.verify.clients import EntrezClient, HttpJsonClient  # noqa: E402
from pubmed_toolkit.verify.models import Issue, Reference, VerifyResult  # noqa: E402
from pubmed_toolkit.verify.normalize import (  # noqa: E402
    journal_matches,
    norm_author,
    norm_text,
    surname_candidates,
    surnames_agree,
    title_similarity,
)
from pubmed_toolkit.verify.runner import summarize, write_markdown_report  # noqa: E402

_passed = 0
_failed = 0


def check(label, actual, expected):
    global _passed, _failed
    ok = actual == expected
    if ok:
        _passed += 1
    else:
        _failed += 1
    detail = "" if ok else f"  (expected {expected!r}, got {actual!r})"
    print(f"  {'[PASS]' if ok else '[FAIL]'} {label}{detail}")


# ======================================================================
print("\n--- C1: `verified` must not be claimed when a check never ran ---")
# ======================================================================
# CrossRef answered, Entrez timed out. The bidirectional DOI<->PMID check —
# the headline feature — did not happen, so this entry is not certified.
r = VerifyResult(key="k", errors=["pubmed/esummary: timeout"])
check("resolved + error -> partial", decide_status(r, resolved_anything=True), "partial")

r = VerifyResult(key="k")
check("resolved + no error -> verified", decide_status(r, resolved_anything=True), "verified")

r = VerifyResult(key="k", issues=[Issue("year", "2015", "2014", "crossref")])
check("issues outrank a clean lookup", decide_status(r, resolved_anything=True), "mismatch")

r = VerifyResult(key="k", errors=["crossref/doi: http_429"])
check("nothing resolved + error -> error", decide_status(r, resolved_anything=False), "error")

r = VerifyResult(key="k")
check("nothing resolved, no error -> not_found",
      decide_status(r, resolved_anything=False), "not_found")

results = [
    VerifyResult(key="a", status="partial", errors=["pubmed/esummary: http_429"]),
    VerifyResult(key="b", status="verified"),
]
s = summarize(results)
check("summarize counts partial", s["partial"], 1)
check("summarize counts incomplete entries", s["incomplete"], 1)
check("a partial entry is not counted as verified", s["verified"], 1)


# ======================================================================
print("\n--- C2: accent folding in norm_text ---")
# ======================================================================
check("umlaut folds, not deleted", norm_text("Zeitschrift für Gastroenterologie"),
      "zeitschrift fur gastroenterologie")
check("journal with umlaut matches ASCII spelling",
      journal_matches("Zeitschrift fur Gastroenterologie",
                      "Zeitschrift für Gastroenterologie"), True)
check("Nordic o-slash folds", norm_text("Følling"), "folling")
check("title similarity survives transliteration",
      title_similarity("Uber Ausscheidung von Brenztraubensaure",
                       "Über Ausscheidung von Brenztraubensäure") == 1.0, True)
check("distinct journals still differ", journal_matches("Nature", "Cell"), False)


# ======================================================================
print("\n--- C3: an unregistered DOI is a finding, not an excuse ---")
# ======================================================================
r = VerifyResult(
    key="halluc", status="error",
    issues=[Issue("doi", "10.1/fabricated", "(not registered)", "crossref", "missing")],
    errors=["crossref/doi: http_404"],
)
s = summarize([r])
check("unregistered identifiers are counted", s["unresolvable_ids"], 1)

with tempfile.TemporaryDirectory() as d:
    path = write_markdown_report([r], os.path.join(d, "r.md"))
    report = path.read_text(encoding="utf-8")
check("report has an unregistered-identifier section",
      "## Unregistered identifiers" in report, True)
check("the fabricated DOI appears in the report", "10.1/fabricated" in report, True)
check("it is NOT filed under the excusing 'Unresolved' heading",
      "## Unresolved" in report, False)


# ======================================================================
print("\n--- H1: an unbalanced brace must not steal the next entry ---")
# ======================================================================
BROKEN = r"""
@article{s1,
  title = {Broken {brace},
  doi = {10.1/s1},
  year = {2020}
}
@article{s2,
  doi = {10.1/s2},
  year = {2021}
}
"""
refs = {r.key: r for r in parse_bibtex(BROKEN)}
check("both entries still parsed", sorted(refs), ["s1", "s2"])
check("s2 keeps its own DOI", refs["s2"].doi, "10.1/s2")
check("s1 did NOT absorb s2's DOI", refs["s1"].doi == "10.1/s2", False)


# ======================================================================
print("\n--- H2: JSON input must clean identifiers like BibTeX does ---")
# ======================================================================
payload = {"references": [
    {"key": "a", "doi": "https://doi.org/10.1038/nature13480", "pmid": "PMID: 25079317"},
]}
with tempfile.TemporaryDirectory() as d:
    p = os.path.join(d, "refs.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    jrefs = load_json_refs(p)
check("DOI URL prefix stripped on the JSON path", jrefs[0].doi, "10.1038/nature13480")
check("PMID prefix stripped on the JSON path", jrefs[0].pmid, "25079317")


# ======================================================================
print("\n--- H3: `conflict` requires two user-supplied identifiers ---")
# ======================================================================
doi_only = Reference(key="k", doi="10.1002/hep.31288")   # no PMID supplied
pubmed_meta = {"doi": "10.1002/hep.31289"}               # PubMed records another DOI
issues = cross_check_identifiers(doi_only, derived_pmid="123", pubmed_meta=pubmed_meta)
check("no conflict when the user never supplied a PMID", len(issues), 0)

both = Reference(key="k", doi="10.1002/hep.31288", pmid="999")
issues = cross_check_identifiers(both, derived_pmid="999", pubmed_meta=pubmed_meta)
check("conflict still raised when both identifiers were supplied", len(issues), 1)


# ======================================================================
print("\n--- H4: get_json must always return a dict ---")
# ======================================================================
class _FakeResp:
    def __init__(self, payload):
        self._p = payload.encode()

    def read(self):
        return self._p

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


import pubmed_toolkit.verify.clients as clients_mod  # noqa: E402

_orig_urlopen = clients_mod.urlopen
try:
    clients_mod.urlopen = lambda *a, **k: _FakeResp("[]")
    out = HttpJsonClient().get_json("https://example.invalid/x")
    check("a JSON list becomes an error dict", out, {"__error__": "not_an_object"})
    check("the sentinel is detectable", "__error__" in out, True)

    clients_mod.urlopen = lambda *a, **k: _FakeResp('"a string"')
    check("a JSON string becomes an error dict",
          HttpJsonClient().get_json("https://example.invalid/x"),
          {"__error__": "not_an_object"})

    clients_mod.urlopen = lambda *a, **k: _FakeResp('{"ok": 1}')
    check("a JSON object passes through",
          HttpJsonClient().get_json("https://example.invalid/x"), {"ok": 1})
finally:
    clients_mod.urlopen = _orig_urlopen


# ======================================================================
print("\n--- M2: PMID cleaning must reject, not salvage ---")
# ======================================================================
check("a PMCID does not become a PMID", _clean_identifier("PMC3388858", "pmid"), "")
check("an arXiv id does not become a PMID", _clean_identifier("arXiv:2301.00234", "pmid"), "")
check("an over-long number is rejected", _clean_identifier("123456789012", "pmid"), "")
check("a small PMID is kept", _clean_identifier("13", "pmid"), "13")
check("a 'PMID:' prefix is stripped", _clean_identifier("PMID: 25079317", "pmid"), "25079317")
check("a PubMed URL is stripped",
      _clean_identifier("https://pubmed.ncbi.nlm.nih.gov/25079317/", "pmid"), "25079317")

check("eprint read when eprinttype is pmid",
      _read_pmid({"eprinttype": "pmid", "eprint": "25079317"}), "25079317")
check("eprint read when eprinttype is pubmed",
      _read_pmid({"eprinttype": "pubmed", "eprint": "25079317"}), "25079317")
check("arXiv eprint is ignored",
      _read_pmid({"eprinttype": "arxiv", "eprint": "2301.00234"}), "")
check("an explicit pmid field wins",
      _read_pmid({"pmid": "111", "eprinttype": "pmid", "eprint": "222"}), "111")


# ======================================================================
print("\n--- M9: commented-out entries must not be verified ---")
# ======================================================================
COMMENTED = r"""
% @article{disabled2020,
%   doi = {10.1/should-not-appear}
% }
@article{live2021,
  doi = {10.1/real},
  title = {A live entry with 100% coverage}
}
"""
keys = [r.key for r in parse_bibtex(COMMENTED)]
check("commented entry skipped", keys, ["live2021"])
live = parse_bibtex(COMMENTED)[0]
check("live entry intact", live.doi, "10.1/real")
check("a % inside a braced value is preserved",
      "100% coverage" in live.title, True)


# ======================================================================
print("\n--- M4: author roster is not truncated ---")
# ======================================================================
meta = {"first_author": "Aaa A",
        "all_authors": [f"N{i}" for i in range(1, 12)] + ["Target T"]}
check("a 12th author is still recognised",
      len(compare_fields(Reference(key="k", first_author="Target"), meta, "crossref")), 0)


# ======================================================================
print("\n--- P0-1: non-Latin names normalised to nothing ---")
# ======================================================================
# norm_author filtered with [^a-z]+, so any CJK, Cyrillic or Greek name reduced
# to ''. compare_fields then saw an empty supplied value and skipped the author
# check entirely — silently, on the very name class this tool exists to
# disambiguate.
check("CJK surname survives normalisation", norm_author("李四"), "李四")
check("Cyrillic surname survives", norm_author("Иванов"), "иванов")
check("accented Latin still folds", norm_author("Følling"), "folling")
check("punctuation still stripped", norm_author("O'Brien"), "obrien")

check("identical CJK names agree", surnames_agree("李四", "李四"), True)
check("different CJK names disagree", surnames_agree("李四", "王五"), False)
check("CJK author mismatch is now reported",
      len(compare_fields(Reference(key="k", first_author="李四"),
                         {"first_author": "王五"}, "crossref")), 1)
check("CJK author match is not reported",
      len(compare_fields(Reference(key="k", first_author="李四"),
                         {"first_author": "李四"}, "crossref")), 0)


# ======================================================================
print("\n--- P0-2: ambiguous name order produced false mismatches ---")
# ======================================================================
# 'Jing WU' is structurally identical to 'Bray FJ'. The old heuristic read the
# short all-caps token as initials, so a correct citation written given-first
# with a capitalised surname was flagged as the wrong author.
check("given+SURNAME matches PubMed style", surnames_agree("Jing WU", "Wu J"), True)
check("two-letter caps surname matches", surnames_agree("Yi LI", "Li Y"), True)
check("surname+initials matches bare family name", surnames_agree("Bray F", "Bray"), True)
check("western order still matches", surnames_agree("Freddie Bray", "Bray"), True)
check("compound surname matches", surnames_agree("Van Der Berg J", "Van Der Berg"), True)
check("a genuinely different author is still flagged",
      surnames_agree("Smith John", "Jones"), False)

check("a single letter is never a surname candidate",
      "f" in surname_candidates("Bray F"), False)
check("compound surname yields a joined candidate",
      "vanderberg" in surname_candidates("Van Der Berg"), True)
check("wrong author still reported despite permissive matching",
      len(compare_fields(Reference(key="k", first_author="Jing WU"),
                         {"first_author": "Zhang Q"}, "pubmed")), 1)


# ======================================================================
print("\n--- M10: @string macros were compared literally ---")
# ======================================================================
# `journal = nat` was read as the literal 'nat' and compared against 'Nature',
# reporting a mismatch on a perfectly correct entry.
r = parse_bibtex('@string{nat = "Nature"}\n@article{a, journal = nat, doi = {10.1/x}}')
check("macro resolved to its definition", r[0].journal, "Nature")
check("no spurious journal mismatch after resolution",
      len(compare_fields(r[0], {"journal": "Nature"}, "crossref")), 0)

r = parse_bibtex('@string{nrc = {Nat Rev Cancer}}\n@article{b, journal = nrc # " Suppl"}')
check("concatenation keeps the literal's leading space", r[0].journal, "Nat Rev Cancer Suppl")

r = parse_bibtex('@string{x = {Y}}@article{c, journal = x}')
check("macro defined on the same line resolves", r[0].journal, "Y")

r = parse_bibtex("@article{d, journal = notdefined}")
check("undefined macro kept verbatim rather than blanked", r[0].journal, "notdefined")

r = parse_bibtex('@string{j = {Nat Rev}}\n@article{e, journal = j # ", Suppl", year = {2020}}')
check("comma inside a quoted concat piece does not truncate",
      r[0].journal, "Nat Rev, Suppl")
check("the field after a comma-bearing value is still read", r[0].year, "2020")


# ======================================================================
print("\n--- M1: paren-delimited entries were dropped silently ---")
# ======================================================================
# @article(...) is legal BibTeX. The entry regex only accepted braces, so these
# entries vanished from the bibliography without any warning.
r = parse_bibtex("@article(paren2020, title = {A paren entry}, doi = {10.1/x})")
check("paren entry is parsed", len(r), 1)
check("paren entry key read", r[0].key, "paren2020")
check("paren entry doi read", r[0].doi, "10.1/x")

r = parse_bibtex("@article(p2, title = {Study (phase 3) results}, year = {2020})")
check("a ')' inside a braced value does not end the entry early",
      r[0].title, "Study (phase 3) results")
check("fields after the nested paren are still read", r[0].year, "2020")

r = parse_bibtex("@article{brace1, doi = {10.1/a}}\n@article(paren1, doi = {10.1/b})")
check("brace and paren entries coexist", len(r), 2)
check("both identifiers survive", sorted(x.doi for x in r), ["10.1/a", "10.1/b"])


# ======================================================================
print("\n--- M6: identifier resolution is batched ---")
# ======================================================================
# Entrez allows 3 requests/second, and that cap — not --max-workers — bounds
# throughput. One reference at a time costs two calls each, so 500 references
# spent 5-6 minutes waiting on the limiter.
class _CountingHttp:
    """Stands in for HttpJsonClient, recording every call and its payload."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.tool = "test"
        self.email = ""

    def post_json(self, url, fields, retries=1):
        self.calls.append((url, fields))
        if "esearch" in url:
            # Two of the three DOIs exist in PubMed; the third resolves to nothing.
            return {"esearchresult": {"idlist": ["111", "222"]}}
        return {"result": {
            "uids": ["111", "222"],
            "111": {"articleids": [{"idtype": "doi", "value": "10.1/a"}],
                    "authors": [{"name": "Alpha A"}], "pubdate": "2020",
                    "fulljournalname": "Journal A", "title": "A"},
            "222": {"articleids": [{"idtype": "doi", "value": "10.1/b"}],
                    "authors": [{"name": "Beta B"}], "pubdate": "2021",
                    "fulljournalname": "Journal B", "title": "B"},
        }}

    def get_json(self, url, retries=1):
        self.calls.append((url, {}))
        return {"__error__": "unexpected_individual_call"}


http = _CountingHttp()
entrez = EntrezClient(http, api_key="")
mapping = entrez.batch_pmids_from_dois(["10.1/a", "10.1/b", "10.1/missing"])

check("three DOIs resolved in two requests", len(http.calls), 2)
check("first request is an esearch", "esearch" in http.calls[0][0], True)
check("second request is an esummary", "esummary" in http.calls[1][0], True)
check("mapping built from the summary records", mapping,
      {"10.1/a": "111", "10.1/b": "222"})
check("a DOI PubMed does not know is simply absent", "10.1/missing" in mapping, False)

# DOIs contain parentheses, which are grouping operators in Entrez syntax. If
# they are not quoted the query silently means something else.
http = _CountingHttp()
EntrezClient(http, api_key="").batch_pmids_from_dois(["10.1016/S0140-6736(20)31288-5"])
check("DOIs are quoted inside the OR query",
      '"10.1016/S0140-6736(20)31288-5"[doi]' in http.calls[0][1]["term"], True)

http = _CountingHttp()
metas = EntrezClient(http, api_key="").batch_summaries(["111", "222"])
check("one request covers many PMIDs", len(http.calls), 1)
check("summaries keyed by pmid", sorted(metas), ["111", "222"])
check("doi extracted from articleids", metas["111"]["doi"], "10.1/a")


# ======================================================================
print("\n--- connection errors are retried, not reported as failures ---")
# ======================================================================
# A dropped TLS handshake ("EOF occurred in violation of protocol") happens
# routinely when several requests open at once. Without a retry it downgraded a
# perfectly verifiable entry to `partial`, reporting a network hiccup as an
# unfinished check.
class _FlakyOpener:
    def __init__(self, fail_times: int):
        self.remaining = fail_times
        self.attempts = 0

    def __call__(self, req, timeout=None):
        self.attempts += 1
        if self.remaining > 0:
            self.remaining -= 1
            raise URLError("EOF occurred in violation of protocol")
        return _FakeResponse(b'{"ok": true}')


class _FakeResponse:
    def __init__(self, payload: bytes):
        self.payload = payload

    def read(self):
        return self.payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


import pubmed_toolkit.verify.clients as _clients  # noqa: E402

_real_urlopen = _clients.urlopen
_real_sleep = _clients.time.sleep
_clients.time.sleep = lambda *_a, **_k: None
try:
    flaky = _FlakyOpener(fail_times=1)
    _clients.urlopen = flaky
    out = HttpJsonClient().get_json("https://example.invalid/x", retries=2)
    check("a single connection drop is retried and succeeds", out, {"ok": True})
    check("it took exactly two attempts", flaky.attempts, 2)

    always = _FlakyOpener(fail_times=99)
    _clients.urlopen = always
    out = HttpJsonClient().get_json("https://example.invalid/x", retries=2)
    check("persistent failure still reports an error", "__error__" in out, True)
    check("retries are bounded", always.attempts, 3)
finally:
    _clients.urlopen = _real_urlopen
    _clients.time.sleep = _real_sleep


print("\n--- PMID discovery across real exporter formats ---")
# Measured on real bibliographies at v0.2.0: PMIDs appeared in a `pmid` field
# 0% of the time. Zotero -- the dominant reference manager in biomedicine --
# maps its "Extra" field to `note`, so its PMIDs arrive as prose. Missing them
# meant the bidirectional DOI<->PMID check could not fire on the exports this
# module's intended users actually produce.
_PMID_CASES = [
    ("explicit pmid field", r"@article{a, doi={10.1/x}, pmid={25079317}}", "25079317"),
    ("biblatex eprint", r"@article{b, doi={10.1/x}, eprint={25079317}, eprinttype={pmid}}", "25079317"),
    ("zotero note", r"@article{c, doi={10.1/x}, note={PMID: 25079317}}", "25079317"),
    ("zotero annote", r"@article{d, doi={10.1/x}, annote={PMID: 25079317}}", "25079317"),
    ("pmid without colon", r"@article{e, doi={10.1/x}, note={PMID 25079317}}", "25079317"),
    ("pmid amid other prose", r"@article{f, doi={10.1/x}, note={Publisher: Nature. PMID: 25079317. Cited 40}}", "25079317"),
]
for label, src, expected in _PMID_CASES:
    check(f"reads PMID from {label}", parse_bibtex(src)[0].pmid, expected)

# Rejections matter more than the finds: a confidently wrong PMID gets
# "verified" against the wrong paper, which is worse than no PMID at all.
_PMID_REJECT = [
    ("PMCID is not a PMID", r"@article{g, doi={10.1/x}, note={PMCID: PMC3388858}}"),
    ("bare PMC accession", r"@article{h, doi={10.1/x}, note={PMC11704023}}"),
    ("unlabelled digits are not a PMID", r"@article{i, doi={10.1/x}, note={Cited by 25079317 times}}"),
    ("arXiv eprint is not a PMID", r"@article{j, doi={10.1/x}, eprint={2301.00001}, eprinttype={arxiv}}"),
]
for label, src in _PMID_REJECT:
    check(f"rejects: {label}", parse_bibtex(src)[0].pmid, "")


print("\n" + "=" * 70)
print(f"Summary: {_passed} passed / {_failed} failed / {_passed + _failed} total")
print("=" * 70)
sys.exit(0 if _failed == 0 else 1)
