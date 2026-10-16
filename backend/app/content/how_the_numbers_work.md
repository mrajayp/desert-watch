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

## The theme model

Word lists miss stories and catch the wrong ones. So we also use a model that learned from our own articles which words go with which theme. It reads the headline and the summary and gives each theme a score from 0 to 1. Each theme has its own bar, set where the model did best on labelled articles.

For the six main themes an article counts when the word list matches or the score passes the bar. The model can add a theme. It never takes away one the word list found. For the gender themes the word lists still decide. The model may only switch off a word-list match for a gender theme once people have labelled at least 100 articles, with 10 or more of them about that theme. On those labels it also has to do at least as well as the word list. Labels from the October review do not count for this. An AI made them, and in our checks letting the model switch off gender matches lost some real gender stories.

People label articles by marking every theme an article is about and whether it is about Libya. A label on one copy of a story covers its other copies. We started with 532 articles that an AI labelled in a blind review in October 2026. They train the model and set the bars for the six main themes.

Each night we retrain the part of the model that learns from labels. Every version is scored on the October review articles, and each article is scored by a copy of the model that did not learn from it. A new version goes live only if its score for the six main themes is no more than 0.01 below the live version's. If it would switch off gender matches, it must also do as well as the live version on people's labels.

Admins can see every version and switch to any of them. A version switched on by hand stays live. The nightly retrain keeps checking new versions but leaves them off until an admin picks one or lets nightly updates take over again. Old nightly versions that nobody picked lose their file after five newer ones, so they can no longer be switched on. Nothing changes until a version is made live.

On the October 2026 labels the model with the word lists made fewer wrong matches for the six main themes than we had before. It found about as many of the right ones as before.

## Need

Need is the other side of the comparison. It is what suggests a topic should be getting coverage. We have five kinds, one per lens.

- The audience lens uses Wikipedia page views for articles linked to each theme. National only.
- The search lens uses Google searches from people in Libya for each theme's words. National only. See Search interest below.
- The humanitarian lens uses ReliefWeb reports on Libya, matched to themes by the same words.
- The events lens will use conflict and protest events from ACLED and UCDP. It stays empty until the keys arrive.
- The journalists lens counts gaps people flag in the app, one unit each.

## The gap score

Each cell is one theme, one place and one week, for one lens. It looks at the four weeks ending that week.

We work out how many articles the theme would get if coverage kept pace with need. That is the expected number. Then we compare it with the articles we counted.

- For the audience and search lenses the expected number comes from the same theme's own record over the 12 weeks before. If a theme usually got 1 article for every 100 page views and this window had 3,000, we expect 30 articles. So the gap says "fewer articles for the interest than usual for this topic". It finds changes. A theme that has always had too little coverage looks normal here, and a shortfall that lasts more than about three months becomes the new usual.
- For the other lenses the expected number uses the average across all themes nationally. For a district it uses that theme's national figure. So the gap says "fewer articles per report or event than other topics get".

Before comparing we add 5 articles to both sides. A theme expecting 8 articles that got 1 then reads as 13 against 6, about 2.2 times fewer. Without this, one missing article in a small theme would look like a collapse. The 5 is counted in articles, so it weighs the same on every lens and every theme, however popular its Wikipedia pages are. The gap is shown as how many times fewer articles there are than expected. The small Trends charts flag a gap from about 1.5 times fewer. Elsewhere anything under about 1.15 times is shown as covered about as expected.

A cell is not judged, and shows as hatched, in four cases.

- The week is still coming in. That is always true of the current week. Wikipedia also gives us page views a day or two late, so on the audience lens a week is only judged once most of its Wikipedia articles have page views for the Sunday. For such a week we stop counting articles on the last day we have page views for, so both sides cover the same days. If the page views are still short a week after that Sunday, we stop waiting. The week is then judged on the days we have, cut the same way, and the cell says its need data stops before the week ends.
- We are still building its baseline. The window or the 12 weeks before it reach back to before we started collecting, which was January 2019.
- There is no need data. On the audience lens that means no Wikipedia page views for the theme. On the search lens it means Google gave no data for one of the window's four weeks.
- Fewer than 3 articles are expected. Then even no articles at all could be chance.

