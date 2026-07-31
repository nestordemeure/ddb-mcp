---
name: ddb-search
description: Search the Deutsches Zeitungsportal (Deutsche Digitale Bibliothek) with the `ddb` CLI. Use it for German-language newspapers from 1850 to 1950 — the German press coverage of performers on tour, and all material published in Germany.
---

# Deutsches Zeitungsportal (DDB)

The national newspaper portal of Germany. It collects the holdings of the Staatsbibliothek zu Berlin, the state and university libraries, and dozens of regional institutions. It holds approximately 33.8 million digitised pages, and approximately 27.9 million of them are from 1850 to 1949. Use it for the German press. The 1920s and the 1930s, the years of the great Weimar mind readers, are the decades with the best coverage in the full collection.

The results are individual **pages**, not issues and not titles. A result tells you the newspaper, the date and the page number, and it includes the matched text.

## Commands

```sh
ddb search "<query>" [--pages N|N-M|all] [--rows N] [filters] [--json]
ddb facets <field> ["<query>"] [--limit N] [filters]   # what values a filter can take
ddb snippets <id> "<query>"   # where a query appears inside one page or issue
ddb get <id>                  # download OCR text, prints path to the cached file
```

The filters for `search` and `facets` are `--from-year`, `--to-year`, `--title TEXT` (the newspaper title), `--place TEXT`, `--language CODE` (ISO 639-2, `ger`), `--provider TEXT` (the institution that holds the item) and `--zdb-id ID`.

**There is no `--sort` option.** The results come back in order of relevance. See the risks below.

## `facets` — how to find a value, and how to describe a result set

`ddb facets place|provider|language|title` lists the values that a filter can take, with page counts, and it puts the largest counts first. It does two different tasks.

**How to find the correct value.** `--place` and `--provider` match a full string, and a near-miss is not a near-miss. It is silence. `--place Halle` reports `0 pages matched` with no error. `--place "Halle (Saale)"` matches 1.1 million pages. `--provider Bayerische` matches nothing. `--provider "Bayerische Staatsbibliothek"` matches 8.3 million. You cannot guess which form the index holds, so look before you filter. `--title` is the one exception: it is analysed text with German stemming, so a fragment of a title operates correctly.

**How to describe a result set.** Give `facets` a query, and the counts describe that result set. The index computes them over the full set, not over the twenty results that you received. This is the nearest thing to an overview that this source has, and it is worth one request before a long search:

```sh
ddb facets place '"Hellseher"' --limit 15                     # the geography of a term
ddb facets title 'Hanussen' --from-year 1930 --to-year 1935   # which papers carried him
ddb facets language '"Gedankenleser"'                        # is the corpus really all German
```

`facets title` lists **ZDB identifiers with a title beside each one**. The reason is that `paper_title` is stemmed text, and it facets into word stems (`zeitung`, `nachricht`, `fuer`) and not into titles. Thus the tool counts the titles through `zdb_id`, which is one term for each paper, and adds the labels afterwards. This has two consequences:

- The identifier is exact, and you can put it directly into `--zdb-id`. The title beside it is only a guide. The recorded string covers the full run of a paper, so an entry for 1900-1910 can show a subtitle that the paper received in the 1930s. One identifier can also cover several forms (`Hamburger Fremdenblatt` and `Hamburger Fremdenblatt, Abendausgabe`).
- The counts are page counts for each title. Thus a paper with a morning edition and an evening edition under one identifier collects both.

`place` and `language` can have more than one value for each page, so their counts can sum to more than the total. This is not an error to correct. It means that the tool counts a page distributed in two places in both places.

The identifiers have two shapes, and both commands accept both shapes. A **page id** looks like `QH5LZ372MFWP2SLFKDRQI4FK3BN4O6JI-fulltext_5_DDB_FULLTEXT`. An **issue id** is the part before the hyphen. Give `get` an issue id, and it gives each page of that issue in one file, with `=== ... page N ===` markers between the pages.

