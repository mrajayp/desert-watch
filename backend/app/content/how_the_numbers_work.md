# How the numbers work

This is for admins. It says how each figure in Desert Watch is worked out and where it can mislead you. If something on a page looks odd, start here.

## Articles we count

An article counts as coverage when it mentions Libya or a Libyan place, or comes from a Libyan outlet and matches a theme. Anything else is kept but marked as not relevant.

Articles come from Google News searches, outlet news feeds, Google Alerts, YouTube channels, social media posts that Google indexes and the historical backfill. People can also add them. Every article counts once, whatever its source.

The same story often reaches us twice. Google News gives us its own link, and the outlet's feed or the backfill gives the real one. So we look for articles from the same outlet, published within a day of each other, with almost the same headline. We count one copy and keep the outlet's own link. The others are kept but left out of every number. A story found by two routes, say Google News and the outlet's feed, counts once, and it counts in the comparisons over time when either route is one we compare. A Facebook page or YouTube channel that the outlet's website links to counts as the same outlet here, and we keep the website's copy.

Coverage also goes up whenever we add a source. The Trends charts and every gap score allow for this. The monthly bars don't.

## Social media

We collect two kinds of social media posts. Neither needs us to sign up or pay, and both stay within what the platforms allow.

The first is YouTube. We follow nine channels that their outlets' own websites link to, among them Wasat TV, Libya Al Ahrar, HNEC and UNSMIL. Every hour we read each channel's public feed. The feed only lists the 15 newest videos, and YouTube often turns a request away, so we try again a few times. YouTube has its own line under Data sources in Admin. When YouTube refuses us for hours on end that line shows an error, and the website feeds carry on as normal. A channel takes the scope of the website that links to it.

The second is posts that Google News has indexed. This covers the Facebook pages on the 2023-24 social media scrape register, plus any Facebook, X, Instagram or TikTok account we have given a type or scope. Each night we ask Google News for each account's posts from yesterday, and again for the day before, because Google adds posts late. We ask the Arabic edition for every account. When the account or its website publishes in English we ask the English edition as well, because each edition mostly keeps to its own language. Google keeps only some posts, mostly recent ones, and never gives more than 100 for one day. So this is a sample of what a page posts and it misses a lot. These posts show as "Social (Google-indexed)" and count as coverage like any article. Comparisons over time leave each account out until we have collected it for the whole period compared.

A post from a Libyan page counts when it matches a theme, even if it names no place in Libya. That is the same rule we use for Libyan websites. Most of these posts are Libyan news that takes the place for granted. Libyan pages also share world news, so a few posts about other countries count too.

We don't read Telegram. We don't scrape Facebook or X ourselves either. Telegram's terms ban scraping for AI use, and Libyan channels there are small. X charges for every post we would read. Facebook and Instagram only open page data to apps that pass Meta's review, and we have not applied. Paid scraping services would be a separate decision.

We try to keep posts from private people out of the numbers. A social account only counts once it is on the register or someone has given it a type or scope in Admin. Posts filed under a whole platform, like facebook.com with no page, never count, because we can't tell whose they are. The same goes for sites where anyone can post, such as LinkedIn and Reddit. Link shorteners such as t.co and bit.ly are not outlets, so their items don't count either. This applies to the historical backfill too. We keep all of these. Labelling an account brings its posts back on the next hourly run.

## Themes and places

A theme is a list of words in Arabic and English. If a headline contains one of the words, the article gets that theme. A summary on its own needs two of the words. Some themes need two sets of words close together, for example women plus violence. A few words do not count when certain other words are in the story. "Killed" in a story about a crash or a flood does not put it under security. When a search or a Google Alert finds an article for a theme, we keep that as a hint. It only counts when the words are really in the text. For the six main themes the theme model can also make it count. For Google Alerts we only read the parts of the summary that match the headline, because the rest is often menus and links from the page.

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
- For the other lenses the expected number uses the average across the themes with need data nationally. For a district it uses that theme's national figure. So the gap says "fewer articles per report or event than other topics get".