A Wikipedia article listed under two themes counts for both. One day of page views counts for at most five times the article's usual day, which is the middle value of the 28 days before it. That stops a one-day burst of automated traffic from passing as interest. We keep the real count, so this can be undone.

We only count outlets we were collecting from across the whole span being compared, through the same route. For the last year, which is what the Trends page shows, the span runs from 15 weeks before the first week shown to the last full week. Every week in that year is scored on the same outlets as the Trends bars. Older weeks use the 16 weeks of their own comparison. An outlet still counts if it went quiet for up to two weeks at the end. So Al Wasat through Google News counts, because we have years of it. Al Wasat through its own feed only started in October, so it is left out. The same goes for Google Alerts and for outlets Google News only turns up for recent weeks. The backfill is never used in these comparisons. How much it holds for a week depends on how many stories the monitoring review chose to cite, and that grew through the year. The gap panel and the article lists still show every article.

## Flags on a cell

- Coverage dropped. Coverage fell by more than half compared with the previous four weeks while need stayed about the same. Both windows are counted on the same outlets, so an outlet or feed starting or stopping does not trigger it.
- Little Arabic. Less than a fifth of the articles are in Arabic.
- Only covered from outside. No Libyan outlet covered it, only international or diaspora ones.
- One side only. Every outlet with a known political alignment that covered it is on the same side. This uses our own alignment labels, never the ones from the social media scrape.
- Mostly unplaced. More than 80% of the articles name no place, so the regional picture is weak.

## Search interest

The search lens uses Google Trends. Google gives an index from 0 to 100 for each week, scaled to the busiest week in the request. It never says how many searches there were. So we ask for each theme's words next to an everyday word that belongs to no theme, «مطعم» (restaurant). Each week is stored as searches for the theme's words per 100 searches for the everyday word. We use the everyday word's usual level over the 13 weeks around that week, so one odd week for «مطعم» does not move every theme. That matters in Ramadan, when far fewer people search for restaurants.

It only counts people using Google from Libya. Google handles about 98% of web searches there and about 88% of people are online (StatCounter and DataReportal, 2026). Everyone else is missing.

Each theme has a handful of its own Arabic words, listed in the gap panel, and those words set the size of the number. Change the words and the number changes. That is why we only compare a theme with its own past. A word sits in one theme's list only, so one search never counts for two themes. Words also catch things we don't mean. «الانتخابات» (elections) peaks with the Turkish and US elections, so governance uses the names of Libyan institutions instead.

A rise means more people looked something up. It does not tell us they were worried. Many electricity searches are people topping up a meter or checking the load shedding times.

Google holds back any week with too few searches. Migration and every gender theme fall below that line for their whole word list, so we can't measure them here. For security the Libyan words fall below it in about half of all weeks, and the general ones mostly follow news from abroad, so security is left out too. Governance lacks data in a few weeks. A four-week window that includes one of them is not scored. When such a week falls in the 12 weeks we compare against, it counts at the typical level of the weeks around it.

Google draws these numbers from a share of all searches and revises the latest two weeks. We mark those two weeks as provisional and replace them at the next import. A week only gets search data at the first import after it ends, so the search lens opens on the latest week it could score.

When something happens people look it up, and reporters write about it at the same time. So a gap here means searches rose and coverage did not keep up. It does not prove that nobody reported it.

Google changed how it collects this data on 1 January 2022. Earlier weeks don't compare, so we start there. In July and August 2026 searches for the services words ran about twice the rest of the year. From 2022 to 2025 the summer rise was 10 to 25%, so summer 2026 was unusual. Economy searches came close to doubling in Ramadan 2026 against the weeks before, and the biggest economy gaps sit there. Earlier Ramadans showed little or no rise.

We fetch the data about once a week on a computer outside the server and load it by hand. Google marks these requests as automated, so we keep them slow and few. The official Google Trends API is still a closed trial. We have also built a route through SerpApi, a paid service. It stays switched off because Google is suing SerpApi over how it collects Google's results. If no import arrives for 10 days the source strip marks the search data as stale.

Data source: Google Trends.

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

Votes and corrections are saved as labels for training. So are article ratings. Theme labels train the theme model described above. Votes and ratings do not change the rankings yet.

