# DDB MCP Server

An MCP server and a CLI for the Deutsches Zeitungsportal, the newspaper collection of the Deutsche Digitale Bibliothek.

## Stack

- Python ≥3.12, uv, fastMCP ≥2.0.0, httpx ≥0.27.0

## Functions

- **A full-text search** over approximately 33.8M German newspaper pages, with the full Solr syntax
- **Highlighted snippets** that the search itself returns, with the matched terms in `{braces}`
- **Filters** for the date range, the newspaper title, the place, the language, the provider and the ZDB id
- **A facet listing** of the values that a filter can take, with page counts, over the corpus or over the results of one query
- **An OCR text download** for a page or a full issue, with a local cache
- **Pagination** up to 100 results for each page

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

`client.py` holds all the behaviour. `server.py` and `cli.py` are thin presentation layers over it, so the search semantics and the cache stay identical for each method of access.

## API Details

**Search API:** a plain Apache Solr core, with no authentication.

- Endpoint: `https://api.deutsche-digitale-bibliothek.de/search/index/newspaper-issues/select`
- Two document types share the index, `type:page` and `type:issue`. This client queries the pages only. The OCR is there, and so is the page number that a citation needs.
- Fields on a page document: `id`, `pagename`, `pagenumber`, `paper_title`, `provider`, `provider_ddb_id`, `zdb_id`, `publication_date`, `place_of_distribution`, `language`, `thumbnail`, `pagefulltext`, `preview_reference`, `plainpagefulltext`.
- `plainpagefulltext` carries the full OCR of the page, so the search and the full-text retrieval use the same endpoint. The client deliberately excludes it from `fl` on a search: at approximately 20KB for each page, it would return a megabyte to describe fifty results.
- `preview_reference` links to ALTO v3 XML with pixel coordinates for each word.

**Item metadata:** `https://api.deutsche-digitale-bibliothek.de/2/items/{ITEM_ID}` — the client does not use this endpoint, but the canonical record is there.

## Facets, and the Fields That Do Not Exist

The server exposes only the `select` handler. `schema/fields` and `admin/luke` both give HTTP 404, so there is no method to list the schema. But Solr rejects an undefined `facet.field` with an HTTP 400 that names it, and a batch of candidates in one facet request against a single-document query makes each probe free. That is how the tests established the field set below, and that is how to examine it again.

**The full schema, confirmed live.** A page carries `id`, `pagename`, `pagenumber`, `paper_title`, `provider`, `provider_ddb_id`, `zdb_id`, `publication_date`, `place_of_distribution`, `language`, `type`, `thumbnail`, `pagefulltext`, `plainpagefulltext`, `preview_reference`. An issue carries the same metadata without the page-level fields and the fulltext fields, plus `license` and `ns_disclaimer_required`.

**There is nothing else.** The tests probed each credible name for the facets that a newspaper portal can offer, and Solr rejected each one as an undefined field: `publication_frequency`, `frequency`, `region`, `state`, `country`, `place_of_publication`, `publication_place`, `subject`, `keywords`, `topic`, `format`, `medium`, `category`, `sector`, `genre`, `collection`, `coverage`, `contributor`, `creator`, `publisher`, `editor`, `year`, `issue_number`, `edition`, `supplement`, `issn`, `paper_id`, `rights`. The web interface of the portal offers the year, the title, the place, the provider and the language, and nothing more, which agrees. **Do not add `--subject`, `--format` or `--contributor` here to match the sibling sources. The concepts have no field to attach to.**

**Two fields exist, and the client still does not show them.**

- `license` is populated on **issue** documents only. `type:page AND license:*` gives 0 of 33.8M pages, and `type:issue AND license:*` gives all 5.49M issues. This client searches the pages, so a `--license` flag would accept a value that looks correct and would quietly give nothing. That is the exact risk that the rest of this file is about.
- `provider_ddb_id` filters the pages correctly (1,564,725 for the Halle provider, which agrees with the count for the full name of the provider). But it says nothing that `--provider` does not say, and `ddb facets provider` now supplies the name exactly.

