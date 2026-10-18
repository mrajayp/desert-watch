# Help {#top}

Desert Watch finds the stories about Libya that nobody is covering. Week by week it compares how much the monitored outlets write about each topic with signs that people need that coverage. Where the writing falls well short of the need it shows a gap, with the articles that do exist, so you can judge whether there is a story in it.

## Words used on every page {#glossary}

### Gap {#gap}

How much less coverage a topic got than expected, given the need signal, over four weeks. "About 3 times fewer articles than expected" means the outlets we count wrote a third of what the need suggested. Only a shortfall is shown; more coverage than expected stays neutral.

### Need signal {#need-signal}

What suggests a topic should be getting coverage: Wikipedia reading, Google searches from Libya, humanitarian reports, conflict events, or the gaps the team has flagged. Each lens uses one of them.

### Lens {#lens}

The need signal a page compares coverage with. The five lenses are listed below. A lens says "compared with other topics" when it pools the topics, and "compared with this theme's usual level" when it compares a theme with its own record.

### Monitored coverage {#monitored-coverage}

The articles Desert Watch collects: Google News, outlet feeds, Google Alerts, YouTube channels, social-media posts that Google indexes, and links the team adds. A gap score counts only the outlets we followed all year, so a new source does not look like more coverage. The article lists show everything.

### Expected {#expected}

The number of articles a topic would have if coverage kept pace with the need signal. On every lens the gap is the actual count against this one number.

### Not judged {#not-judged}

A gap or a week the tool could not score, always with the reason: "Not judged · too few events". It is drawn striped. The five reasons are listed under the gap score below. Not judged never means there is no story.

### Week, and "4 weeks to …" {#week}

Weeks run Monday to Sunday. A gap score covers the four weeks ending on the Sunday it names: "4 weeks to 11 Oct 2026". The current week is never judged, because its data is still coming in.

### Theme {#theme}

A topic defined by a list of Arabic and English words: economy, security, services, governance, migration, health, and the gender themes. An article can be about several themes.

### District, region, national {#district}

A district is one of Libya's 22 districts; the regions group them (Tripolitania, Cyrenaica, Fezzan); national is all of Libya. Most articles name no place below Libya, so they count nationally only, and the district numbers are much smaller.

### Warning {#warning}

A note on a gap that changes how to read it: coverage dropped while need held, little Arabic coverage, only outlets outside Libya, only one political side, or most articles name no place. A warning is not a gap by itself.

## What counts as an article {#articles}

An article counts when it mentions Libya or a Libyan place, or comes from a Libyan outlet and matches a theme. Everything else is kept but marked as not relevant. The same story often reaches us twice, for example once through Google News and once through the outlet's own feed. It is counted once, and the outlet's own link is kept. Every article counts once, whatever its source.

## What we see of social media {#social-media}

Two kinds of posts. The first is the public feeds of nine YouTube channels that outlets' own websites link to. The second is posts that Google News has indexed from the Facebook pages and other accounts on our register. Google keeps only some posts and never more than 100 a day for one account, so this is a sample. We do not read Telegram, we do not scrape Facebook or X ourselves, and posts from private people are kept out: an account counts only once it is on the register.

## Themes and places {#themes-and-places}

A theme is a list of words in Arabic and English. A headline with one of the words gets the theme; a summary on its own needs two. Some themes need two sets of words close together, such as women and violence, and some words do not count next to others: "killed" in a story about a crash does not mean security. For the six main themes a model trained on the team's labels can add a theme too; it never removes one. Places work the same way, with district and town names in their spellings. The town a news agency puts at the start of a story is skipped, because that is where it filed from.

## The five lenses {#lenses}

- International readers (Wikipedia): worldwide page views of the Wikipedia articles picked for each theme, against the theme's own recent record. National only.
- Libyan searches (Google): Google searches from people in Libya for each theme's words, against the theme's own record. National only. See Search interest below.
- Humanitarian: ReliefWeb reports on Libya, matched to themes by the same words, compared with other topics.
- Events: conflict and protest events from ACLED and UCDP, compared with other topics. Empty until the access keys arrive.
- Journalists: gaps the team has flagged in the app, one unit each, compared with other topics.

## The gap score {#gap-score}

Each score is one theme, one place and one lens, over the four weeks ending on a Sunday. We work out how many articles the theme would get if coverage kept pace with the need signal. That is the expected number. Then we compare it with the articles counted from the outlets we followed all year. On the Wikipedia and searches lenses the expected number comes from the same theme's own record over the 12 weeks before, so the gap finds changes: a topic that has always been thinly covered looks normal there. On the other lenses it comes from what other topics get for the same need. Before comparing we add 5 articles to both sides, so one missing article in a small topic does not look like a collapse. The gap is shown as how many times fewer articles there are than expected. From about 1.5 times fewer it turns red.

A gap is not judged in five cases:

- The week is still coming in. That is always true of the current week, and on the Wikipedia lens a week waits until most of its page views are in.
- We are still building the theme's baseline, because the weeks compared reach back to before collection started.
- There is no need data: no Wikipedia page views for the theme, or no Google search data for one of the four weeks.
- There is too little need to compare with other topics: fewer than 2 ReliefWeb reports, or fewer than 3 events, in the four weeks.
- Fewer than 3 articles are expected, so even none at all could be chance.

## Warnings on a gap {#warnings}

- Coverage dropped while need held: coverage fell by more than half against the previous four weeks while need stayed about the same.
- Little Arabic coverage: fewer than a fifth of the articles are in Arabic.
- Only covered from outside Libya: no Libyan outlet covered it.
- Only one side's outlets: every outlet with a known political alignment that covered it is on the same side.
- Most coverage names no place: more than 80% of the articles name no place, so the district picture is weak.

## Search interest {#search-interest}

The searches lens uses Google Trends, which gives an index, never a count of searches, and only for people using Google from Libya. We measure each theme's words against an everyday word that belongs to no theme, and compare a theme only with its own past, because the words chosen set the size of the number. Google holds back any week with too few searches, so migration, security and the gender themes cannot be measured here. A rise means more people looked something up, not that nobody reported it. Searches and reporting usually rise together, so a gap here means searches rose and coverage did not keep up. The data is imported about once a week.

## Contribute {#contribute}

Votes on a gap (Real gap, Already covered, Not newsworthy), corrections, topic labels and article ratings are saved for the team and kept as training labels. Votes and ratings do not change the gap score or the ranking yet. They will start to train the ranking once there are about 150 of them. Topic labels train the theme model. A link pasted with "Already covered" counts as coverage from the next hourly update.

## When the numbers update {#updates}

- Every hour: outlet feeds, YouTube channels, Google Alerts and the theme model on new articles, then the scores for the last 12 weeks.
- Every six hours: Google News, GDELT, official statements, the Wikipedia pages read in Libya and the dinar's exchange rates.
- Nightly: Wikipedia page views, the social-media posts Google has indexed and a retrain of the theme model, then the full history of scores.
- Mondays: the weekly digest.
- About once a week, by hand: Google searches for the searches lens.

## Your data {#your-data}

Desert Watch improves its rankings and topic matching from what the team does. It records votes, comments, corrections, ratings and added articles, and also which gaps and articles are viewed, clicked and read for how long, and the filters used. Activity is stored under a pseudonymous ID, never sent to third-party analytics, and raw activity logs are deleted after 12 months. Comments and "working on this" flags are visible to the team only. The data can be exported or deleted on the [Privacy page](/me).