The classifier queue picks recent unlabelled articles whose score sits closest to a theme's bar, plus a few the word lists may have got wrong. Label this on any article row does the same job. Each theme on a row also says why it is there: the word that matched, the search that found it, the model's score or a person's label.

## Weekly digest

Once a week we work out the facts here first. These are the biggest gaps with their flags, plus a few headlines. Only those facts go to the AI model, and it is told to use no number that is not in them. The facts are saved with the text so any claim can be checked. It needs the Anthropic key to run. The digest covers the week that ended on Sunday. Wikipedia gives us Sunday's page views a day or two late. If they are not in on Monday morning, that run covers the latest complete week instead, which usually has its digest already. The digest then tries again each morning up to Thursday, and on Thursday it goes ahead with what it has.

## Engagement

Engagement is how much attention an article got after it came out. We measure two things per article and keep a few dated figures per outlet.

Story pickup is the number of outlets that ran the same story. We use the headline match from the reprint arrows. Most of the words match and the articles appeared within two days of each other. It is worked out whenever the network updates, for the last 12 weeks. Rewritten and translated versions are missed, so it undercounts. Most stories only ever appear in one outlet. Close to nine in ten articles in the last 12 weeks were single-outlet stories. Link shorteners like t.co are left out because they are not outlets.

Facebook engagement is the total that Facebook reports for an article's link. Hover over it to see the breakdown. We read it about two days after the article came out and again after about a week. The week-old reading is the one we trust most. Facebook says its counts are approximate on purpose, so we show them rounded with a ≈ sign. This needs an app ID and secret from a Meta developer account. Until both are set the source shows as waiting for its key. We read at most 400 links a day. If Facebook says we are asking too often we stop and try again six hours later. We skip LANA because its links drew no Facebook posts at all in the 2023-24 scrape.

Facebook can only match the outlet's own link. Google News gives us a redirect link instead, and in October 2026 that was the only link for about 60% of the articles we count. So every night we look for the outlet's own link for Google News articles from the last two weeks. First we look for a copy of the same story from the same outlet that reached us another way, like its feed or Google Alerts. If there is none and the outlet's site runs WordPress, we search the site for the headline. We only accept a result with almost the same headline, published within a day. Daily posts like exchange rates that differ only by a date or weekday never count as a match. The Google link stays the article's main link and the outlet's link is kept beside it. We ask each site at most once a second. If a site asks us to slow down we leave it alone until the next night.

For each outlet we keep dated reach figures. Once a month we look up the web rank of every Libyan outlet and of the 100 busiest outlets in the Tranco list. Web rank says little about Libya, where much of the news is read on Facebook. For ten Libyan outlets it did not line up with their 2023-24 Facebook engagement at all. We also show the outlet's Facebook figures from the 2023-24 social media scrape, marked as historical. Once an outlet has 20 week-old Facebook readings we also show its own median per article over the last eight weeks.

We never rank outlets against each other by engagement. Raw counts differ hugely. Links from some outlets are posted on Facebook dozens of times each, so their totals dwarf the rest. A count only means something next to the same outlet's usual figure.

Some things we chose not to collect. Bluesky, Reddit, Hacker News and X either barely carry Libyan news or charge for access. SharedCount sells the same Facebook numbers we can read ourselves. Some outlet sites show view counters, but they are easy to game, and on some sites reading the counter adds a view. We never call those. Telegram views would mean scraping public channel pages, and few Libyan outlet channels link their articles, so we left it for now. There is no engagement score in the gap figures yet. It needs at least eight weeks of Facebook readings to compare against.

## When the numbers update

- Hourly: outlet feeds, YouTube channels and Google Alerts, the theme model on new articles, then scores and the network for the last 12 weeks.
- Every six hours: Google News, GDELT articles and the official statements.
- Nightly: Wikipedia page views, the social media posts Google has indexed, the outlets' own links for Google News items and a retrain of the theme model on new labels, then the full history of scores and the network.
- Mondays: the digest.
- About once a week, by hand: Google searches for the search lens.
- Monthly: web ranks for outlets.
- By hand only: the GDELT long-run line and anything in the backfill job.