Before comparing we add 5 articles to both sides. A theme expecting 8 articles that got 1 then reads as 13 against 6, about 2.2 times fewer. Without this, one missing article in a small theme would look like a collapse. The 5 is counted in articles, so it weighs the same on every lens and every theme, however popular its Wikipedia pages are. The gap is shown as how many times fewer articles there are than expected. Whether it is red is decided by the test in the next section, not by its size alone.

A cell is not judged, and shows as hatched, in six cases.

- The week is still coming in. That is always true of the current week. Wikipedia also gives us page views a day or two late, so on the audience lens a week is only judged once most of its Wikipedia articles have page views for the Sunday. For such a week we stop counting articles on the last day we have page views for, so both sides cover the same days. If the page views are still short a week after that Sunday, we stop waiting. The week is then judged on the days we have, cut the same way, and the cell says its need data stops before the week ends.
- We are still building its baseline. The window or the 12 weeks before it reach back to before we started collecting, which was January 2019.
- There is no need data. On the audience lens that means no Wikipedia page views for the theme. On the search lens it means Google gave no data for one of the window's four weeks.
- There is too little need to compare with other topics. On the humanitarian lens that means fewer than 2 reports in the window, and on the events lens fewer than 3 events.
- Fewer than 3 articles are expected. Then even no articles at all could be chance.
- The cell has a gap but no verdict: the theme's week-to-week swing rests on fewer than 8 weeks of history, or the margin on the shortfall is wider than 4 times either way. See the next section.

A Wikipedia article listed under two themes counts for both. One day of page views counts for at most five times the article's usual day, which is the middle value of the 28 days before it. That stops a one-day burst of automated traffic from passing as interest. We keep the real count, so this can be undone.

We only count outlets we were collecting from across the whole span being compared, through the same route. For the last year, which is what the Trends page shows, the span runs from 15 weeks before the first week shown to the last full week. Every week in that year is scored on the same outlets as the Trends bars. Older weeks use the 16 weeks of their own comparison. An outlet still counts if it went quiet for up to two weeks at the end. So Al Wasat through Google News counts, because we have years of it. Al Wasat through its own feed only started in October, so it is left out. The same goes for Google Alerts and for outlets Google News only turns up for recent weeks. The backfill is never used in these comparisons. How much it holds for a week depends on how many stories the monitoring review chose to cite, and that grew through the year. The gap panel and the article lists still show every article.

## How we decide a cell is short

A shortfall is shown in red only when it is larger than chance would explain. Article counts swing from week to week even when nothing has changed, and a small theme swings more than a large one. So each cell gets a verdict as well as a gap: short, possibly short, usual, over or unclear. The pages colour a cell red only for short, give possibly short a pale tint, leave usual plain and give over a blue tint. Unclear shows as not judged.

The verdict rests on four steps.

- Dispersion. For each theme and lens we measure how much its weekly count swings around its expected level, over its last 52 complete weeks. The measure is the extra variance beyond a plain count, kept between 0.02 and 2, and it is pulled towards the median of the lens's themes so that one odd theme does not set its own rules. A theme with fewer than 12 usable weeks takes the lens-wide value. The value is stored with the cell as alpha, with the number of weeks it rests on.
- The chance of the count. From the expected number, the dispersion and the uncertainty in the baseline itself, we work out how likely a count this low (or this high) would be if nothing had changed. The cell stores both tails, p_low and p_high. The pages show the one the cell leans to as "happens by chance about once in N such weeks", with N rounded to 10, 20, 50, 100, 200, 500 or 1000, and 1000 means once in 1000 or rarer. Past 1 in 5 the page says the difference could easily be chance.
- The interval. The gap is still ln((expected + 5) / (articles + 5)), shown as "N times fewer". Around it we give a 90% interval under the same variance model as the chance, shown as "likely 1.8 to 3.6 times fewer". The interval and the chance agree with each other by construction.
- The decision, per lens and week. Across the national cells of one lens and week (and the district cells of each level as their own group) we control the false-discovery rate at 10% with the Benjamini-Hochberg rule. A cell is short when it passes that rule on p_low and the shortfall is at least 1.5 times. It is over when it passes on p_high and there are at least 1.5 times more articles. It is possibly short when p_low is under 0.10 but it did not pass the rule. Otherwise it is usual.

