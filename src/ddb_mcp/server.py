"""DDB MCP Server - FastMCP tools for the Deutsches Zeitungsportal."""

from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

try:
    from .client import DEFAULT_FACET_VALUES, DEFAULT_ROWS, DDBClient
    from .paths import cache_dir
except ImportError:  # direct execution
    from ddb_mcp.client import DEFAULT_FACET_VALUES, DEFAULT_ROWS, DDBClient
    from ddb_mcp.paths import cache_dir

mcp = FastMCP("DDB")

_client: DDBClient | None = None


def get_client() -> DDBClient:
    """Get or create the global DDB client."""
    global _client
    if _client is None:
        _client = DDBClient(cache_dir=cache_dir(), api_key=os.environ.get("DDB_API_KEY"))
    return _client


@mcp.tool()
async def search_ddb(
    query: str,
    page: int = 1,
    rows: int = DEFAULT_ROWS,
    from_year: int | None = None,
    to_year: int | None = None,
    paper_title: str | None = None,
    place: str | None = None,
    language: str | None = None,
) -> dict:
    """Search German newspaper pages in the Deutsches Zeitungsportal.

    Covers ~33.8M digitised pages, densest between 1850 and 1949. Results are
    individual newspaper *pages*, and each carries highlighted snippets showing
    where the query matched, with matched terms in {braces} - so a single search
    is usually enough to judge a hit without downloading anything.

    Args:
        query: Solr query over page OCR text. Supports:
            - Exact phrases: '"Bert Reese"'
            - Boolean operators: 'Hellseher AND Telepathie', 'A OR B', 'A NOT B'
            - Wildcards: 'Hellseh*'
            - Fuzziness for OCR damage: 'Hanussen~1'
            - Proximity: '"Hellseher Hanussen"~10'
        page: Result page number, 1-indexed
        rows: Results per page (max 100)
        from_year: Earliest publication year, inclusive
        to_year: Latest publication year, inclusive
        paper_title: Restrict to one newspaper title
        place: Restrict to a place of distribution
        language: Language code, ISO 639-2 (e.g. 'ger')

    Returns:
        total_results (a true count, not a ranking depth), total_pages, and the
        matching pages with their metadata, viewer URL and snippets. Results are
        ordered by relevance; DDB cannot order by date, so chronological work
        means bounding the query with from_year/to_year and sweeping it whole.
    """
    return await get_client().search(
        query=query,
        page=page,
        rows=rows,
        from_year=from_year,
        to_year=to_year,
        paper_title=paper_title,
        place=place,
        language=language,
    )


@mcp.tool()
async def list_ddb_facet_values(
    field: str,
    query: str = "",
    limit: int = DEFAULT_FACET_VALUES,
    from_year: int | None = None,
    to_year: int | None = None,
) -> dict:
    """List the values a search filter can take, with page counts.

    Use this before filtering, and to characterise a result set. `place` and
    `provider` are matched as whole strings, so place='Halle' returns zero pages
    while place='Halle (Saale)' returns 1.1M - this is how to find which form the
    index holds. Given a query, the counts describe that result set instead of
    the whole corpus, which answers "where did this term appear, and in which
    newspapers".

    Args:
        field: One of 'place', 'provider', 'language', 'title'. 'title' lists ZDB
            identifiers with one recorded title form each, because the title
            field is stemmed text and facets into word stems rather than titles.
        query: Optional Solr query over page OCR; omit for the whole corpus
        limit: Values to return (max 100)
        from_year: Earliest publication year, inclusive
        to_year: Latest publication year, inclusive

    Returns:
        total_results (pages matching the query, not the sum of the counts) and
        values, ordered by count. `place` and `language` are multi-valued per
        page, so their counts can sum to more than the total.
    """
    return await get_client().facet(
        field=field,
        query=query,
        limit=limit,
        from_year=from_year,
        to_year=to_year,
    )


@mcp.tool()
async def get_ddb_snippets(identifier: str, query: str) -> dict:
    """Find where a query appears inside one page or one whole issue.

    Args:
        identifier: A page id ('ITEMID-pagename') or an issue item id ('ITEMID')
        query: Solr query over page OCR text

    Returns:
        The matching pages, with snippets showing the terms in {braces}.
    """
    return await get_client().search(query=query, rows=100, restrict_to=identifier)


@mcp.tool()
async def download_ddb_text(identifier: str, refresh: bool = False) -> str:
    """Download the OCR text of a page, or of every page of an issue.

    Args:
        identifier: A page id ('ITEMID-pagename') or an issue item id ('ITEMID')
        refresh: Ignore any cached copy and fetch again

    Returns:
        Path to the cached text file. Files run to tens of kilobytes per page,
        so read slices of them rather than the whole thing.
    """
    return await get_client().get_page_text(identifier, refresh=refresh)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
