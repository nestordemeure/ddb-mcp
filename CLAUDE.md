# DDB MCP Server

MCP server and CLI for the Deutsches Zeitungsportal, the newspaper collection of the Deutsche Digitale Bibliothek.

## Stack

- Python ≥3.12, uv, fastMCP ≥2.0.0, httpx ≥0.27.0

## Functionality

- **Fulltext search** over ~33.8M German newspaper pages, with the full Solr syntax
- **Highlighted snippets** returned by the search itself, matched terms in `{braces}`
- **Filters** for date range, newspaper title, place, language, provider and ZDB id
- **OCR text download** for a page or a whole issue, with local caching
- **Pagination** up to 100 results per page

## Structure

```
ddb-mcp/
├── .claude/skills/ddb-search/   # Skill documenting the CLI
├── src/ddb_mcp/
│   ├── __init__.py
│   ├── client.py           # API client + caching
│   ├── cli.py              # `ddb` command-line interface
│   ├── paths.py            # Cache location resolution
│   ├── ratelimit.py        # Cross-process request pacing
│   ├── server.py           # FastMCP tools
│   └── install.py          # MCP server installer
├── pyproject.toml
└── CLAUDE.md               # This file
```

`client.py` holds all the behaviour; `server.py` and `cli.py` are thin presentation layers over it, so search semantics and caching stay identical no matter how it is called.

## API Details

**Search API:** a plain Apache Solr core, unauthenticated.

- Endpoint: `https://api.deutsche-digitale-bibliothek.de/search/index/newspaper-issues/select`
- Two document types share the index, `type:page` and `type:issue`. This client queries pages only — the OCR lives there, and so does the page number a citation needs.
- Fields on a page document: `id`, `pagename`, `pagenumber`, `paper_title`, `provider`, `provider_ddb_id`, `zdb_id`, `publication_date`, `place_of_distribution`, `language`, `thumbnail`, `pagefulltext`, `preview_reference`, `plainpagefulltext`.
- `plainpagefulltext` carries the page's entire OCR, so search and full-text retrieval are the same endpoint. It is deliberately excluded from `fl` on searches: at ~20KB per page it would return a megabyte to describe fifty results.
- `preview_reference` links to ALTO v3 XML with per-word pixel coordinates.

**Item metadata:** `https://api.deutsche-digitale-bibliothek.de/2/items/{ITEM_ID}` — not used by the client, but it is where the canonical record lives.

**Viewer URL:** `https://www.deutsche-digitale-bibliothek.de/newspaper/item/{ITEM_ID}?issuepage={n}` — for a human to open, never to fetch.

## Identifiers

A page id is the issue's item id, a hyphen, then the page name: `QH5LZ...O6JI-fulltext_5_DDB_FULLTEXT`. The client derives the item id by stripping `-{pagename}` using the `pagename` field rather than splitting on the first hyphen, which only happens to work and would break on a page name containing one.

Page names are not uniform across providers — `fulltext_5_DDB_FULLTEXT`, `ALTO1488900_DDB_FULLTEXT`, `FILE_0008_DDB_FULLTEXT` and `uuid-...-_DDB_FULLTEXT` all occur. Do not parse them.

## Result Ordering

Relevance, and only relevance. **This client deliberately breaks the shared `sort` vocabulary** (`relevance`/`date_asc`/`date_desc`) that the sibling clients offer, and exposes no `sort` parameter at all.

`publication_date` is a Solr `DateRangeField`; the server answers `sort=publication_date asc` with `"Sorting not supported on SpatialField: publication_date"`. Range *filtering* against the same field works fine, so the field is still useful — just not sortable.

Date ordering could therefore only have been faked by reordering the documents already fetched. That was the first implementation, with a `partial_sort` flag and a printed warning, and it was wrong: reordering a relevance-selected page is a chronology in name only, because the *selection* is still by relevance. A flag whose meaning silently degrades is worse than an absent one — an agent reading `--sort date_asc` will believe it got a chronology. Chronology here means a bounded date range swept whole with `--pages all`.

## Rate Limiting

Cross-process limiter (`ratelimit.py`), default **1s**, overridable with `DDB_MIN_REQUEST_INTERVAL`, plus an in-process semaphore limiting concurrency.

DDB publishes no rate limit for the search index, sets no `RateLimit`/`X-RateLimit-*`/`Retry-After` headers, and serves no `robots.txt` on the API host (404). None was observed across roughly eighty requests including a deliberate burst.

**1s is a conservative choice, not a measured ceiling.** Nothing here establishes where the real limit is — only that ordinary use does not approach it. The downside is asymmetric: exceeding an unpublished limit costs hours of access, while pacing costs seconds.

## Caching

- **Cache:** OCR text downloads. **Don't cache:** search results.
- **Location:** `$XDG_CACHE_HOME/ddb-mcp/`, resolved by `paths.cache_dir()`; override with `--cache-dir` or `DDB_CACHE_DIR`.

The cache must not depend on the working directory: the CLI is installed globally and run from whatever project the researcher is in.

## Gotchas

- **`hl.method=original` is load-bearing.** This Solr's default highlighter returns an empty highlight block for every document on a phrase query — HTTP 200, well-formed response, no snippets — which reads as "no matches in the text" rather than as a failure. `hl.method=original` returns them correctly. `hl.usePhraseHighlighter=false` also works but highlights terms independently of the phrase. Do not remove this parameter; the failure it prevents is silent. (Note for anyone re-testing: this is *not* a function of `rows`, which was the initial hypothesis. It reproduces at `rows=2` and does not reproduce at `rows=20` with the parameter set.)
- **`publication_date` cannot be sorted on**, only filtered — which is why there is no `sort` parameter. See Result Ordering.
- **A Solr error arrives under two different statuses.** A malformed query is HTTP 400 with a JSON error block; a query that times out server-side is HTTP 200 carrying the same shape. `_get_json` reads the error block *before* `raise_for_status`, so both surface as one clear message instead of an httpx traceback.
- **The `www` host serves an anti-bot challenge with HTTP 200.** Only `www` is walled; `api.` is clean and needs no key. The Anubis proof-of-work on `www` is set to a difficulty that is not worth solving (measured at roughly 18 days single-threaded), which is fine because nothing here needs that host. The content-type check in `_get_json` is what would catch a redirect that ever routed us there.
- **Hyphenation across line breaks is not rejoined in the OCR**, so phrase searches silently miss occurrences that broke mid-word. This is a property of the data, not something the client can fix, and it belongs in any advice about why a name looks under-represented.
- **German stemming is active on the fulltext field**, so a bare term matches its whole stem class and single-term counts are stem counts.
- **An empty result set is one empty page**, `total_pages: 1`, normalised so callers behave the same here as for any other source.
- **A search result without an id raises.** Dropping it would shrink the result list while the reported total still counted it — a silent under-report, which is the worst failure mode for a tool whose value rests on exhaustivity.
- **No API key is needed today**, but that may be an unenforced gate rather than policy. `DDB_API_KEY` is sent when set, so the client keeps working if enforcement is switched on. Keys are free and carry no affiliation requirement: DDB's documentation states that any registered user can generate one from the *Meine DDB* area of their account, and there is no paid tier. The signup pages are on the Anubis-walled `www` host, so that flow has only been read about, not walked through.