The practical floor matters. A theme with 400 expected articles that got 350 may be short beyond any doubt, but it is not a story, so it reads usual. The 10% rate means that among the red cells on a page about 1 in 10 is still chance, and the pages say so. The 4-week windows overlap, so a short cell is usually short for several weeks in a row. The digest calls a gap new only in the first week it is short.

Collection drift widens the margin. Google News finds fewer articles for a week the longer ago it was when we search for it, so an expected level built on weeks we searched back for runs low. Where any of a cell's 12 baseline weeks was collected that way, the cell is flagged and its interval is widened by the measured drift (about 0.12 in the log, 8 weeks of lag at 1.5% a week). The verdict does not move with the flag, only the margin the page quotes. The Sunday job that searches Google News again for the weeks aged 2, 3 and 4 keeps new weeks out of this state.

A cell with a gap has no verdict, and shows as not judged, in two cases: its dispersion rests on fewer than 8 weeks, or its interval is wider than 4 times either way, so the margin says nothing. The verdict is also unclear when fewer than 3 articles are expected, as before.

A simulation test (tests/test_stats_simulation.py) checks the rule on 13 themes over 104 weeks of overdispersed counts: a false red in under 3% of lens-weeks on steady data. Its power against a lone 2x four-week drop is modest, from a third to two thirds for a steady theme expecting 30 to 250 articles, and small for a theme that swings a lot. The rule is built to keep the reds honest, not to catch every drop.

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

The grey line is the number of articles the gap score expects for the theme that week. On the audience and search lenses it is the theme's usual level. That comes from the theme's own record and the lens's need data, for example its Wikipedia reading. On the other lenses it comes from what other topics get for the same need. Each week uses the baseline of its own score, and baselines move a little from week to week. So the four weeks a verdict covers are drawn on that verdict's baseline, and their four steps add up to the number it quotes. That is the latest full week until you point at another one. Where the lens has no need data for a theme, or we are still building its baseline, there is no line. The verdict for the last four weeks is the gap score's verdict, with the same numbers. The strip is red only when the shortfall is larger than chance would explain (see How we decide a cell is short), pale when it is possibly fewer, and blue when there are clearly more articles than expected. The pill above the chart carries the same verdict, and its tooltip the counts, the likely range and the chance.

Google News finds more for recent weeks than for older ones when we search back, so the bars run higher towards the right. On the audience and search lenses the line comes from the weeks before, so it lags behind this rise. Recent weeks can look better covered than they were. GDELT counts for economy stayed flat over the same months, so most of that rise comes from how much we find.

The monthly bars count articles per month, coloured by how they reached us: Google News, outlet feeds, the backfill, Google Alerts or elsewhere. The tooltip gives the split by language. The current month is hatched because it is not over yet. Older months come from searching back, which finds fewer articles, so look at the ups and downs between years. The totals don't compare. 2026 is fuller because of the backfill, but even there the backfill follows what one monitoring service picked. Outlet feeds only hold their latest items, so they add a lot to the months since we started reading them.

The long-run line comes from GDELT. It counts articles worldwide that mention the theme and Libya, using its own English translations. It does not depend on what we collect, which makes it the fairest long view. Each point is the average of the days we have among the last 7. A day GDELT did not give us leaves a break in the line. A theme has more words than fit one GDELT request, so each theme is asked in parts of eight words and the daily counts of the parts are added. An article that matches words from two parts is counted twice there, so the line runs a little high rather than low. GDELT often refuses our requests. So we ask for one part at a time, at least six seconds apart, and wait longer after each refusal before trying again. After three refusals in a row the run stops, and the Wikipedia page views work the same way. The line is also only refreshed when an admin runs the backfill job, so it can be weeks old.

Clicking a point on any of these charts lists the articles behind it. For the GDELT line it lists our own articles for that week, because GDELT only gives counts.

## Map and who covers where

The lines join each outlet to the districts its articles name. Line thickness is the number of articles. Outlets based outside Libya sit around the edge by country. Districts are coloured by gap only when the lens has enough need data at district level. Right now none does, so the colours show how much coverage each district gets.

