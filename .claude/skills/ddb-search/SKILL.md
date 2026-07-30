---
name: ddb-search
description: Search the Deutsches Zeitungsportal (Deutsche Digitale Bibliothek) with the `ddb` CLI. Use for German-language newspapers 1850-1950 — the German press coverage of touring performers, and anything published in Germany.
---

# Deutsches Zeitungsportal (DDB)

Germany's national newspaper portal, aggregating the holdings of the Staatsbibliothek zu Berlin, the state and university libraries, and dozens of regional institutions. ~33.8 million digitised pages, of which about 27.9 million fall between 1850 and 1949. The place to look for the German press — and the 1920s and 1930s, the years of the great Weimar mind readers, are the best-covered decades in the whole collection.

Results are individual **pages**, not issues or titles. A hit tells you the newspaper, the date and the page number, and comes with the matched text already quoted.

## Commands

```sh
ddb search "<query>" [--pages N|N-M|all] [--rows N] [filters] [--json]
ddb facets <field> ["<query>"] [--limit N] [filters]   # what values a filter can take
ddb snippets <id> "<query>"   # where a query appears inside one page or issue
ddb get <id>                  # download OCR text, prints path to the cached file
```

Filters for `search` and `facets`: `--from-year`, `--to-year`, `--title TEXT` (newspaper title), `--place TEXT`, `--language CODE` (ISO 639-2, `ger`), `--provider TEXT` (holding institution), `--zdb-id ID`.

**There is no `--sort`.** Results come back by relevance; see the trap below.

## `facets` — finding the value, and characterising a result set

`ddb facets place|provider|language|title` lists the values that filter can take, with page counts, most pages first. It does two different jobs.

**Getting the value right.** `--place` and `--provider` match a whole string, and a near-miss is not a near-miss — it is silence. `--place Halle` reports `0 pages matched` with no error; `--place "Halle (Saale)"` matches 1.1 million pages. `--provider Bayerische` matches nothing; `--provider "Bayerische Staatsbibliothek"` matches 8.3 million. There is no way to guess which form the index holds, so look before filtering. `--title` is the forgiving exception: it is analysed text with German stemming, so a fragment of a title works.

**Characterising what you found.** Hand `facets` a query and the counts describe that result set, computed by the index over all of it rather than over the twenty results you fetched. This is the closest thing this source has to an overview, and it is worth a request before a long sweep:

```sh
ddb facets place '"Hellseher"' --limit 15                     # the geography of a term
ddb facets title 'Hanussen' --from-year 1930 --to-year 1935   # which papers carried him
ddb facets language '"Gedankenleser"'                        # is the corpus really all German
```

`facets title` lists **ZDB identifiers with a title beside each**, because `paper_title` is stemmed text and facets into word stems (`zeitung`, `nachricht`, `fuer`) rather than titles — so titles are counted through `zdb_id`, which is one term per paper, and labelled afterwards. Two consequences worth holding on to:

- The identifier is the exact thing and pastes straight into `--zdb-id`. The title beside it is a signpost: the recorded string covers a paper's whole run, so a 1900-1910 listing happily shows a subtitle the paper only acquired in the 1930s, and one identifier can cover several forms (`Hamburger Fremdenblatt` and `Hamburger Fremdenblatt, Abendausgabe`).
- Counts are page counts per title, so a paper publishing morning and evening editions under one identifier accumulates both.

`place` and `language` are multi-valued per page, so their counts can sum to more than the total. That is not double counting to correct for — it means a page distributed in two places is counted in both.

Identifiers come in two shapes and both commands accept either. A **page id** looks like `QH5LZ372MFWP2SLFKDRQI4FK3BN4O6JI-fulltext_5_DDB_FULLTEXT`; an **issue id** is the part before the hyphen. Give `get` an issue id and it returns every page of that issue in one file, with `=== ... page N ===` markers between them.

## Search already gives you the snippets

This is the important workflow difference from the other sources. DDB returns highlighted excerpts **in the search response itself**, with matched terms in `{braces}`, so judging a hit costs nothing beyond the search that found it. There is no separate cheap-triage step to run.

That makes the shape here: `search` → read the snippets → `get` only what deserves reading at length. `--snippets N` sets how many excerpts per page (default 3), `--snippet-size N` how long each is (default 200 characters). `--no-snippets` gives a compact listing when you only want to know which issues exist.

`ddb snippets` is for the case where you already hold an identifier and want to know where a *different* term appears in it — for instance sweeping a promising issue for a collaborator's name after the original search found the performer.

## Query syntax

The query is passed to Solr essentially untouched, so the whole syntax is available:

- `"quoted phrases"` match exactly
- `AND`, `OR`, `NOT` — uppercase, as usual
- Parentheses group: `(Hanussen OR Steinschneider) AND Hellseher`
- `Hellseh*` wildcards
- `Hanussen~1` fuzzy-matches, for OCR damage
- `"Hellseher Hanussen"~10` matches the two terms within ten words of each other

Proximity is worth more here than on other sources. Page-level matching means an `AND` of two terms can join a name at the top of a page to a word in an unrelated column at the bottom; `~10` asks for them in the same passage, which on a dense newspaper page is usually what you meant.

**Search in German.** Names generally carry across, but everything around them does not: `Gedankenleser` (mind reader), `Hellseher` (clairvoyant), `Telepathie`, `Gedankenübertragung` (thought transference), `Wahrsager` (fortune teller), `Medium`, `Zauberkünstler` (conjurer), `Varieté`. German papers write `Professor Reese`, not `Prof. Reese`.

## The result total is a true count

