"""Deutsches Zeitungsportal (DDB) client: Solr search, snippets and page OCR.

The newspaper index is a plain Apache Solr core exposed without authentication.
That shapes the whole client: queries are Solr queries, filters are ``fq``
clauses, and - unusually for this project - a page's entire OCR text is a field
on the search document rather than a separate download. Search and snippets are
therefore one request, not two.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

import httpx

from .paths import cache_dir as default_cache_dir
from .ratelimit import CrossProcessRateLimiter, configured_interval

USER_AGENT = "ddb-mcp/0.1.0 (historical research tool)"

# The field holding a page's OCR. `pagefulltext` also exists and carries markup;
# the `plain` variant is what is worth searching and reading.
FULLTEXT_FIELD = "plainpagefulltext"

# Metadata requested for every hit. `plainpagefulltext` is deliberately absent:
# it runs to 20KB per page, and asking for it on a 50-row search would return a
# megabyte to describe results the caller has not yet decided to read.
SUMMARY_FIELDS = (
    "id",
    "pagename",
    "pagenumber",
    "paper_title",
    "publication_date",
    "place_of_distribution",
    "provider",
    "zdb_id",
    "language",
    "preview_reference",
    "score",
)

# Result ordering is relevance, and only relevance.
#
# The sibling clients share a `sort` vocabulary of relevance/date_asc/date_desc.
# This one deliberately does not offer it. `publication_date` is a Solr
# DateRangeField and the server refuses to sort on it ("Sorting not supported on
# SpatialField"), so date ordering could only ever be faked by reordering the
# handful of documents already fetched - which looks like a chronology while
# being no such thing, since the *selection* would still be by relevance.
# Offering a flag that quietly means something weaker than its name is worse
# than not offering it: chronological work here means bounding the query with a
# date range and sweeping it whole.

# Braces are the house convention for "this is the token that matched", so the
# highlighter is asked to emit them directly rather than <em> we would strip.
HIGHLIGHT_PRE = "{"
HIGHLIGHT_POST = "}"

DEFAULT_ROWS = 20
MAX_ROWS = 100

# A human-readable page in the DDB newspaper viewer.
VIEWER_URL = "https://www.deutsche-digitale-bibliothek.de/newspaper/item/{item_id}?issuepage={page}"


class DDBClient:
    """Client for the Deutsches Zeitungsportal newspaper index."""

    SEARCH_URL = "https://api.deutsche-digitale-bibliothek.de/search/index/newspaper-issues/select"
    ITEM_URL = "https://api.deutsche-digitale-bibliothek.de/2/items/{item_id}"

    def __init__(
        self,
        cache_dir: Path | None = None,
        max_concurrent_requests: int = 1,
        min_request_interval: float | None = None,
        api_key: str | None = None,
    ) -> None:
        """Initialise the client.

        Args:
            cache_dir: Directory for cached page text
            max_concurrent_requests: Maximum concurrent API requests
            min_request_interval: Seconds between requests; defaults to the
                configured interval
            api_key: Optional DDB API key. The search index currently answers
                without one, but that may be an unenforced gate rather than
                policy, so a key is sent when available.
        """
        self.cache_dir = Path(cache_dir) if cache_dir is not None else default_cache_dir()
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        headers = {"User-Agent": USER_AGENT}
        if api_key:
            headers["Authorization"] = f"OAuth oauth_consumer_key=\"{api_key}\""

        # Solr answers most queries in tens of milliseconds, but a faceted sweep
        # over 33M documents can take seconds, and an unbounded range query on
        # the fulltext field times out server-side. A short client timeout would
        # turn a slow-but-successful query into a spurious failure.
        self.client = httpx.AsyncClient(timeout=120.0, follow_redirects=True, headers=headers)
        self._request_semaphore = asyncio.Semaphore(max_concurrent_requests)
        self._rate_limiter = CrossProcessRateLimiter(
            state_file=self.cache_dir / ".rate-limit",
            min_interval=(
                min_request_interval
                if min_request_interval is not None
                else configured_interval()
            ),
        )

    async def close(self) -> None:
        await self.client.aclose()

    async def search(
        self,
        query: str,
        page: int = 1,
        rows: int = DEFAULT_ROWS,
        from_year: int | None = None,
        to_year: int | None = None,
        paper_title: str | None = None,
        place: str | None = None,
        language: str | None = None,
        provider: str | None = None,
        zdb_id: str | None = None,
        snippets: int = 3,
        snippet_size: int = 200,
        restrict_to: str | None = None,
    ) -> dict[str, Any]:
        """Search newspaper pages.

        ``restrict_to`` narrows the search to a single page id or to every page
        of one issue, which is how `snippets` locates a term inside a document
        already in hand.

        Returns a dict with ``page``, ``total_results``, ``total_pages`` and
        ``documents``. Results come back by relevance; see the note on ordering
        at the top of this module. Each document carries its metadata,
        a viewer URL, and the highlighted snippets showing where the query
        matched - DDB returns those in the search response itself, so no second
        request is needed to judge a hit.
        """
        if page < 1:
            raise ValueError(f"Page numbers start at 1; got {page}")
        rows = max(1, min(rows, MAX_ROWS))

        params: list[tuple[str, str]] = [
            ("q", self._build_query(query, restrict_to)),
            ("rows", str(rows)),
            ("start", str((page - 1) * rows)),
            ("fl", ",".join(SUMMARY_FIELDS)),
            ("wt", "json"),
        ]
        for clause in self._build_filters(
            from_year=from_year,
            to_year=to_year,
            paper_title=paper_title,
            place=place,
            language=language,
            provider=provider,
            zdb_id=zdb_id,
        ):
            params.append(("fq", clause))

        if snippets > 0:
            params.extend(self._highlight_params(snippets, snippet_size))

        payload = await self._get_json(params)
        response = payload.get("response")
        if response is None or "numFound" not in response:
            raise RuntimeError(
                "DDB returned a response with no result block; the search index "
                "may have changed shape."
            )

        total_results = int(response["numFound"])
        highlighting = payload.get("highlighting") or {}
        documents = [
            self._parse_document(doc, highlighting) for doc in response.get("docs", [])
        ]

        # An empty result set is one empty page, not zero pages, so callers
        # looping over pages behave the same here as for any other source.
        total_pages = max(1, (total_results + rows - 1) // rows)

        return {
            "page": page,
            "total_results": total_results,
            "total_pages": total_pages,
            "documents": documents,
        }

    async def get_page_text(self, identifier: str, refresh: bool = False) -> str:
        """Download the OCR text of a page, or of every page of an issue.

        Args:
            identifier: A page id (``ITEM-pagename``) or a bare issue item id
            refresh: Ignore any cached copy and fetch again

        Returns:
            Path to the cached text file
        """
        identifier = identifier.strip()
        if not identifier:
            raise ValueError("An identifier is required")

        cache_file = self.cache_dir / f"{self._cache_name(identifier)}.txt"
        if cache_file.exists() and not refresh:
            return str(cache_file.resolve())

        params: list[tuple[str, str]] = [
            ("q", self._identifier_clause(identifier)),
            ("rows", str(MAX_ROWS)),
            ("fl", f"id,pagenumber,paper_title,publication_date,{FULLTEXT_FIELD}"),
            ("sort", "id asc"),
            ("wt", "json"),
        ]
        payload = await self._get_json(params)
        docs = (payload.get("response") or {}).get("docs") or []

        if not docs:
            raise RuntimeError(
                f"DDB holds no page text for {identifier!r}. Check the identifier: "
                "a page id looks like ITEMID-pagename, an issue id like ITEMID."
            )

        docs.sort(key=lambda doc: doc.get("pagenumber") or 0)
        sections = []
        for doc in docs:
            text = self._first_value(doc.get(FULLTEXT_FIELD)) or ""
            if not text.strip():
                continue
            header = f"=== {doc.get('paper_title') or 'Unknown title'} — page {doc.get('pagenumber')} ({doc.get('id')}) ==="
            sections.append(f"{header}\n{text.strip()}")

        if not sections:
            raise RuntimeError(
                f"DDB returned pages for {identifier!r} but none carried OCR text. "
                "The scan is probably image-only; nothing has been cached."
            )

        cache_file.write_text("\n\n".join(sections), encoding="utf-8")
        return str(cache_file.resolve())

    def _build_query(self, query: str, restrict_to: str | None = None) -> str:
        """Wrap a user query into a Solr query over page fulltext.

        The user's text is passed through untouched so that the whole Solr
        syntax - phrases, boolean operators, wildcards, ``~`` fuzziness and
        proximity - remains available.
        """
        parts = ["type:page"]

        text = (query or "").strip()
        if text:
            parts.append(f"{FULLTEXT_FIELD}:({text})")

        if restrict_to and restrict_to.strip():
            parts.append(self._identifier_clause(restrict_to.strip()))

        return " AND ".join(parts)

    def _identifier_clause(self, identifier: str) -> str:
        """A clause matching one page, or every page of one issue."""
        if self._looks_like_page_id(identifier):
            return f'id:"{self._escape_phrase(identifier)}"'
        # Page ids are the item id followed by "-" and the page name, so a
        # prefix query collects every page of one issue.
        return f"id:{self._escape_term(identifier)}*"

    def _build_filters(
        self,
        from_year: int | None,
        to_year: int | None,
        paper_title: str | None,
        place: str | None,
        language: str | None,
        provider: str | None,
        zdb_id: str | None,
    ) -> list[str]:
        """Build the `fq` clauses for the optional filters."""
        clauses: list[str] = []

        if from_year is not None or to_year is not None:
            start = f"{from_year:04d}-01-01T00:00:00Z" if from_year is not None else "*"
            end = f"{to_year:04d}-12-31T23:59:59Z" if to_year is not None else "*"
            clauses.append(f"publication_date:[{start} TO {end}]")

        for field, value in (
            ("paper_title", paper_title),
            ("place_of_distribution", place),
            ("provider", provider),
        ):
            if value and value.strip():
                clauses.append(f'{field}:"{self._escape_phrase(value.strip())}"')

        if language and language.strip():
            clauses.append(f"language:{self._escape_term(language.strip())}")
        if zdb_id and zdb_id.strip():
            clauses.append(f'zdb_id:"{self._escape_phrase(zdb_id.strip())}"')

        return clauses

    @staticmethod
    def _highlight_params(snippets: int, snippet_size: int) -> list[tuple[str, str]]:
        """Highlighting parameters, including the one that makes it work at all.

        `hl.method=original` is not a preference. This Solr's default highlighter
        returns an empty block for every document on a phrase query - HTTP 200,
        a well-formed response, and no snippets - which reads as "the terms are
        not there" rather than as a failure. The original highlighter returns
        them correctly. Do not drop this parameter.
        """
        return [
            ("hl", "true"),
            ("hl.fl", FULLTEXT_FIELD),
            ("hl.method", "original"),
            ("hl.snippets", str(snippets)),
            ("hl.fragsize", str(snippet_size)),
            ("hl.simple.pre", HIGHLIGHT_PRE),
            ("hl.simple.post", HIGHLIGHT_POST),
        ]

    def _parse_document(
        self, doc: dict[str, Any], highlighting: dict[str, Any]
    ) -> dict[str, Any]:
        """Turn one Solr document into the shape the CLI and server present."""
        try:
            identifier = doc["id"]
        except KeyError as error:
            # Dropping the record instead would shrink the result list while the
            # reported total still counted it - a search that silently
            # under-reports. For a tool whose value rests on exhaustivity, a
            # loud failure beats a quiet omission.
            raise RuntimeError(f"A DDB search result carried no id: {doc!r}") from error

        item_id = self._item_id(identifier, doc.get("pagename"))
        page_number = doc.get("pagenumber")
        raw_date = self._first_value(doc.get("publication_date"))

        highlights = (highlighting.get(identifier) or {}).get(FULLTEXT_FIELD) or []

        return {
            "identifier": identifier,
            "item_id": item_id,
            "page_number": page_number,
            "title": self._first_value(doc.get("paper_title")) or "Untitled",
            "date": raw_date[:10] if raw_date else None,
            "places": self._as_list(doc.get("place_of_distribution")),
            "provider": self._first_value(doc.get("provider")),
            "zdb_id": self._first_value(doc.get("zdb_id")),
            "languages": self._as_list(doc.get("language")),
            "alto_url": self._first_value(doc.get("preview_reference")),
            "url": VIEWER_URL.format(item_id=item_id, page=page_number or 1),
            "snippets": [self._clean_snippet(text) for text in highlights],
        }

    async def _get_json(self, params: list[tuple[str, str]]) -> dict[str, Any]:
        """Issue a paced request and return the parsed JSON body."""
        response = await self._rate_limited_get(self.SEARCH_URL, params=params)

        if response.status_code == 429:
            raise RuntimeError(
                "DDB rate limited the request (HTTP 429). Stop querying for now, "
                "and consider raising DDB_MIN_REQUEST_INTERVAL."
            )

        # The API host serves JSON; the www host serves an anti-bot challenge
        # with HTTP 200. If a redirect or a future change ever routes us there,
        # the body would parse as neither, so say so plainly.
        content_type = response.headers.get("content-type", "")
        if "json" not in content_type.lower():
            response.raise_for_status()
            raise RuntimeError(
                f"DDB returned {content_type or 'an unknown content type'} rather than "
                "JSON. If the body is an anti-bot page, the request reached the www "
                "host instead of the API host."
            )

        payload = response.json()

        # Solr reports a rejected query as an error block, and the status that
        # carries it varies: a malformed query is HTTP 400, while a query that
        # times out server-side is HTTP 200 with the same shape. Reading the
        # block before raising for status turns both into one clear message
        # instead of an httpx traceback.
        if "error" in payload:
            error = payload["error"]
            message = error.get("msg") if isinstance(error, dict) else str(error)
            raise RuntimeError(f"DDB rejected the query: {message}")

        response.raise_for_status()
        return payload

    async def _rate_limited_get(self, url: str, **kwargs: Any) -> httpx.Response:
        """Issue a GET honouring concurrency and cross-process pacing."""
        async with self._request_semaphore:
            await self._rate_limiter.acquire()
            return await self.client.get(url, **kwargs)

    @staticmethod
    def _item_id(identifier: str, pagename: str | None) -> str:
        """Derive the issue's item id from a page id.

        A page id is the item id, a hyphen, then the page name. Stripping the
        page name is exact; splitting on the first hyphen only happens to work,
        and would break on any page name that contains one.
        """
        if pagename and identifier.endswith(f"-{pagename}"):
            return identifier[: -(len(pagename) + 1)]
        return identifier.split("-", 1)[0]

    @staticmethod
    def _looks_like_page_id(identifier: str) -> bool:
        """Whether an identifier names a page rather than a whole issue."""
        return "-" in identifier

    def _cache_name(self, identifier: str) -> str:
        """A filesystem-safe name for a cached document."""
        return re.sub(r"[^A-Za-z0-9_.-]", "_", identifier)

    @staticmethod
    def _escape_phrase(value: str) -> str:
        """Escape a value destined for a quoted Solr phrase."""
        return value.replace("\\", "\\\\").replace('"', '\\"')

    @staticmethod
    def _escape_term(value: str) -> str:
        """Escape a value destined for an unquoted Solr term."""
        return re.sub(r'([+\-!(){}\[\]^"~*?:\\/ ])', r"\\\1", value)

    @staticmethod
    def _clean_snippet(text: str) -> str:
        """Normalise whitespace in a highlighted fragment.

        The braces are produced by the highlighter itself, so nothing has to be
        rewritten here - but OCR fragments arrive with newlines and runs of
        spaces that make them unreadable in a terminal.
        """
        return " ".join(text.split())

    @staticmethod
    def _as_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    @staticmethod
    def _first_value(value: Any) -> str | None:
        if isinstance(value, list):
            return str(value[0]) if value else None
        return str(value) if value is not None else None