## Coverage clusters

We take the outlets with at least 10 articles in the last 12 weeks, up to 120 of them. For each one we work out which themes it covers more or less than the average outlet. Outlets with similar patterns are linked, and a standard community method splits them into clusters. Each cluster is named after the two themes it over-covers most.

Arrows between clusters are reprints. Two headlines count as the same story when most of their words match and they appeared within two days of each other. The arrow points from the outlet that published first.

## Contribute page

The gap list shows the biggest gaps in the last four weeks that nobody has voted on. The article lists are recent articles with no theme or no place, one unrated article from each busy outlet, and outlets with a lot of articles but no scope or alignment on record.

Votes and corrections are saved as labels for training. So are article ratings. Theme labels train the theme model described above. Votes and ratings do not change the rankings yet.

The classifier queue picks recent unlabelled articles the word lists may have got wrong. When a model is live it also picks the ones whose score sits closest to a theme's bar. Label this on any article row does the same job. Each theme on a row also says why it is there: the word that matched, the search that found it, the model's score or a person's label.

The Ask an AI assistant task gives this week's questions for the AI answers audit and a form for the source links an app showed. AI answers (audit) below says how those entries are used.

## Weekly digest

Once a week we work out the facts here first. These are the biggest gaps with their flags, and the article count for each theme in this window and the one before it, counted the way the gaps count (the outlets and routes we monitored across the whole compared period) beside the count from every source. Each gap goes with its verdict, its likely range and its chance in "1 in N" form, and whether it is new (short this week and not the week before). No headlines go to the model. Only those facts go to the AI model, and it is told to use no number that is not in them, to quote the range and the chance as they are, and to call a gap new only when the facts say so. The facts are saved with the text so any claim can be checked. It needs the Anthropic key to run. The digest covers the week that ended on Sunday. Wikipedia gives us Sunday's page views a day or two late. If they are not in on Monday morning, that run covers the latest complete week instead, which usually has its digest already. The digest then tries again each morning up to Thursday, and on Thursday it goes ahead with what it has.

## Engagement

Engagement is how much attention an article got after it came out. We measure two things per article and keep a few dated figures per outlet.

Story pickup is the number of outlets that ran the same story. We use the headline match from the reprint arrows. Most of the words match and the articles appeared within two days of each other. It is worked out whenever the network updates, for the last 12 weeks. Rewritten and translated versions are missed, so it undercounts. Most stories only ever appear in one outlet. Close to nine in ten articles in the last 12 weeks were single-outlet stories. Link shorteners like t.co are left out because they are not outlets.

Facebook engagement is the total that Facebook reports for an article's link. Hover over it to see the breakdown. We read it about two days after the article came out and again after about a week. The week-old reading is the one we trust most. Facebook says its counts are approximate on purpose, so we show them rounded with a ≈ sign. This needs an app ID and secret from a Meta developer account. Until both are set the source shows as waiting for its key. We read at most 400 links a day. If Facebook says we are asking too often we stop and try again six hours later. We skip LANA because its links drew no Facebook posts at all in the 2023-24 scrape.

Facebook can only match the outlet's own link. Google News gives us a redirect link instead, and in October 2026 that was the only link for about 60% of the articles we count. So every night we look for the outlet's own link for Google News articles from the last two weeks. First we look for a copy of the same story from the same outlet that reached us another way, like its feed or Google Alerts. If there is none and the outlet's site runs WordPress, we search the site for the headline. We only accept a result with almost the same headline, published within a day. Daily posts like exchange rates that differ only by a date or weekday never count as a match. The Google link stays the article's main link and the outlet's link is kept beside it. We ask each site at most once a second. If a site asks us to slow down we leave it alone until the next night.

For each outlet we keep dated reach figures. Once a month we look up the web rank of every Libyan outlet and of the 100 busiest outlets in the Tranco list. Web rank says little about Libya, where much of the news is read on Facebook. For ten Libyan outlets it did not line up with their 2023-24 Facebook engagement at all. We also show the outlet's Facebook figures from the 2023-24 social media scrape, marked as historical. Once an outlet has 20 week-old Facebook readings we also show its own median per article over the last eight weeks.