## The search already gives you the snippets

This is the important difference in procedure from the other sources. DDB gives the highlighted extracts **in the search response**, with the matched terms in `{braces}`. Thus to judge a result costs nothing more than the search that found it. There is no separate low-cost rejection step.

The procedure here is: `search` → read the snippets → `get` only the pages that deserve a long reading. `--snippets N` sets the number of extracts for each page (default 3). `--snippet-size N` sets the length of each extract (default 200 characters). `--no-snippets` gives a compact list when you only want to know which issues exist.

Use `ddb snippets` when you already have an identifier and want to know where a *different* term appears in it. For example, use it to search a promising issue for the name of a collaborator after the first search found the performer.

## Query syntax

The client sends the query to Solr with almost no change, so the full syntax is available:

- `"quoted phrases"` match exactly
- `AND`, `OR`, `NOT` — uppercase, as usual
- Parentheses group the terms: `(Hanussen OR Steinschneider) AND Hellseher`
- `Hellseh*` is a wildcard
- `Hanussen~1` is a fuzzy match, for OCR errors
- `"Hellseher Hanussen"~10` matches the two terms within ten words of each other

Proximity has more value here than on the other sources. A match is at page level, so an `AND` of two terms can join a name at the top of a page to a word in an unrelated column at the bottom. `~10` asks for the two terms in the same passage, which is usually your intention on a dense newspaper page.

**Search in German.** Names usually stay the same, but the words around them do not: `Gedankenleser` (mind reader), `Hellseher` (clairvoyant), `Telepathie`, `Gedankenübertragung` (thought transference), `Wahrsager` (fortune teller), `Medium`, `Zauberkünstler` (conjurer), `Varieté`. German papers write `Professor Reese`, not `Prof. Reese`.

## The result total is a true count

**The total of DDB means what it says.** This is different from Gallica. Solr reports `numFoundExact`, and tests confirm it: `"Bert Reese"` reports 31 results and gives exactly 31 documents, from 1901 to 1938. Thus:

- You can give a total in a report as a count of matching pages.
- A query that you searched to the end is truly complete, and a statement about completeness on this source has a meaning.
- `--pages all` is a reasonable action on a limited query. This is different from Gallica.

Keep the count honest about *what* it counts: pages, not articles and not stories. One story that continues across two pages is two results. One wire story printed in forty papers is forty results.

## How to be complete

There are 20 results on each page by default, and up to 100 with `--rows`. `--pages all` collects each page to the end.

The totals are real, so the decision is simple: is the number small enough to read? A few hundred pages is a search that you can complete. Tens of thousands means that you must make the query more narrow first — with a date range, with a title, or with proximity in place of `AND`.

## False positives to expect

- **The OCR does not join hyphenation across a line break.** This is the largest practical risk on this source, and it loses results silently. It does not add incorrect results. The OCR keeps `Ver waltungsstellen` and `organisatori scher` exactly as the line divided them, so a phrase search does not find any occurrence that divided inside a word. When a name looks rare, search for its two halves, or use a proximity query.
- **Letterspaced names break apart.** German papers gave emphasis to personal names with letterspacing, and the OCR reads each letter as a token: `S ch l e s i n g e r`. This is a second silent loss. Use wildcards or fuzzy matching when a name that you know is present does not appear.
- **German stemming is active**, so a count for a single term is a count for the stem: `Hellseher` and `Hellsehers` both give 16,355. You cannot select one exact surface form with a bare term. Use a quoted phrase when the exact form is important.
- **A long ſ reads as f.** `Hellfeher` for `Hellseher`, `Hanuffen` for `Hanussen`. This occurs in approximately 0.5% of the occurrences of common words, but in 3.8% of proper nouns, which have no lexicon for a correction. Add one more `OR` clause for each name. This is not a serious problem.
- **A substitution of the first letter of a name, with no pattern.** A paper of 1934 prints Hanussen as `üanussen` and Erik as `Erle`, and the index holds these forms exactly. `~1` fuzzy matching finds them, but alone it gives far too many incorrect results. Combine it with a second term.
- **The index keeps the umlauts. It does not fold them**, so `für` and `fur` are different terms. When the OCR loses an umlaut, that form is a separate group of results that you must request.
- **The spacing around punctuation is different for each provider.** Some collections put a space around each mark (`Okt . 1932`), and others do not. Never assume that a phrase holds punctuation without a space.
- **The Fraktur double hyphen ⸗ reads as `=`**: `X = Strahl = Augen`, `Industrie = und Handelskammer`.
- **Common names are also places and titles.** `Cumberland` gives 110,511 pages, mostly the Duke of Cumberland. `NOT Herzog` reduces this to 43,885. Find what a name competes with before you trust a large total.

