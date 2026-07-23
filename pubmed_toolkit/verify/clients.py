"""
CrossRef and NCBI Entrez clients used by the reference verifier.

Deliberately built on urllib rather than requests so the verifier has no
third-party dependency and can be vendored on its own.

Two behaviours matter here and are easy to get wrong:

1. **Hard per-request timeout.** A single hanging URL must not stall a batch.
   Every call passes an explicit timeout; there is no unbounded wait anywhere.
2. **Entrez rate limiting.** NCBI allows 3 requests/second without an API key
   and 10/second with one. Exceeding it gets your IP throttled, which surfaces
   as sporadic empty results rather than a clean error, so the limiter is
   enforced process-wide by a lock rather than left to the caller.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger("pubmed_toolkit.verify.clients")

CROSSREF_API = "https://api.crossref.org/works"
ENTREZ_API = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


def _safe_url(url: str) -> str:
    """Strip the query string so credentials never reach a log file."""
    return url.split("?", 1)[0]


def _retry_after_seconds(err: HTTPError) -> float:
    """Read a Retry-After header, if the server sent a usable one."""
    try:
        return float((err.headers or {}).get("Retry-After", ""))
    except (TypeError, ValueError):
        return 0.0


class _RateLimiter:
    """Minimum interval between calls, safe across threads."""

    def __init__(self, min_interval: float):
        self.min_interval = min_interval
        self._lock = threading.Lock()
        self._last = 0.0

    def wait(self) -> None:
        # The sleep happens while holding the lock so that spacing is exact,
        # but the caller performs its HTTP request after wait() returns, so
        # network I/O is not serialised beyond the required interval.
        with self._lock:
            elapsed = time.monotonic() - self._last
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
            self._last = time.monotonic()


# Rate limits belong to the remote service, not to a client object, so these are
# module-level singletons. Two ReferenceVerifier instances (or a verify run
# alongside the toolkit's own eutils traffic) would otherwise each keep their own
# clock and together exceed NCBI's cap — which surfaces as sporadic empty
# results rather than a clean error.
_ENTREZ_LIMITER_ANON = _RateLimiter(0.34)   # NCBI: 3 req/s without an API key
_ENTREZ_LIMITER_KEYED = _RateLimiter(0.11)  # NCBI: 10 req/s with one
_CROSSREF_LIMITER = _RateLimiter(0.02)      # CrossRef public pool, ~50 req/s


class HttpJsonClient:
    """Minimal JSON-over-HTTP client with a hard timeout and a polite UA."""

    def __init__(self, email: str = "", timeout: float = 12.0, tool: str = "pubmed-toolkit"):
        self.email = email
        self.timeout = timeout
        self.tool = tool

    @property
    def user_agent(self) -> str:
        if self.email:
            return f"{self.tool}/1.0 (mailto:{self.email})"
        return f"{self.tool}/1.0"

    def get_json(self, url: str, retries: int = 1) -> dict[str, Any]:
        """
        Return parsed JSON, or {"__error__": reason} — never raises.

        Always returns a dict. A JSON document may legitimately be a list or a
        scalar, and callers immediately do `.get(...)` on the result, so a bare
        `json.loads` return could raise AttributeError past the `__error__`
        sentinel check (`"__error__" in []` is False).
        """
        req = Request(url, headers={"User-Agent": self.user_agent, "Accept": "application/json"})
        return self._fetch(req, url, retries)

    def post_json(self, url: str, fields: dict[str, str], retries: int = 1) -> dict[str, Any]:
        """
        Same contract as get_json, but sends the parameters in the body.

        Batched Entrez queries OR together dozens of DOIs and overrun what NCBI
        accepts in a URL; their guidance is to POST anything large.
        """
        req = Request(
            url,
            data=urlencode(fields).encode("utf-8"),
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        return self._fetch(req, url, retries)

    def _fetch(self, req: Request, url: str, retries: int) -> dict[str, Any]:
        attempt = 0
        while True:
            try:
                with urlopen(req, timeout=self.timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8", errors="replace"))
                return data if isinstance(data, dict) else {"__error__": "not_an_object"}
            except HTTPError as e:
                # 429/503 are transient and expected on large bibliographies.
                if e.code in (429, 503) and attempt < retries:
                    delay = _retry_after_seconds(e) or (2.0 * (attempt + 1))
                    logger.debug("%s from %s; retrying in %.1fs", e.code, _safe_url(url), delay)
                    time.sleep(min(delay, 30.0))
                    attempt += 1
                    continue
                return {"__error__": f"http_{e.code}"}
            except TimeoutError:
                # Must precede URLError: socket.timeout is TimeoutError and is
                # not a URLError subclass, so ordering matters for the message.
                if attempt < retries:
                    time.sleep(1.0 * (attempt + 1))
                    attempt += 1
                    continue
                return {"__error__": "timeout"}
            except URLError as e:
                # Connection-level failures are transient too. Dropped TLS
                # handshakes ("EOF occurred in violation of protocol") show up
                # regularly when several requests open at once, and without a
                # retry they downgrade a perfectly verifiable entry to
                # `partial` — reporting a network hiccup as an unfinished check.
                if attempt < retries:
                    delay = 1.0 * (attempt + 1)
                    logger.debug("connection error from %s (%s); retrying in %.1fs",
                                 _safe_url(url), getattr(e, "reason", "unknown"), delay)
                    time.sleep(delay)
                    attempt += 1
                    continue
                return {"__error__": f"urlerror_{getattr(e, 'reason', 'unknown')}"}
            except json.JSONDecodeError:
                return {"__error__": "invalid_json"}
            except Exception as e:  # noqa: BLE001 - last resort, must not kill the batch
                # Log the sanitised URL: the raw one carries the NCBI API key
                # and the contact email as query parameters.
                logger.debug("unexpected error fetching %s: %s", _safe_url(url), e)
                return {"__error__": f"unexpected_{type(e).__name__}"}


class CrossRefClient:
    """Resolves DOIs and searches CrossRef by bibliographic string."""

    SELECT = "DOI,title,author,issued,container-title,volume,issue,page,type"

    def __init__(self, http: HttpJsonClient):
        self.http = http

    def by_doi(self, doi: str) -> dict[str, Any]:
        if not doi:
            return {"__error__": "no_doi"}
        _CROSSREF_LIMITER.wait()
        data = self.http.get_json(f"{CROSSREF_API}/{quote(doi)}")
        if "__error__" in data:
            return data
        return self._extract(data.get("message", {}))

    def search(self, title: str, author_hint: str = "", rows: int = 5) -> list[dict[str, Any]]:
        """Bibliographic search, used for entries that carry no DOI."""
        if not title:
            return []
        params = {"query.bibliographic": title, "rows": str(rows), "select": self.SELECT}
        if author_hint:
            params["query.author"] = author_hint
        _CROSSREF_LIMITER.wait()
        data = self.http.get_json(f"{CROSSREF_API}?{urlencode(params)}")
        if "__error__" in data:
            return []
        items = data.get("message", {}).get("items", []) or []
        return [self._extract(item) for item in items]

    @staticmethod
    def _extract(m: dict[str, Any]) -> dict[str, Any]:
        issued = m.get("issued", {}).get("date-parts") or [[None]]
        year = ""
        if issued and issued[0] and issued[0][0]:
            year = str(issued[0][0])
        authors = m.get("author") or []
        first_author = ""
        if authors:
            first_author = authors[0].get("family") or authors[0].get("name") or ""
        return {
            "doi": m.get("DOI", ""),
            "title": " ".join(m.get("title") or []),
            "first_author": first_author,
            "all_authors": [(a.get("family") or a.get("name") or "") for a in authors],
            "year": year,
            "journal": " ".join(m.get("container-title") or []),
            "volume": m.get("volume") or "",
            "issue": m.get("issue") or "",
            "pages": m.get("page") or "",
            "type": m.get("type") or "",
        }


class EntrezClient:
    """PubMed lookups: DOI -> PMID (ESearch) and PMID -> metadata (ESummary)."""

    def __init__(self, http: HttpJsonClient, api_key: str = ""):
        self.http = http
        self.api_key = api_key
        self.limiter = _ENTREZ_LIMITER_KEYED if api_key else _ENTREZ_LIMITER_ANON

    # How many identifiers go into one batched request. ESummary accepts far
    # more, but a modest chunk keeps any single failure cheap to retry.
    DOI_CHUNK = 50
    PMID_CHUNK = 200

    def _param_dict(self, **kw: str) -> dict[str, str]:
        params = {"retmode": "json", "tool": self.http.tool, **kw}
        if self.http.email:
            params["email"] = self.http.email
        if self.api_key:
            params["api_key"] = self.api_key
        return params

    def _params(self, **kw: str) -> str:
        return urlencode(self._param_dict(**kw))

    def pmid_from_doi(self, doi: str) -> str:
        """Forward resolution: DOI -> PMID."""
        if not doi:
            return ""
        self.limiter.wait()
        url = f"{ENTREZ_API}/esearch.fcgi?{self._params(db='pubmed', term=f'{doi}[doi]')}"
        data = self.http.get_json(url)
        if "__error__" in data:
            return ""
        ids = data.get("esearchresult", {}).get("idlist", []) or []
        return ids[0] if ids else ""

    def batch_pmids_from_dois(self, dois: list[str]) -> dict[str, str]:
        """
        Resolve many DOIs to PMIDs in a handful of requests.

        Two requests per chunk: one ESearch ORing the DOIs together, then one
        ESummary over the PMIDs it returned. ESearch gives back an unordered id
        list with no indication of which DOI produced which PMID, so the mapping
        is rebuilt from the `articleids` of the ESummary records — which is the
        authoritative source for a record's DOI anyway.

        NCBI's PMC ID Converter would do this in one call, but it only covers
        PMC. Lancet, NEJM and JAMA DOIs all come back "not found in PMC" while
        ESearch resolves them correctly, so using it would silently disable the
        bidirectional check on exactly the clinical literature that matters most.

        Returns {lowercased doi: pmid}; DOIs that resolve to nothing are absent.
        """
        mapping: dict[str, str] = {}
        unique = [d for d in dict.fromkeys(d.strip() for d in dois if d and d.strip())]

        for i in range(0, len(unique), self.DOI_CHUNK):
            chunk = unique[i:i + self.DOI_CHUNK]
            # Quote each DOI: parentheses are grouping operators in Entrez query
            # syntax, and DOIs like 10.1016/S0140-6736(20)31288-5 contain them.
            term = " OR ".join(f'"{d}"[doi]' for d in chunk)

            self.limiter.wait()
            data = self.http.post_json(
                f"{ENTREZ_API}/esearch.fcgi",
                self._param_dict(db="pubmed", term=term, retmax=str(len(chunk) * 2)),
            )
            if "__error__" in data:
                logger.debug("batched esearch failed (%s); falling back per DOI",
                             data["__error__"])
                for d in chunk:
                    pmid = self.pmid_from_doi(d)
                    if pmid:
                        mapping[d.lower()] = pmid
                continue

            ids = data.get("esearchresult", {}).get("idlist", []) or []
            for pmid, meta in self.batch_summaries(ids).items():
                doi = (meta.get("doi") or "").strip().lower()
                if doi:
                    mapping.setdefault(doi, pmid)

        return mapping

    def batch_summaries(self, pmids: list[str]) -> dict[str, dict[str, Any]]:
        """PMID -> metadata for many PMIDs, ~200 per request."""
        out: dict[str, dict[str, Any]] = {}
        unique = [p for p in dict.fromkeys(str(p).strip() for p in pmids if p and str(p).strip())]

        for i in range(0, len(unique), self.PMID_CHUNK):
            chunk = unique[i:i + self.PMID_CHUNK]
            self.limiter.wait()
            data = self.http.post_json(
                f"{ENTREZ_API}/esummary.fcgi",
                self._param_dict(db="pubmed", id=",".join(chunk)),
            )
            if "__error__" in data:
                logger.debug("batched esummary failed (%s); leaving chunk unresolved",
                             data["__error__"])
                continue
            result = data.get("result") or {}
            for pmid in result.get("uids", []) or []:
                record = result.get(pmid) or {}
                if record and not record.get("error"):
                    out[pmid] = self._summary_to_meta(pmid, record)
        return out

    @staticmethod
    def _summary_to_meta(pmid: str, record: dict[str, Any]) -> dict[str, Any]:
        doi = ""
        for aid in record.get("articleids", []) or []:
            if aid.get("idtype") == "doi":
                doi = aid.get("value", "")
                break
        authors = record.get("authors") or []
        pubdate = record.get("pubdate", "") or ""
        return {
            "pmid": pmid,
            "doi": doi,
            "title": record.get("title", ""),
            "first_author": authors[0].get("name", "") if authors else "",
            "all_authors": [a.get("name", "") for a in authors],
            "year": pubdate.split(" ")[0] if pubdate else "",
            "journal": record.get("fulljournalname", "") or record.get("source", ""),
            "volume": record.get("volume", ""),
            "issue": record.get("issue", ""),
            "pages": record.get("pages", ""),
        }

    def by_pmid(self, pmid: str) -> dict[str, Any]:
        """Reverse resolution: PMID -> canonical metadata (including its DOI)."""
        if not pmid:
            return {"__error__": "no_pmid"}
        self.limiter.wait()
        url = f"{ENTREZ_API}/esummary.fcgi?{self._params(db='pubmed', id=pmid)}"
        data = self.http.get_json(url)
        if "__error__" in data:
            return data
        record = (data.get("result") or {}).get(pmid) or {}
        if not record or record.get("error"):
            return {"__error__": "pmid_not_found"}
        return self._summary_to_meta(pmid, record)