We never rank outlets against each other by engagement. Raw counts differ hugely. Links from some outlets are posted on Facebook dozens of times each, so their totals dwarf the rest. A count only means something next to the same outlet's usual figure.

Some things we chose not to collect. Bluesky, Reddit, Hacker News and X either barely carry Libyan news or charge for access. SharedCount sells the same Facebook numbers we can read ourselves. Some outlet sites show view counters, but they are easy to game, and on some sites reading the counter adds a view. We never call those. Telegram views would mean scraping public channel pages, and few Libyan outlet channels link their articles, so we left it for now. There is no engagement score in the gap figures yet. It needs at least eight weeks of Facebook readings to compare against.

## Signals from outside the news

The Trends page shows a few daily numbers next to coverage. We never score them. Each has its own scale, and we never put one on the same axis as articles.

Wikimedia publishes, for each country, the Wikipedia pages read from there on a day. It only lists a page on days it has more than about 90 views from that country, and it adds noise of about 35 views to protect readers. For Libya that leaves 10 to 30 pages a day. Most are the main pages, football and pages we leave out.

We keep two things from it. The first is how often people in Libya read the page on the central bank's currency booking platform, and the page on the central bank itself. These are signs of how much people are dealing with getting foreign currency. The second is the list of Libya pages read from Libya each day, which the Timeline page shows. On most days it holds one or two pages. On days when something happens it fills up, for example with Derna and its dams after the flood, or with Abdel Ghani al-Kikli after the Tripoli clashes. We only keep pages that name Libya or one of its places, public figures and institutions on a short list, and pages a theme follows. A gap in a line means the page had fewer than about 90 views that day.

The card also shows the dinar's exchange rates. The parallel rate is what traders in Tripoli's market charge for a dollar or a euro in cash. We take it from Al-Mashhad al-Libi, which posts the price every day. We use the evening close where there is one and the midday price otherwise. Other outlets repeat the same figures, and when we checked them against each other on the same days they agreed to within a few hundredths of a dinar. The price by bank cheque is a separate line, because it usually costs a little more. The official rate is the Central Bank of Libya's average of its buying and selling price. From 18 January 2026 the official rate includes the 15% tax on buying foreign currency, so it jumps that week. For the years before late 2023 the parallel line comes from the rate box on the Libya Observer website, as the Internet Archive saved it. That box was only updated now and then, so the older line is patchy. We never use prices.ly, whose figures are read automatically from a dealers' WhatsApp group and whose terms do not allow collecting them.

## AI answers (audit)

This audit checks what AI assistants tell people who ask about Libya, and which sources they lean on. It is never part of a gap score, a lens, the Trends page or the digest. It writes only to its own tables and never adds articles or outlets.

The answers reach us in three ways. Each is counted on its own, and we never put two of them in one figure.

- Once a week the server asks the questions through the developer APIs of three assistants. These are the automatic answers.
- Journalists on the team ask the same questions in the app they use on their own phone. They log the source links the answer showed.
- In a browser session the owner signs in to a chatbot in a browser in London. Claude, working in that browser, types in the questions while the owner watches.

The automatic run is on Monday at 04:20 UTC. It asks the same 8 questions in Arabic and in English. The question set has one question for each of the six main themes, one on women's rights and one asking for the latest news from Kufra. The questions name no person and don't assume a crisis. They never ask the assistant to cite anything or to use particular sources, because that changes which outlets turn up. Each answer records which wording of the question it got. The team and the browser sessions use the same 8 questions.

The automatic run asks three assistants. Claude goes through Anthropic's developer API, ChatGPT through OpenAI's and Perplexity through Perplexity's. Each uses its own web search, with at most 2 searches per question. Every question starts a new conversation. The only instruction is one line giving today's date, which the questions about this week and this month need. We don't limit which sites the search may use. The location is set to Tripoli, Libya. OpenAI assumes the United States when it is not told. If Anthropic turns down Libya as a country we send the city and time zone only. Perplexity has no time zone setting, and if it turns down Libya we send the city and region only. Our server is in London, and no provider says whether that changes the results. Each run records the location it sent, the model it used and the server's region.

