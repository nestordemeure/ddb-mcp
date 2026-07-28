"""Command-line interface for the Deutsches Zeitungsportal.

A thin wrapper over :class:`DDBClient` that formats results for reading in a
terminal or by an agent driving the command through a shell. Output is compact
and greppable by default; ``--json`` emits the raw client structures.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import Any

import httpx

from .client import DEFAULT_ROWS, MAX_ROWS, DDBClient
from .paths import cache_dir

PROGRAM_NAME = "ddb"
API_KEY_ENV_VAR = "DDB_API_KEY"


class PageRange:
    """A 1-indexed, inclusive range of result pages. ``last is None`` means all."""

    def __init__(self, first: int, last: int | None) -> None:
        self.first = first
        self.last = last

    def contains(self, page: int) -> bool:
        return page >= self.first and (self.last is None or page <= self.last)

    def __str__(self) -> str:
        if self.last is None:
            return f"{self.first}-all"
        if self.last == self.first:
            return str(self.first)
        return f"{self.first}-{self.last}"


def parse_page_range(value: str) -> PageRange:
    """Parse a ``--pages`` value: ``3``, ``2-5`` or ``all``."""
    text = value.strip().lower()

    if text == "all":
        return PageRange(1, None)

    try:
        if "-" in text:
            first_text, _, last_text = text.partition("-")
            first, last = int(first_text), int(last_text)
        else:
            first = last = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"expected a page number, a range like 2-5, or 'all'; got {value!r}"
        ) from None

    if first < 1:
        raise argparse.ArgumentTypeError(f"page numbers start at 1; got {value!r}")
    if last < first:
        raise argparse.ArgumentTypeError(f"page range runs backwards: {value!r}")

    return PageRange(first, last)


def build_client(args: argparse.Namespace) -> DDBClient:
    return DDBClient(
        cache_dir=cache_dir(getattr(args, "cache_dir", None)),
        api_key=os.environ.get(API_KEY_ENV_VAR),
    )


def format_document(position: int, document: dict[str, Any]) -> str:
    """Render one search result: metadata, viewer URL, then its snippets."""
    lines = []

    page_number = document.get("page_number")
    page_label = f"p.{page_number}" if page_number is not None else "p.?"
    lines.append(
        f"[{position}] {document['identifier']}  ({document.get('date') or 'n.d.'}, {page_label})"
    )

    title = document.get("title") or "Untitled"
    if places := document.get("places"):
        title += f" — {', '.join(places)}"
    lines.append(f"    {title}")

    if provider := document.get("provider"):
        lines.append(f"    {provider}")

    lines.append(f"    {document['url']}")

    for snippet in document.get("snippets") or []:
        lines.append(f"    · {snippet}")

    return "\n".join(lines)


async def run_search(args: argparse.Namespace) -> int:
    client = build_client(args)
    try:
        page_range = args.pages
        current = page_range.first
        printed_header = False
        total_pages = None

        while page_range.contains(current):
            result = await client.search(
                query=args.query,
                page=current,
                rows=args.rows,
                from_year=args.from_year,
                to_year=args.to_year,
                paper_title=args.title,
                place=args.place,
                language=args.language,
                provider=args.provider,
                zdb_id=args.zdb_id,
                snippets=0 if args.no_snippets else args.snippets,
                snippet_size=args.snippet_size,
            )
            total_pages = result["total_pages"]

            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                if not printed_header:
                    print(
                        f"{result['total_results']} pages matched "
                        f"({total_pages} result page(s) of {args.rows}); "
                        f"showing {page_range}"
                    )
                    printed_header = True

                offset = (current - 1) * args.rows
                print(f"\n--- result page {current} ---")
                for index, document in enumerate(result["documents"], start=offset + 1):
                    print(format_document(index, document))

            if not result["documents"]:
                break
            current += 1
            if total_pages is not None and current > total_pages:
                break

        return 0
    finally:
        await client.close()


async def run_snippets(args: argparse.Namespace) -> int:
    """Show where a query appears within one page or one issue."""
    client = build_client(args)
    try:
        identifier = args.identifier.strip()
        result = await client.search(
            query=args.query,
            page=1,
            rows=args.rows,
            snippets=args.snippets,
            snippet_size=args.snippet_size,
            restrict_to=identifier,
        )

        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0

        documents = result["documents"]
        if not documents:
            print(f"No occurrences of {args.query!r} found in {identifier}")
            return 0

        print(f"{result['total_results']} matching page(s) in {identifier}")
        for index, document in enumerate(documents, start=1):
            print(format_document(index, document))
        return 0
    finally:
        await client.close()


async def run_get(args: argparse.Namespace) -> int:
    client = build_client(args)
    try:
        path = await client.get_page_text(args.identifier, refresh=args.refresh)
        print(path)
        return 0
    finally:
        await client.close()


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--cache-dir", help="Override the cache directory")
    parser.add_argument("--json", action="store_true", help="Emit raw JSON")


def add_snippet_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--snippets",
        type=int,
        default=3,
        help="Highlighted excerpts per page (default: 3)",
    )
    parser.add_argument(
        "--snippet-size",
        type=int,
        default=200,
        help="Approximate characters per excerpt (default: 200)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROGRAM_NAME,
        description=(
            "Search the Deutsches Zeitungsportal (Deutsche Digitale Bibliothek): "
            "German newspapers, ~33.8M pages, strongest 1850-1949."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    search = subparsers.add_parser(
        "search",
        help="Search newspaper pages; returns metadata and highlighted snippets",
    )
    search.add_argument("query", help="Solr query over page fulltext")
    search.add_argument(
        "--pages",
        type=parse_page_range,
        default=parse_page_range("1"),
        help="Result pages to fetch: N, N-M, or all (default: 1)",
    )
    search.add_argument(
        "--rows",
        type=int,
        default=DEFAULT_ROWS,
        help=f"Results per page, max {MAX_ROWS} (default: {DEFAULT_ROWS})",
    )
    search.add_argument("--from-year", type=int, help="Earliest publication year")
    search.add_argument("--to-year", type=int, help="Latest publication year")
    search.add_argument("--title", help="Restrict to a newspaper title")
    search.add_argument("--place", help="Restrict to a place of distribution")
    search.add_argument("--language", help="Language code, ISO 639-2 (e.g. ger)")
    search.add_argument("--provider", help="Restrict to a holding institution")
    search.add_argument("--zdb-id", help="Restrict to a ZDB title identifier")
    search.add_argument(
        "--no-snippets",
        action="store_true",
        help="Omit highlighted excerpts, for a compact listing",
    )
    add_snippet_arguments(search)
    add_common_arguments(search)
    search.set_defaults(func=run_search)

    snippets = subparsers.add_parser(
        "snippets",
        help="Show where a query appears inside one page or issue",
    )
    snippets.add_argument("identifier", help="A page id or an issue item id")
    snippets.add_argument("query", help="Solr query over page fulltext")
    snippets.add_argument(
        "--rows",
        type=int,
        default=MAX_ROWS,
        help=f"Maximum pages to report (default: {MAX_ROWS})",
    )
    add_snippet_arguments(snippets)
    add_common_arguments(snippets)
    snippets.set_defaults(func=run_snippets)

    get = subparsers.add_parser(
        "get",
        help="Download OCR text for a page or a whole issue; prints the cached path",
    )
    get.add_argument("identifier", help="A page id or an issue item id")
    get.add_argument(
        "--refresh", action="store_true", help="Ignore any cached copy and fetch again"
    )
    add_common_arguments(get)
    get.set_defaults(func=run_get)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    try:
        sys.exit(asyncio.run(args.func(args)))
    except KeyboardInterrupt:
        sys.exit(130)
    except (RuntimeError, ValueError, httpx.HTTPError) as error:
        print(f"{PROGRAM_NAME}: {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
