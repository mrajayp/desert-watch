# How the numbers work

This is for admins. It says how each figure in Desert Watch is worked out and where it can mislead you. If something on a page looks odd, start here.

## Articles we count

An article counts as coverage when it mentions Libya or a Libyan place, or comes from a Libyan outlet and matches a theme. Anything else is kept but marked as not relevant.

Articles come from Google News searches, outlet news feeds, Google Alerts, YouTube channels, social media posts that Google indexes and the historical backfill. People can also add them. Every article counts once, whatever its source.

The same story often reaches us twice. Google News gives us its own link, and the outlet's feed or the backfill gives the real one. So we look for articles from the same outlet, published within a day of each other, with almost the same headline. We count one copy and keep the outlet's own link. The others are kept but left out of every number. A Facebook page or YouTube channel that the outlet's website links to counts as the same outlet here, and we keep the website's copy.

Coverage also goes up whenever we add a source. The trend charts and the audience gap allow for this. The monthly bars don't.

## Social media

We collect two kinds of social media posts. Neither needs us to sign up or pay, and both stay within what the platforms allow.

The first is YouTube. We follow nine channels that their outlets' own websites link to, among them Wasat TV, Libya Al Ahrar, HNEC and UNSMIL. Every hour we read each channel's public feed. The feed only lists the 15 newest videos, and YouTube often turns a request away, so we try again a few times. YouTube has its own line under Data sources in Admin. When YouTube refuses us for hours on end that line shows an error, and the website feeds carry on as normal. A channel takes the scope of the website that links to it.

The second is posts that Google News has indexed. This covers the Facebook pages on the 2023-24 social media scrape register, plus any Facebook, X, Instagram or TikTok account we have given a type or scope. Each night we ask Google News for each account's posts from yesterday, and again for the day before, because Google adds posts late. We ask the Arabic edition for every account. When the account or its website publishes in English we ask the English edition as well, because each edition mostly keeps to its own language. Google keeps only some posts, mostly recent ones, and never gives more than 100 for one day. So this is a sample of what a page posts and it misses a lot. These posts show as "Social (Google-indexed)" and count as coverage like any article. Comparisons over time leave each account out until we have collected it for the whole period compared.

A post from a Libyan page counts when it matches a theme, even if it names no place in Libya. That is the same rule we use for Libyan websites. Most of these posts are Libyan news that takes the place for granted. Libyan pages also share world news, so a few posts about other countries count too.

We don't read Telegram. We don't scrape Facebook or X ourselves either. Telegram's terms ban scraping for AI use, and Libyan channels there are small. X charges for every post we would read. Facebook and Instagram only open page data to apps that pass Meta's review, and we have not applied. Paid scraping services would be a separate decision.

We try to keep posts from private people out of the numbers. A social account only counts once it is on the register or someone has given it a type or scope in Admin. Posts filed under a whole platform, like facebook.com with no page, never count, because we can't tell whose they are. The same goes for sites where anyone can post, such as LinkedIn and Reddit. Link shorteners such as t.co and bit.ly are not outlets, so their items don't count either. This applies to the historical backfill too. We keep all of these. Labelling an account brings its posts back on the next hourly run.

## Themes and places

A theme is a list of words in Arabic and English. If a headline contains one of the words, the article gets that theme. A summary on its own needs two of the words. Some themes need two sets of words close together, for example women plus violence. A few words do not count when certain other words are in the story. "Killed" in a story about a crash or a flood does not put it under security. When a search or a Google Alert finds an article for a theme, we keep that as a hint. It only counts when the words are really in the text. For Google Alerts we only read the parts of the summary that match the headline, because the rest is often menus and links from the page.

Places work the same way. We look for district and town names, including other spellings. We skip the town a news agency puts at the start of a story, because that is where it filed from. Most articles do not name a place below Libya, so they only count nationally. That is normal and is why the regional numbers are much smaller.

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

## When the numbers update

- Hourly: outlet feeds, YouTube channels and Google Alerts, then scores and the network for the last 12 weeks.
- Every six hours: Google News, GDELT articles and the official statements.
- Nightly: Wikipedia page views and the social media posts Google has indexed, then the full history of scores and the network.
- Mondays: the digest.
- By hand only: the GDELT long-run line and anything in the backfill job.