ChatGPT brings about 60% of the visits that chatbots send to websites from Libya. Perplexity brings about 4% and Claude about half of one per cent (StatCounter, September 2026). We ask Claude as well because the digest already uses its key. ChatGPT and Perplexity each need a key of their own. Until the owner sets one, that assistant's line under Data sources in Admin shows it waiting for its key. Each assistant has its own line there, and it turns stale when no run has finished for 8 days.

For each answer we keep the searches the assistant ran and every result its search returned. Separately we keep the links the answer cites, with how many times it cites each one. An assistant can be shown 20 results and cite 3, so the two are never mixed. OpenAI gives only the web address of each result, with no title. Perplexity marks the results an answer used only when the question asks for such marks, and ours never do. So we keep Perplexity's cited links only when an answer carries the marks anyway. Its cited count can be zero even when the answer drew on its results. We also note the language and length of the answer. The answer text itself is never stored, and neither are the quotes Claude takes from the pages it cites. Only admins see the searches, the result titles and the full web addresses, because they can carry the names of private people even when the question names no one. Everyone else sees counts by outlet and by domain.

Each link is matched to the outlet register by its address. A registered section of a site comes first, then the site itself, then its parent domain, so a subdomain counts as the site it belongs to. A post on an outlet's own social account counts as that outlet. A domain that is not on the register is kept with no outlet and shows as not in the register. Admins see a list of these domains with the Libyan ones marked, so they can add the ones that are outlets. The links that the team and the browser sessions log are matched the same way.

Each week the Contribute page shows the 8 questions in Arabic and English, each with a button to copy it. A journalist asks one or more of them in the app they actually use on their own phone. That can be the ChatGPT app, Gemini, Google's AI Overview or AI Mode, Meta AI in WhatsApp, Facebook or Instagram, Copilot, the Perplexity app, the Claude app, Grok, DeepSeek or another app. They paste the source links the answer showed, one per line, or tick no sources shown. They also pick the app, the question, the language they asked in and whether they asked from Libya or from somewhere else. We keep only the web addresses in what they paste, at most 30 per entry, and drop repeats. Each person can log up to 40 entries a week. The answer text is never stored. The form asks people not to paste it, or anything that names a private person.

These links count as cited links, because an app shows the links its answer used. There are no searches and no searched results. An app's answer depends on the account, its memory, the phone and where the person is. So these entries only show what a few journalists saw on their own phones and accounts. It is a small and uneven sample, and one person who logs a lot can fill a week. Nobody else sees who logged an entry. Admins see the links, with the author shown only as a team member. Each person sees their own entries for the week and can delete them. If someone deletes their account, their entries stay in the counts but are no longer linked to them. Their data export includes them.

Browser sessions are run by the owner. They sign in to a chatbot in a browser in London, and Claude types in the questions while they watch. Claude logs only the source links each answer showed, the same way as the team's entries, marked as a browser session asked from London. Only admins can log one. These answers come from a signed-in account in London, so they don't show what people in Libya see. They show what the app itself gives, and that can differ a lot from what its developer API gives.

The Outlets page has a card called What AI assistants cite. A switch at the top picks one of the three ways in, Automatic, Logged by the team or Browser sessions, and the card shows one at a time. For each assistant it shows how many sources an answer searched and how many it cited, as the middle value and the range. It splits the cited sources by scope (Libyan, diaspora, international, unknown or not in the register) and by language, next to the scope of the articles we monitored in the same weeks. These are different units. One counts citations and the other counts articles. The card also gives the language of the assistant's searches, the outlets cited most and the Libyan outlets that no answer cited. That last list covers register outlets with counted articles in the last 12 weeks. It says whether each one at least appeared in the search results. For the team's entries and the browser sessions the card lists apps in place of assistants. It has no searched figures there, because an app only shows the links its answer used. It also counts where those answers were asked from: Libya, elsewhere or London. The outlet panel adds a line saying how often the assistants cited that outlet in the last 4 weeks. That line counts the automatic answers only. We never add the assistants or the apps together, because each one means something different by a result and by a citation. For now only admins see the card and the outlet line, until the owner opens them to the team.

