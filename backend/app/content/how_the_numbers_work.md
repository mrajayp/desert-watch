# How the numbers work

This is for admins. It says how each figure in Desert Watch is worked out and where it can mislead you. If something on a page looks odd, start here.

## Articles we count

An article counts as coverage when it mentions Libya or a Libyan place, or comes from a Libyan outlet and matches a theme. Anything else is kept but marked as not relevant.

Articles come from Google News searches, outlet news feeds, Google Alerts and the historical backfill. People can also add them. Every article counts once, whatever its source.

The same story often reaches us twice. Google News gives us its own link, and the outlet's feed or the backfill gives the real one. So we look for articles from the same outlet, published within a day of each other, with almost the same headline. We count one copy and keep the outlet's own link. The others are kept but left out of every number.

Coverage also goes up whenever we add a source. The trend charts and the audience gap allow for this. The monthly bars don't.

## Themes and places

A theme is a list of words in Arabic and English. If a headline or summary contains one of the words, the article gets that theme. Some themes need two sets of words together, for example women plus violence. The gender themes are strict. A search result only counts for them if the words are really in the text.

Places work the same way. We look for district and town names, including other spellings. Most articles do not name a place below Libya, so they only count nationally. That is normal and is why the regional numbers are much smaller.

You can change the words for any theme in Admin → Themes and preview what they would match before saving.

## Need

Need is the other side of the comparison. It is what suggests a topic should be getting coverage. We have four kinds, one per lens.

- The audience lens uses Wikipedia page views for articles linked to each theme. National only.
- The humanitarian lens uses ReliefWeb reports on Libya, matched to themes by the same words.
- The events lens will use conflict and protest events from ACLED and UCDP. It stays empty until the keys arrive.
- The journalists lens counts gaps people flag in the app, one unit each.

## The gap score

Each cell is one theme, one place and one week, for one lens. It looks at the four weeks ending that week.

We divide coverage by need to get a ratio. Then we compare that ratio with a reference.

- For the audience lens the reference is the same theme's own ratio over the 12 weeks before. So the gap says "less coverage for the interest than usual for this topic".
- For the other lenses the reference is the average across all themes nationally. For a district it is that theme's national ratio. So the gap says "less coverage per report or event than other topics get".

Small cells are pulled towards the reference before comparing, so a district with two reports cannot swing wildly. The gap is shown as how many times less coverage there is than expected. Anything under about 1.15 times is shown as covered about as expected.

If need is below a minimum the cell is not scored and shows as hatched. The minimums are 500 page views, 2 reports, 3 events or 1 flag in the window. Weeks before we started collecting are not scored either.

For the audience lens we only count outlets we were collecting from across the whole 16 weeks being compared, through the same route. So Al Wasat through Google News counts, because we have years of it. Al Wasat through its own feed only started in October, so it is left out until it has 16 weeks behind it. The same goes for Google Alerts and for outlets Google News only turns up for recent weeks. The backfill is never used in these comparisons. How much it holds for a week depends on how many stories the monitoring review chose to cite, and that grew through the year. The gap panel and the article lists still show every article.

## Flags on a cell

- Coverage dropped. Coverage fell by more than half compared with the previous four weeks while need stayed about the same. Both windows are counted on the same outlets, so an outlet or feed starting or stopping does not trigger it.
- Little Arabic. Less than a fifth of the articles are in Arabic.
- Only covered from outside. No Libyan outlet covered it, only international or diaspora ones.
- One side only. Every outlet with a known political alignment that covered it is on the same side. This uses our own alignment labels, never the ones from the social media scrape.
- Mostly unplaced. More than 80% of the articles name no place, so the regional picture is weak.

## Trends page

The small charts show the last 52 weeks for each theme. Need and coverage are each set so their own average is 100. That lets them share one axis, so you see how each moves over time. You can't read off which theme gets more coverage. The coverage line only counts outlets we collected from all through the year shown, and never the backfill. The note under the charts says how many.

The monthly bars are a straight count of articles per month by language. Older months come from searching back, which finds fewer articles, so look at the ups and downs between years. The totals don't compare. 2026 is fuller because of the backfill, but even there the backfill follows what one monitoring service picked.

The long-run line comes from GDELT. It counts articles worldwide that mention the theme and Libya, using its own English translations. It does not depend on what we collect, which makes it the fairest long view. GDELT often refuses our requests. The line is also only refreshed when an admin runs the backfill job, so it can be weeks old.

Clicking a point on any of these charts lists the articles behind it. For the GDELT line it lists our own articles for that week, because GDELT only gives counts.

