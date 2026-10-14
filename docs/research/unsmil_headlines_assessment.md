# UNSMIL "Libya News Headlines" (Jan–Oct 2026): assessment

*14 October 2026. Source: the user's folder `UNDP Dashboard Data/UNSMIL Article/` (196 daily .docx files, 2 exclusion
spreadsheets, 2 SRSG Security Council remarks).*

## What it is

The daily Media Monitoring Review compiled by UNSMIL's Public Information & Communications Section (PICS). Each issue is a
curated selection, not a full feed:

- one English summary line per story, often with the speaker's role in brackets (`[HoR Member] …`);
- grouped under sections (United Nations, Politics, Military & Security, Human Rights & Rule of Law, Economy, Energy,
  Banking, Environment, Reconstruction, Regional & International, Varieties) and then running sub-topics
  ("Teachers' strike", "Electricity crisis", "Smaller Convening", "Foot-and-mouth disease" …);
- after the dash, every outlet that carried it, each linked to the original article;
- "Varieties": features, reports and think-tank pieces with a short summary.

The disclaimer says the reviews "do not reflect the views or official positions of UNSMIL", and UNSMIL does not vouch
for the information they contain. The disclaimer has no confidentiality marking, but this is an internal mission product
sent to a distribution list.

## Size and shape

| | |
|---|---|
| Days | 195 working days, 4 Jan – 14 Oct 2026 (median 93 stories a day) |
| Stories | 19,433 (1,286 of them features, reports or analysis) |
| Article links | 34,061 (33,460 unique); 247 stories have no link |
| Outlets | 914 domains; 76% of outlet mentions are Arabic-language |
| Monthly volume | 1.5–1.6k a month Jan–May, rising to 2.8k in September |
| Outlook SafeLinks | 1,377 links are wrapped in `safelinks.protection.outlook.com`. They can be unwrapped to the real URL, but the wrapper also carries the recipient's email address and must never be stored |
| Exclusion ledgers | 2 days only (6–8 Oct): 469 candidate records, of which 142 were cited, 117 collapsed into another story and the rest excluded with a reason (duplicate 69, not about Libya 61, commentary on an already-covered story 28, sport, weather, routine notices …) |
| Gender-related | 251 stories mention women, girls, gender or GBV |

## How much do we already have?

- **Exact URL match:** 975 of 33,460 links (3%) are already in Desert Watch, almost all from the outlet RSS feeds.
- **Why that number is low:** it understates the true duplication. 20,675 of our 2,026 articles come from Google News, which stores Google's redirect link rather than the outlet's own URL, so those cannot be matched by URL. For the outlets we collect well, overlap is probably high. Compare UNSMIL's link counts with our 2026 article counts:

| Outlet | UNSMIL links | Our 2026 articles |
|---|---|---|
| alwasat.ly | 4,449 | 1,649 |
| eanlibya.com | 2,634 | 2,235 |
| libyaobserver.ly | 1,515 | 2,560 |
| libyareview.com | 1,371 | 1,190 |

- **Where the real gap is:** some major Libyan outlets that UNSMIL cites every day barely reach us, or not at all:

| Outlet | UNSMIL links | Our 2026 articles |
|---|---|---|
| lana.gov.ly (state news agency) | 3,116 | 6 |
| lywitness.com (Al Shahed) | 1,993 | 10 |
| akhbarlibya24.net | 1,391 | 20 |
| addresslibya.com | 1,190 | 9 |
| almarsad.co | 1,147 | 17 |
| almenassa.ly | 1,035 | 0 (unknown outlet) |
| reportage.ly (RNA) | 923 | 0 (unknown) |
| libya24.tv | 780 | 0 (unknown) |
| libyaalahrar.tv | 698 | 22 |
| fawaselmedia.com, alsabaah.ly, abaad.news, minbarlibya.org, lananews.com | 50–200 each | 0 |

  Some of these feeds only went live today (from the social-media scrape), so the September/October counts will improve on their own. The 2026 history is still missing, though.

## What it is good for (ranked)

1. **Fixing our outlet blind spots (high value, low risk).** Add the missing outlets and check why LANA, Al Shahed, Akhbar Libya 24, Address Libya, Al Marsad and Libya Al Ahrar are under-collected. Their articles are public; only the links are used.
2. **Backfilling those outlets' 2026 coverage.** Import the article links from UNSMIL's selection as coverage items, deduped by URL. To avoid double-counting, only take links from outlets where our own 2026 count is under ~20% of UNSMIL's. That covers the table above, about 13k links. The outlets we already collect well are skipped.
3. **A topic check on our themes.** UNSMIL gives heavy, sustained attention to subjects that none of our themes cover:
   - energy (electricity crisis, fuel supply);
   - banking and liquidity;
   - environment (foot-and-mouth disease);
   - education (the teachers' strike);
   - reconstruction;
   - the political tracks (Structured Dialogue, Smaller Convening, the High Council of State).

   Candidate new themes, with search terms drawn from their sub-topic names.
4. **Training labels (internal only).** 19.4k English summaries with section and sub-topic labels, plus the two exclusion ledgers (relevance, duplicates, "not about Libya"). These can train and evaluate the topic matcher and the relevance guard. They would never be shown to users.
5. **A professional editor's benchmark.** "Did UNSMIL's monitors think this mattered, and did our system rank it?" This is useful for validating gap scores, but needs (2) and (3) first.

## Cautions

- **Internal product.** The summaries, section structure and selection are UNSMIL PICS's editorial work. Desert Watch is shared with outside journalists, so I recommend we don't display or quote the summaries, or label anything "selected by UNSMIL", without PICS's agreement. The links and outlet names are public facts and can be used. If used at all, the summaries stay internal as training data.
- **No email data.** SafeLinks wrappers are unwrapped and the wrapper discarded, which also drops the recipient's address.
- **Named people.** Most bracketed names are officials. Crime stories can name private individuals, which is one more reason not to display summaries.
- **A selection, not a census.** Counts reflect UNSMIL's priorities (a UN-centred view and its section quotas). They must not be read as total Libyan coverage, or mixed into our coverage counts as such.
- **Coverage period.** 2026 only. The exclusion ledgers cover just 2 days, enough to evaluate the relevance guard but not to train it.

## Recommendation

Do (1) and (2) now, add (3) as proposed themes for you to approve, and keep (4) internal for the learning loop. New daily
files can be dropped into the same folder and imported whenever you like; the importer would be idempotent.