Admin has its own card for the audit. It lists each run with its status, its cost and how its answers reached us. For each automatic answer it shows the searches and the addresses and titles of what was searched and cited. For the team's entries and the browser sessions it shows the links each entry logged, with no searches and no names. It also lists the domains that are not on the register, for one way in at a time, and has a button to run the audit by hand. A dry run shows the planned questions and the estimated cost without asking anything.

The audit may spend at most USD 1 a week for all three assistants together. With all three a week has 48 answers. Claude's and ChatGPT's 32 answers should cost about USD 0.80, mostly search fees, and Perplexity's 16 about USD 0.15. Before each answer the run adds an estimate for that answer to what the week has already spent. If that would pass the cap, the answers still to come are marked over budget and the run stops. The estimate is kept on the high side, so a dry run with all three assistants shows only about 34 of the 48 answers fitting. Real answers cost much less, and a real run usually gets through all or nearly all of them. A full week still comes close to the cap, so in an expensive week the last question or two may go unasked. We go question by question, each one in both languages and for every assistant, so a stop leaves the assistants and the languages covered about evenly. Costs come from the providers' dated price lists. Admin shows the total for the week and for the year. An assistant runs once a week unless an admin forces another run, and a forced run counts towards the same cap. The team's entries and the browser sessions cost the audit nothing and never count towards the cap.

Answers change from run to run even when nothing else does. In other audits two identical runs shared only 13 to 31% of their cited links, and 56 to 74% of the cited domains changed from one week to the next. So the card reads answers over 4 or 12 weeks and looks at whether an outlet turns up at all. Small moves in the list of outlets cited most mean little. Four weeks give 64 automatic answers per assistant, so one outlet never being cited is weak evidence about that outlet. The team's entries are usually far fewer. The card always shows how many answers it rests on.

There is a lot it can't show. The automatic answers come from developer APIs. The ChatGPT and Claude apps add their own instructions, a location from the user's connection, memory and their own choice of model. One study found that the API and the ChatGPT app had only about one link in eight in common. The team's entries and the browser sessions come from the apps themselves, but from a handful of accounts. Google's AI Overviews and AI Mode are probably the AI answers most Libyans see. Google offers no API for them, so only the team and the browser sessions can show them. We don't ask Gemini or Copilot through their developer APIs because their terms forbid storing and analysing the results. Meta's developer API is a US-only preview and Meta restricts Libya. The team can still log what Gemini, Copilot and Meta AI in WhatsApp, Facebook and Instagram show in their apps. The audit also says nothing about whether an answer is true. It counts sources and doesn't grade the answers.

Outlets can ask AI crawlers to stay away in a robots.txt file. On 18 October 2026 we read that file for the 68 Libyan web domains on the register. Of these, 7 block at least one AI crawler, and 4 of those are news outlets. Only 2 block OpenAI's search crawler, Libya Akhbar and almashhadlibya. Perplexity's search crawler is blocked by 3 and Claude's by none. So if Libyan outlets are missing from answers, robots.txt explains little of it. More likely the outlet is missing from the search index the assistant uses, or the assistant simply prefers other sources. Cloudflare can also turn AI crawlers away before they ever read the file, and 27 of the 68 sites answered through Cloudflare. A robots.txt file is only a request. The full survey is in docs/research/ai_crawlers_robots_2026-10-18.md.

## When the numbers update

- Hourly: outlet feeds, YouTube channels, Google Alerts and the theme model on new articles, then scores and the network for the last 12 weeks.
- Every six hours: the Wikipedia pages read in Libya, the dinar's exchange rates, Google News, GDELT articles, the official statements and, once the Meta app is set up, Facebook link readings.
- Nightly: Wikipedia page views, the social media posts Google has indexed, the outlets' own links for Google News items and a retrain of the theme model on new labels, then the full history of scores and the network.
- Mondays: the AI answers audit at 04:20 UTC, then the digest.
- About once a week, by hand: Google searches for the search lens.
- Monthly: web ranks for outlets.
- By hand only: the GDELT long-run line, anything in the backfill job and the AI answers that the team or a browser session logs.
