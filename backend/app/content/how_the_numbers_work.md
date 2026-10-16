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

We work out how many articles the theme would get if coverage kept pace with need. That is the expected number. Then we compare it with the articles we counted.

- For the audience lens the expected number comes from the same theme's own record over the 12 weeks before. If a theme usually got 1 article for every 100 page views and this window had 3,000, we expect 30 articles. So the gap says "fewer articles for the interest than usual for this topic". It finds changes. A theme that has always had too little coverage looks normal here, and a shortfall that lasts more than about three months becomes the new usual.
- For the other lenses the expected number uses the average across all themes nationally. For a district it uses that theme's national figure. So the gap says "fewer articles per report or event than other topics get".

Before comparing we add 5 articles to both sides. A theme expecting 8 articles that got 1 then reads as 13 against 6, about 2.2 times fewer. Without this, one missing article in a small theme would look like a collapse. The 5 is counted in articles, so it weighs the same on every lens and every theme, however popular its Wikipedia pages are. The gap is shown as how many times fewer articles there are than expected. The small Trends charts flag a gap from about 1.5 times fewer. Elsewhere anything under about 1.15 times is shown as covered about as expected.

A cell is not judged, and shows as hatched, in four cases.

- The week is still coming in. That is always true of the current week. Wikipedia also gives us page views a day or two late, so on the audience lens a week is only judged once most of its Wikipedia articles have page views for the Sunday. For such a week we stop counting articles on the last day we have page views for, so both sides cover the same days. If the page views are still short a week after that Sunday, we stop waiting. The week is then judged on the days we have, cut the same way, and the cell says its need data stops before the week ends.
- We are still building its baseline. The window or the 12 weeks before it reach back to before we started collecting, which was January 2019.
- There is no need data. On the audience lens that means no Wikipedia page views for the theme.
- Fewer than 3 articles are expected. Then even no articles at all could be chance.

A Wikipedia article listed under two themes counts for both. One day of page views counts for at most five times the article's usual day, which is the middle value of the 28 days before it. That stops a one-day burst of automated traffic from passing as interest. We keep the real count, so this can be undone.

We only count outlets we were collecting from across the whole span being compared, through the same route. For the last year, which is what the Trends page shows, the span runs from 15 weeks before the first week shown to the last full week. Every week in that year is scored on the same outlets as the Trends bars. Older weeks use the 16 weeks of their own comparison. An outlet still counts if it went quiet for up to two weeks at the end. So Al Wasat through Google News counts, because we have years of it. Al Wasat through its own feed only started in October, so it is left out. The same goes for Google Alerts and for outlets Google News only turns up for recent weeks. The backfill is never used in these comparisons. How much it holds for a week depends on how many stories the monitoring review chose to cite, and that grew through the year. The gap panel and the article lists still show every article.

## Flags on a cell

- Coverage dropped. Coverage fell by more than half compared with the previous four weeks while need stayed about the same. Both windows are counted on the same outlets, so an outlet or feed starting or stopping does not trigger it.
- Little Arabic. Less than a fifth of the articles are in Arabic.
- Only covered from outside. No Libyan outlet covered it, only international or diaspora ones.
- One side only. Every outlet with a known political alignment that covered it is on the same side. This uses our own alignment labels, never the ones from the social media scrape.
- Mostly unplaced. More than 80% of the articles name no place, so the regional picture is weak.

## Trends page

The small charts count articles per week for each theme over the last 52 full weeks, plus the week still coming in. The axis is in articles. The bars only count the outlets we have followed all through that year, as described above. Clicking a bar lists the articles in it, and the list adds up to the bar. The note under the charts says how many outlets that is.

The grey line is the usual level for the theme. It is the number of articles the gap score expects that week, worked out from the theme's own record and its Wikipedia reading. Each week uses the baseline of its own score, and baselines move a little from week to week. So the four weeks a verdict covers are drawn on that verdict's baseline, and their four steps add up to the usual level it quotes. That is the latest full week until you point at another one. Where a theme has no Wikipedia articles linked to it, or we are still building its baseline, there is no line. The verdict for the last four weeks is the gap score itself, with the same numbers. From about 1.5 times fewer articles than usual it turns red. From about 1.5 times more it says so, without the red.

Google News finds more for recent weeks than for older ones when we search back, so the bars run higher towards the right. The usual level comes from the weeks before, so it lags behind this rise. Recent weeks can look better covered than they were. GDELT counts for economy stayed flat over the same months, so most of that rise comes from how much we find.

The monthly bars count articles per month, coloured by how they reached us: Google News, outlet feeds, the backfill, Google Alerts or elsewhere. The tooltip gives the split by language. The current month is hatched because it is not over yet. Older months come from searching back, which finds fewer articles, so look at the ups and downs between years. The totals don't compare. 2026 is fuller because of the backfill, but even there the backfill follows what one monitoring service picked. Outlet feeds only hold their latest items, so they add a lot to the months since we started reading them.

The long-run line comes from GDELT. It counts articles worldwide that mention the theme and Libya, using its own English translations. It does not depend on what we collect, which makes it the fairest long view. Each point is the average of the days we have among the last 7. A day GDELT did not give us leaves a break in the line. GDELT often refuses our requests. So we ask for one theme at a time and wait longer after each refusal before trying again. After three refusals in a row the run stops, and the Wikipedia page views work the same way. The line is also only refreshed when an admin runs the backfill job, so it can be weeks old.

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

The digest covers the week that ended on Sunday. Wikipedia gives us Sunday's page views a day or two late. If they are not in on Monday morning, that run covers the latest complete week instead, which usually has its digest already. The digest then tries again each morning up to Thursday, and on Thursday it goes ahead with what it has.

## When the numbers update

- Hourly: outlet feeds and Google Alerts, then scores and the network for the last 12 weeks.
- Every six hours: Google News, GDELT articles and the official statements.
- Nightly: Wikipedia page views, then the full history of scores and the network.
- Mondays: the digest.
- By hand only: the GDELT long-run line and anything in the backfill job.
