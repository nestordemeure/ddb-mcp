# DDB MCP Server

MCP server and CLI for the [Deutsches Zeitungsportal](https://www.deutsche-digitale-bibliothek.de/newspaper), the newspaper collection of the Deutsche Digitale Bibliothek (DDB). Search the full text of ~33.8 million digitised German newspaper pages, of which roughly 27.9 million fall between 1850 and 1949.

- **search**: full Solr syntax over page OCR — exact phrases, boolean operators, wildcards, fuzzy matching and proximity — with filters for date, title, place, language and holding institution. Every hit is an individual **page**, and comes with highlighted snippets showing where the query matched.
- **snippets**: locate a query inside one page or across every page of an issue you already have in hand.
- **get**: download the OCR text of a page or a whole issue, cached locally.

There are two ways to use it: an **MCP server** for clients that speak MCP, and a **`ddb` CLI** for agents driven through a shell. Both share one client, one cache and one set of behaviours. The CLI is what the bundled `ddb-search` skill uses.

## Installation

### Install the code

```bash
uv sync
```

### Install the CLI

```bash
uv tool install .        # puts `ddb` on your PATH
```

### Install to MCP CLIs

Installs to Claude Code, Codex CLI, and Gemini CLI:

```bash
uv run ddb-mcp-install
```

Verify the installation:

```bash
claude mcp list   # For Claude Code
codex mcp list    # For Codex CLI
gemini mcp list   # For Gemini CLI
```

## Usage

```bash
ddb search '"Bert Reese"'                                    # 31 pages, 1901-1938
ddb search 'Hanussen' --from-year 1930 --to-year 1933
ddb search 'Hellseher AND Telepathie' --place Berlin --rows 50
ddb search '"Erik Jan Hanussen" OR Hanuffen' --pages all     # sweep a bounded query
ddb snippets ZKGB4EXAMPLEITEMID 'Gedankenleser'              # where it appears in an issue
ddb get ZKGB4EXAMPLEITEMID-fulltext_5_DDB_FULLTEXT           # cached OCR text path
```

Add `--json` for machine-readable output.

**Search already includes snippets**, which is the important workflow difference from the sibling clients. DDB returns highlighted excerpts in the search response itself, so judging a hit costs nothing beyond the search that found it. Reach for `get` only when a page or issue is worth reading at length. Use `--no-snippets` when you want a compact listing.

**There is no date ordering, deliberately.** `publication_date` is a Solr `DateRangeField` and the server refuses to sort on it, so results always come back by relevance. Rather than offer a flag that quietly reordered only the handful of results already fetched — a chronology in name while the *selection* stayed relevance-ranked — the client omits it. Chronological work means bounding the query with `--from-year`/`--to-year` and sweeping the range with `--pages all`; the ordering then falls out of the sweep.

**The result total is a true count.** Solr reports `numFoundExact`, and it survives checking: `"Bert Reese"` reports 31 results and returns exactly 31 documents. This is unlike Gallica, whose totals are a ranking depth — here a total can be quoted, and a swept query really has been swept.

Downloads are cached in `$XDG_CACHE_HOME/ddb-mcp` (override with `--cache-dir` or `DDB_CACHE_DIR`). The cache location does not depend on the working directory, so the CLI can be run from anywhere.

Requests are paced one per second by default, overridable with `DDB_MIN_REQUEST_INTERVAL`. DDB publishes no rate limit for this endpoint, sends no rate-limit headers, and serves no `robots.txt` on the API host; none was observed across roughly eighty requests including a deliberate burst. **One second is therefore a conservative choice, not a measured ceiling** — there is no evidence about where the real limit sits, only that ordinary use does not come near it.

### API key

None is needed: the newspaper search index answers unauthenticated. That may be an unenforced gate rather than deliberate policy, so if you hold a DDB API key, set `DDB_API_KEY` and the client will send it — the CLI keeps working if enforcement is ever switched on.

Getting one is free and needs no institutional affiliation. Per [DDB's own documentation](https://pro.deutsche-digitale-bibliothek.de/daten-nutzen/schnittstellen), *"Alle registrierten Nutzer\*innen der Deutschen Digitalen Bibliothek können sich einen Authentifikationsschlüssel für die Verwendung der APIs erzeugen lassen"* — any registered DDB user can generate a key, from the *Meine DDB* area of their own account. There is no paid tier. Note that the account pages live on the `www` host, which serves an anti-bot challenge to scripted clients but passes a real browser transparently.

### MCP server

Run the server directly:

```bash
uv run ddb-mcp
```

Test with MCP Inspector:

```bash
uv run fastmcp dev src/ddb_mcp/server.py
```