Unlike Gallica, **DDB's total means what it says.** Solr reports `numFoundExact`, and it survives checking: `"Bert Reese"` reports 31 results and returns exactly 31 documents, spanning 1901 to 1938. So:

- A total may be quoted in a report as a count of matching pages.
- A query swept to the end really has been swept, and exhaustivity claims about this source are meaningful.
- `--pages all` is a reasonable thing to do on a bounded query, unlike on Gallica.

Do keep the count honest about *what* it counts: pages, not articles or stories. One story continued across two pages is two hits, and a wire story reprinted in forty papers is forty.

## Being exhaustive

20 results per page by default, up to 100 with `--rows`. `--pages all` sweeps to the end.

Because the totals are real, the judgement is simply whether the number is small enough to read. A few hundred pages is a sweep; tens of thousands means tightening the query first — with a date range, a title, or proximity instead of `AND`.

## False positives to expect

- **Hyphenation across line breaks is not rejoined.** This is the biggest practical trap on this source, and it loses hits silently rather than adding noise. The OCR keeps `Ver waltungsstellen` and `organisatori scher` exactly as the line broke them, so a phrase search misses any occurrence that happened to break mid-word. When a name looks under-represented, try its halves, or a proximity query.
- **Letterspaced names shatter.** German papers emphasised personal names by letterspacing them, and the OCR reads each letter as a token: `S ch l e s i n g e r`. Another silent loss — reach for wildcards or fuzzy matching when a name you know is there does not appear.
- **German stemming is active**, so single-term counts are counts of the stem: `Hellseher` and `Hellsehers` return the same 16,355. You cannot pin an exact surface form with a bare term — use a quoted phrase if the exact form matters.
- **Long ſ reads as f.** `Hellfeher` for `Hellseher`, `Hanuffen` for `Hanussen`. Only around 0.5% of occurrences for common words but 3.8% for proper nouns, which have no lexicon to correct against — worth one extra `OR` clause per name, not a crisis.
- **Arbitrary initial-letter substitution on names.** A 1934 paper prints Hanussen as `üanussen` and Erik as `Erle`, and those are indexed literally. `~1` fuzziness finds them but is far too noisy alone: pair it with a second term.
- **Umlauts are preserved, not folded**, so `für` and `fur` are distinct terms. An OCR-dropped umlaut is a separate recall bucket you have to ask for.
- **Punctuation spacing varies by provider.** Some collections put spaces around every mark (`Okt . 1932`), others do not. Never assume punctuation adjacency inside a phrase.
- **The Fraktur double hyphen ⸗ reads as `=`**: `X = Strahl = Augen`, `Industrie = und Handelskammer`.
- **Common names collide with places and titles.** `Cumberland` returns 110,511 pages, mostly the Duke of Cumberland; `NOT Herzog` drops it to 43,885. Check what a name competes with before trusting a large total.

## Traps specific to this source

- **There is no date ordering, and this differs from the other sources.** Gallica and ANNO both offer `--sort date_asc`; DDB has no equivalent, because `publication_date` is a Solr `DateRangeField` the server refuses to sort on. Do not look for the flag: it is absent on purpose rather than missing. For chronological work, narrow with `--from-year`/`--to-year` and sweep the range with `--pages all` — the ordering falls out of the sweep. Since totals here are exact, you can tell in advance whether a range is small enough to sweep whole.
- **The `www` host is walled, the API host is not.** `www.deutsche-digitale-bibliothek.de` serves an Anubis anti-bot challenge to every scripted client, with HTTP 200 rather than an error status. The CLI never touches it. This matters only if you try to fetch a viewer URL directly: those URLs are for the researcher to open in a browser, where they pass transparently, not for fetching.
- **Snippets rely on a non-default highlighter.** The client sets `hl.method=original` because this Solr's default highlighter returns an *empty* highlight block for every document on a phrase query — a well-formed response with no snippets, which reads as "the terms are not there" rather than as a failure. If snippets ever vanish across the board while results keep arriving, that is the cause, not an absence of matches.
- **`get` is cheap here, unusually.** A page's whole OCR is a field on the search document, so downloading is one ordinary query rather than a separate guarded endpoint. Nothing here resembles Gallica, where OCR is billed one request per page against a budget of four. Still prefer snippets for judging, because reading a whole page costs *context*, not requests.
- An issue runs to a few hundred kilobytes across all its pages. Grep the cached file or read slices; never read it whole.

## Cost

Rate-limited to **one request per second** with single concurrency, overridable with `DDB_MIN_REQUEST_INTERVAL`. DDB publishes no limit for this endpoint and none was observed in testing, which makes this the most permissive source in the set — three times looser than Gallica. Pacing is shared across every process, so parallel subagents share one budget: fanning out speeds up the reading, not the fetching.

Server-side query time, not rate limiting, is the real cost. Most queries answer in tens of milliseconds; a faceted sweep over the whole corpus takes seconds, and deep `start` offsets get slow. An unbounded range query on the fulltext field times out server-side and comes back as an error carried by HTTP 200 — the client surfaces it rather than reporting zero results.

No API key is required. If one is ever needed, set `DDB_API_KEY` and the client will send it. Keys are free, need no institutional affiliation and have no approval step: register a DDB account, then generate the key at <https://www.deutsche-digitale-bibliothek.de/user/apikey>. Both pages need a real browser — they sit on the anti-bot-walled `www` host.

**Over-querying gets you banned, and the ban outlasts the session.** This is a free public service; a sweep that looks thorough from here looks like scraping from theirs. If requests start failing or returning something that is not what you asked for, stop and say so rather than retrying into a longer ban.