`pagenumber` is also filterable — `pagenumber:1` selects 4.76M pages — but the tests did not confirm that "page 1 of the digitised unit" means "front page of the issue" for each provider. Thus the client does not offer it.

**String fields against analysed text.** This difference controls the full facet feature:

| Field | Kind | A partial value |
|---|---|---|
| `place_of_distribution`, `provider`, `language`, `zdb_id` | string, matched whole | **0 results, no error** |
| `paper_title` | text, German stemming | matches (`"Nachrichten"` → 3.17M) |

`place_of_distribution:"Halle"` gives 0 where `"Halle (Saale)"` gives 1,130,771. `provider:"Bayerische"` gives 0 where `"Bayerische Staatsbibliothek"` gives 8,278,045. Nothing separates an incorrect value from an absent one, and that is why `facets` exists.

The same difference makes `paper_title` unusable as a facet field: a facet over it gives German-stemmed tokens (`und`, `zeitung`, `fuer`, `nachricht`), not titles. Thus `FACET_FIELDS` maps the `title` facet onto `zdb_id`, which is one term for each paper, and a second grouped request attaches a readable `paper_title`. A facet over four fields across the full corpus costs approximately 1.9s on the server. Over one query it costs approximately 270ms.

**Viewer URL:** `https://www.deutsche-digitale-bibliothek.de/newspaper/item/{ITEM_ID}?issuepage={n}` — for a human to open, never for a script to fetch.

## Identifiers

A page id is the item id of the issue, then a hyphen, then the page name: `QH5LZ...O6JI-fulltext_5_DDB_FULLTEXT`. The client derives the item id when it removes `-{pagename}` with the `pagename` field. It does not divide on the first hyphen, which operates only by chance and would fail on a page name that contains one.

The page names are not uniform across the providers. `fulltext_5_DDB_FULLTEXT`, `ALTO1488900_DDB_FULLTEXT`, `FILE_0008_DDB_FULLTEXT` and `uuid-...-_DDB_FULLTEXT` all occur. Do not parse them.

## Result Ordering

Relevance, and only relevance. **This client deliberately breaks the shared `sort` vocabulary** (`relevance`/`date_asc`/`date_desc`) that the sibling clients offer, and it exposes no `sort` parameter.

`publication_date` is a Solr `DateRangeField`. The server answers `sort=publication_date asc` with `"Sorting not supported on SpatialField: publication_date"`. A range *filter* against the same field operates correctly, so the field is still useful. It is only not sortable.

Thus the client could give a date order only if it reordered the documents that it already fetched. That was the first implementation, with a `partial_sort` flag and a printed warning, and it was incorrect. To reorder a page that relevance selected is a chronological order in name only, because the *selection* is still by relevance. A flag whose meaning quietly becomes weaker is worse than an absent flag: an agent that reads `--sort date_asc` will believe that it received a chronology. Chronology here means a limited date range collected fully with `--pages all`.

## Rate Limiting

A cross-process limiter (`ratelimit.py`) paces the requests. The default is **1s**, and `DDB_MIN_REQUEST_INTERVAL` changes it. An in-process semaphore also limits the concurrency.

DDB publishes no rate limit for the search index. It sets no `RateLimit` header, no `X-RateLimit-*` header and no `Retry-After` header, and it serves no `robots.txt` on the API host (HTTP 404). The tests observed no limit across approximately eighty requests, which included a deliberate burst.

**1s is a careful choice, not a measured maximum.** Nothing here establishes where the real limit is. It establishes only that ordinary use does not approach it. The risk is asymmetric: to go above an unpublished limit costs hours of access, and to pace the requests costs seconds.

## Caching