## Risks specific to this source

- **There is no order by date, and this is different from the other sources.** Gallica and ANNO both offer `--sort date_asc`. DDB has no equivalent, because `publication_date` is a Solr `DateRangeField` and the server refuses to sort on it. Do not look for the flag. It is absent by decision, not by omission.

  For chronological work, limit the query with `--from-year` and `--to-year`. Then collect the full range with `--pages all`. You then put the results in date order yourself. DDB does not supply that order. The totals here are exact, so you can know in advance if a range is small enough to collect completely.
- **The `www` host has a wall. The API host does not.** `www.deutsche-digitale-bibliothek.de` sends an Anubis anti-bot challenge to each script, with HTTP 200 and not with an error status. The CLI never uses that host. This is important only if you try to fetch a viewer URL directly. Those URLs are for the researcher to open in a browser, where they operate correctly. They are not for a script.
- **The snippets need a highlighter that is not the default one.** The client sets `hl.method=original`, because the default highlighter of this Solr gives an *empty* highlight block for each document on a phrase query. That is a correct response with no snippets, which reads as "the terms are not present" and not as a failure. If the snippets ever disappear for each document while the results continue to arrive, this is the cause. The matches are not absent.
- **`get` has a low cost here, which is unusual.** The full OCR of a page is a field on the search document, so a download is one ordinary query and not a separate guarded endpoint. Nothing here is like Gallica, where the OCR costs one request for each page against a budget of four. Still use the snippets to judge a result, because to read a full page costs *context*, not requests.
- One issue holds a few hundred kilobytes across all of its pages. Search the cached file with grep, or read parts of it. Never read it completely.

## Cost

The client permits **one request each second**, with one request at a time. Change this with `DDB_MIN_REQUEST_INTERVAL`. DDB publishes no limit for this endpoint, and the tests observed none. Thus this is the most permissive source in the set — three times more permissive than Gallica. All processes share the rate limit, so parallel subagents share one budget. Many parallel subagents read the documents more quickly. They do not send the requests more quickly.

The real cost is the query time on the server, not the rate limit. Most queries answer in tens of milliseconds. A faceted search across the full corpus takes seconds, and a deep `start` offset becomes slow. A range query with no limits on the fulltext field times out on the server and comes back as an error inside an HTTP 200 response. The client reports this error. It does not report zero results.

No API key is necessary. If a key becomes necessary, set `DDB_API_KEY` and the client will send it. The keys are free, they need no institutional affiliation, and they need no approval. Register a DDB account, then make the key at <https://www.deutsche-digitale-bibliothek.de/user/apikey>. Both pages need a real browser, because they are on the `www` host with the anti-bot wall.

**Warning: Do not send too many requests. Too many requests cause the archive to block you, and the block continues after this session.**

This is a free public service. A search that looks thorough to you looks like data collection to the archive operators. Sometimes the requests start to fail. Sometimes they give content that you did not ask for. If this occurs, stop. Tell the user. Do not send the request again, because a repeated request makes the block longer.
