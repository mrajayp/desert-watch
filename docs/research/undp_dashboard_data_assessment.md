# Assessment: "UNDP Libya Dashboard" exports for Desert Watch (2026-10-14)

Source folder: `OneDrive/Documents/UNDP Dashboard Data` (37 files: 29 `.xlsx` exports, 8 screenshots).
Nothing has been imported into Desert Watch. This note records what the data is, how it lines up
with Desert Watch, and what it could be used for, with the decisions it needs.

## 1. What it is

Exports from a Power BI-style "UNDP Libya Dashboard: Social & Traditional Media Monitor", built
"with the support of UNDP Libya" (front-page screenshot). Three pages:

| Page | Files | Content |
|---|---|---|
| Summary | 9 | Daily volume and average sentiment of UN-related articles and Facebook posts; excerpts mentioning UN keywords; top articles / posts |
| Domain / Article | 14 | Per-domain totals for **90 news domains**: articles, Facebook posts and engagement, tweets, a sentiment score, "Authentic / Inauthentic" + a category (Pro-LNA, Pro-GNU…); volumes by author, topic and keyword |
| Facebook Engagement | 6 | Per-page totals for **625 Facebook pages**: posts, interactions, comments, shares, "social velocity", performance score, sentiment, source type and affiliation; engagement by key phrase |

- **Period:** 1 Oct 2023 – ~10 Aug 2024 (dated files). It is a closed window, not a live feed.
- **Scale:** 32,250 articles (90 domains); 453,301 Facebook posts (625 pages), 147.5M interactions; 6,063 tweets.
- **Grain:** almost everything is pre-aggregated (totals per domain / page / keyword). The only
  time series are the daily UN-related volume and sentiment series and a 14-phrase daily post count.
  There are no article-level rows except "top" lists (31 articles, 10 posts).
- **Duplicates:** `(1)`/`(2)` copies are identical or differently filtered (one sentiment file is
  filtered to climate/UN-development terms; noted in its header row).

## 2. Quality and caveats

- **Totals do not match the screenshots.** The Facebook Page Details screenshot totals 530,253 posts /
  187.9M interactions; the export totals 453,301 / 147.5M. The exports were taken with a different filter or date.
- **Domain field is the first label of the hostname** (`ar`, `bit`, `sticker`, `clubhouse`…), so
  `ar` merges ten unrelated sites and link shorteners appear as "domains". It needs cleaning before any join.
- **Method unknown:** the sentiment model (0–1), "social velocity", "performance score" and how
  "Authentic/Inauthentic" was decided are not documented in the exports.
- **The affiliation labels are contested and in places doubtful.** Al Wasat, Libya Observer and Libya
  Akhbar are all labelled *Inauthentic / Pro-LNA*. Libya Observer is usually described as Tripoli-leaning,
  not pro-LNA. "Inauthentic" normally means coordinated inauthentic behaviour, which is a strong claim
  to make about a news site. These labels must not be treated as fact.
- **Facebook pages are mixed:** sports clubs, a mobile operator, perfume stores and celebrities sit
  alongside news pages. They need filtering to news / public-affairs pages.
- **Sensitivity:** these are dashboard exports produced for UNDP. Use inside Desert Watch should be
  team-only and attributed institutionally ("UNDP Libya dashboard, 2024"). Check whether redistribution
  is allowed before showing it to journalists outside UNDP.

## 3. How it lines up with Desert Watch

- **36 of 90 domains match a Desert Watch outlet.** Not matched, with volume over the period:
  lywitness (1,204 articles), addresslibya (619), arraedlg (365), alwatan-ly (362), sada (82),
  libyan-cna (72), akhbarlibya24 (22), lananews (11) and others.
- **It shows the limits of our historical backfill.** In the same window the UNDP monitor counted
  32,250 articles, all topics. Desert Watch holds 5,446 theme-relevant articles. For Libya Akhbar the
  figures are 19,662 against our 28: our backfill for that window only covers theme-matched search
  results (general themes from Jan 2024; gender from 2019). The two counts measure different things,
  but the gap confirms that our history before 2024 is a sample, not a census.
- **It covers our biggest blind spot, Facebook,** which Desert Watch cannot monitor. The page list gives
  each Libyan Facebook-first outlet's name, posting volume and audience. By interactions the leaders are
  LibyaAlAhrarTV, ObservatoryLY, OnlyLibya, buhmud, LibyaAlhadathLive and Libyan.Address.Journal.

## 4. Possible uses, most useful first

1. **Add the missing Libyan news domains to monitoring** (lywitness, addresslibya, arraedlg,
   alwatan-ly, libyan-cna, akhbarlibya24, lananews…): probe for RSS feeds and add them. Low risk,
   and it uses only the domain list, not the labels.
2. **A "Facebook blind-spot" register:** import the news / public-affairs subset of the 625 pages as
   *unmonitored Facebook outlets*, with reach (posts and interactions, Oct 2023–Aug 2024). They would
   appear on the Outlets page and in gap panels as "may be covered on Facebook; not monitored". This
   makes the coverage caveat concrete instead of generic. Their engagement can also set an outlet
   "reach" tier.
3. **A coverage-completeness benchmark:** per-domain article totals for Oct 2023–Aug 2024 give an
   external check on our collection rate per outlet. This is a one-off calibration table in
   docs/review, not app data.
4. **Third-party labels, kept as published and kept apart.** If wanted, the Authentic/Inauthentic and
   affiliation labels could be stored as a separate attributed layer: "UNDP Libya dashboard (2024)
   classified as …", confidence *disputed*, team-only, never feeding the alignment filters or the
   "only one side's outlets" flag. Given the doubtful cases above, I would not import them without your review.
5. **Low value:** the UN-related sentiment and volume series (closed window, undocumented model),
   key-phrase engagement (dominated by sport and entertainment) and the co-occurring excerpts.
   They could be one context track on the Timeline at most.

## 5. Decisions needed
- Is Desert Watch allowed to store and display this data, and to whom (team only, or also invited
  journalists)?
- Which uses to adopt: 1 (new domains), 2 (Facebook register), 3 (benchmark), 4 (labels)?