- **Cache:** the OCR text downloads. **Do not cache:** the search results.
- **Location:** `$XDG_CACHE_HOME/ddb-mcp/`, resolved by `paths.cache_dir()`; change it with `--cache-dir` or `DDB_CACHE_DIR`.

The cache must not depend on the working directory. The CLI has a global installation, and a person runs it from whichever project they are in.

## Known behaviours and risks

- **`hl.method=original` is necessary.** The default highlighter of this Solr gives an empty highlight block for each document on a phrase query — HTTP 200, a correct response, no snippets — which reads as "no matches in the text" and not as a failure. `hl.method=original` gives them correctly. `hl.usePhraseHighlighter=false` also operates, but it highlights the terms independently of the phrase. Do not remove this parameter. The failure that it prevents gives no message. (A note for a person who tests this again: this is *not* a function of `rows`, which was the first hypothesis. It occurs at `rows=2`, and it does not occur at `rows=20` with the parameter set.)
- **The server cannot sort on `publication_date`.** It can only filter on it, which is why there is no `sort` parameter. See Result Ordering.
- **An incorrect value for an exact-match filter is identical to an absent one.** `--place Halle` prints `0 pages matched`, not an error. See the facet section above. `ddb facets` is the answer, not more guesses.
- **The `numFound` of a group is not a count on this index.** The index is sharded, and under distributed grouping the `numFound` of a group reports the shard that supplied the top document: one title read 150 there against a facet count of 404 for the same query. Thus `_resolve_zdb_titles` takes only the *title text* from the grouped response, and it takes each count from the facet block. The *order* of the groups comes from the score of the top document, not from the size of the group. That is a second reason not to build a "biggest titles" listing out of grouping: it would repeat the false-sort error in a new place.
- **The `paper_title` of a ZDB id is not a title that is accurate for a date.** The recorded string covers the full run of the paper, so a facet for 1900-1910 shows a Stuttgart daily with a subtitle that it received in the 1930s, and one id can cover several forms (a morning edition and an evening edition). `_resolve_zdb_titles` applies the query and the filters of the caller again, which does change the answer — one id labelled itself `... Vorabend-Blatt` with no filter and `... Morgen-Blatt` under a query — but it cannot make the label authoritative. The id is the exact value. The title is only a guide.
- **A Solr error arrives under two different statuses.** A query with an incorrect form is HTTP 400 with a JSON error block. A query that times out on the server is HTTP 200 that carries the same shape. `_get_json` reads the error block *before* `raise_for_status`, so both give one clear message and not a traceback from httpx.
- **The `www` host serves an anti-bot challenge with HTTP 200.** Only `www` has this wall. `api.` is clean and needs no key. The Anubis proof-of-work on `www` has a difficulty that is not worth a solution (measured at approximately 18 days on one thread), which is acceptable because nothing here needs that host. The content-type check in `_get_json` would catch a redirect that ever sent us there.
- **The OCR does not join hyphenation across a line break**, so a phrase search quietly misses each occurrence that divided inside a word. This is a property of the data. The client cannot correct it, and it belongs in any advice about why a name looks rare.
- **German stemming is active on the fulltext field**, so a bare term matches its full stem class, and a count for a single term is a count for the stem.
- **An empty result set is one empty page**, `total_pages: 1`, normalised so that each caller behaves the same here as for every other source.
- **A search result with no id raises an error.** To drop it would make the result list smaller while the reported total still counted it. That is a quiet under-report, which is the worst failure for a tool whose value is completeness.
- **No API key is necessary today**, but this can be a gate that nobody enforces and not a policy. The client sends `DDB_API_KEY` when it is set, so the client continues to operate if DDB enforces the gate. The keys are free and carry no affiliation requirement: the documentation of DDB states that any registered user can generate one from the *Meine DDB* area of their account, at <https://www.deutsche-digitale-bibliothek.de/user/apikey>, and there is no paid level. The registration pages are on the Anubis-walled `www` host, so we have only read about that procedure. We have not walked through it.