## Map and who covers where

The lines join each outlet to the districts its articles name. Line thickness is the number of articles. Outlets based outside Libya sit around the edge by country. Districts are coloured by gap only when the lens has enough need data at district level. Right now none does, so the colours show how much coverage each district gets.

## Coverage clusters

We take the outlets with at least 10 articles in the last 12 weeks, up to 120 of them. For each one we work out which themes it covers more or less than the average outlet. Outlets with similar patterns are linked, and a standard community method splits them into clusters. Each cluster is named after the two themes it over-covers most.

Arrows between clusters are reprints. Two headlines count as the same story when most of their words match and they appeared within two days of each other. The arrow points from the outlet that published first.

## Contribute page

The gap list shows the biggest gaps in the last four weeks that nobody has voted on. The article lists are recent articles with no theme or no place, one unrated article from each busy outlet, and outlets with a lot of articles but no scope or alignment on record.

Votes and corrections are saved as labels for training. So are article ratings. Nothing changes the rankings automatically yet. The plan is to switch on a model only once there are enough labels and it beats the word lists on a test set.

## Weekly digest

Once a week we work out the facts here first. These are the biggest gaps with their flags, plus a few headlines. Only those facts go to the AI model, and it is told to use no number that is not in them. The facts are saved with the text so any claim can be checked. It needs the Anthropic key to run.

## Engagement

Engagement is how much attention an article got after it came out. We measure two things per article and keep a few dated figures per outlet.

Story pickup is the number of outlets that ran the same story. We use the headline match from the reprint arrows. Most of the words match and the articles appeared within two days of each other. It is worked out whenever the network updates, for the last 12 weeks. Rewritten and translated versions are missed, so it undercounts. Most stories only ever appear in one outlet. Close to nine in ten articles in the last 12 weeks were single-outlet stories. Link shorteners like t.co are left out because they are not outlets.

Facebook engagement is the total that Facebook reports for an article's link. Hover over it to see the breakdown. We read it about two days after the article came out and again after about a week. The week-old reading is the one we trust most. Facebook says its counts are approximate on purpose, so we show them rounded with a ≈ sign. This needs an app ID and secret from a Meta developer account. Until both are set the source shows as waiting for its key. We read at most 400 links a day. If Facebook says we are asking too often we stop and try again six hours later. We skip LANA because its links drew no Facebook posts at all in the 2023-24 scrape.

Facebook can only match the outlet's own link. Google News gives us a redirect link instead, and in October 2026 that was the only link for about 60% of the articles we count. So every night we look for the outlet's own link for Google News articles from the last two weeks. First we look for a copy of the same story from the same outlet that reached us another way, like its feed or Google Alerts. If there is none and the outlet's site runs WordPress, we search the site for the headline. We only accept a result with almost the same headline, published within a day. Daily posts like exchange rates that differ only by a date or weekday never count as a match. The Google link stays the article's main link and the outlet's link is kept beside it. We ask each site at most once a second. If a site asks us to slow down we leave it alone until the next night.

For each outlet we keep dated reach figures. Once a month we look up the web rank of every Libyan outlet and of the 100 busiest outlets in the Tranco list. Web rank says little about Libya, where much of the news is read on Facebook. For ten Libyan outlets it did not line up with their 2023-24 Facebook engagement at all. We also show the outlet's Facebook figures from the 2023-24 social media scrape, marked as historical. Once an outlet has 20 week-old Facebook readings we also show its own median per article over the last eight weeks.

We never rank outlets against each other by engagement. Raw counts differ hugely. Links from some outlets are posted on Facebook dozens of times each, so their totals dwarf the rest. A count only means something next to the same outlet's usual figure.

Some things we chose not to collect. Bluesky, Reddit, Hacker News and X either barely carry Libyan news or charge for access. SharedCount sells the same Facebook numbers we can read ourselves. Some outlet sites show view counters, but they are easy to game, and on some sites reading the counter adds a view. We never call those. Telegram views would mean scraping public channel pages, and few Libyan outlet channels link their articles, so we left it for now. There is no engagement score in the gap figures yet. It needs at least eight weeks of Facebook readings to compare against.

## When the numbers update

- Hourly: outlet feeds and Google Alerts, then scores and the network for the last 12 weeks.
- Every six hours: Google News, GDELT articles and the official statements.
- Nightly: Wikipedia page views, then the full history of scores and the network.
- Mondays: the digest.
- Monthly: web ranks for outlets.
- By hand only: the GDELT long-run line and anything in the backfill job.
