## Robots.txt survey: which outlets in the Desert Watch register block AI crawlers (snapshot 2026-10-18)

**Bottom line:** Very few Libyan outlets block AI crawlers. 7 of the 68 Libyan web domains block at least one AI agent, and 4 of those are real news outlets. Only 2 Libyan outlets block OpenAI's search bot, 3 block PerplexityBot, and none block Claude-SearchBot or Claude-User. The top international outlets block much more: 8 of 25, holding 20 to 35% of their article volume, are blocked to the AI search bots. So if the "AI answers" lens finds Libyan outlets missing from answers, robots.txt opt-outs are not the main reason, at least as far as robots.txt shows.

### Method
- **Outlet list.** Read from the local copy of the production DB, opened read-only (`mode=ro`). It holds 188 outlets whose current scope is `libyan` and none with `diaspora`. I dropped 120 platform paths (facebook.com/..., x.com/..., youtube.com/channel/..., tiktok.com/...), leaving **68 Libyan web domains**. I added the **25 international outlets with the most articles** (`item.kind='article'`). Total: 93 hosts.
- **Fetching.** One `GET https://<domain>/robots.txt` per host, run one at a time, with UA `desert-watch/0.2 (https://desert-watch.fly.dev)`, a 20 s timeout and at least 2.2 s between requests. Redirects were followed (for example to www.). No other page on any site was requested.
  - At most one retry, and only after a network, timeout or TLS error. After a certificate error, the retry was the same URL with verification off. This is marked "cert unverified" and applied to 3 Libyan hosts.
- **Parsing (RFC 9309).**
  - Consecutive User-agent lines form one group, and blank lines don't matter.
  - All groups naming an agent are merged. An agent with no group of its own falls back to the `*` group.
  - `*` and `$` wildcards are supported. The longest matching rule wins, and Allow wins a tie.
  - Content-Signal lines are recorded.
- **Verdict per agent.** I tested `/`, one made-up article-like path, and up to 20 real article paths for that outlet from the DB. Tracking query strings such as `?utm_*` and `?traffic_source=rss` were removed first, so a generic tracking-parameter rule isn't mistaken for a content block.
  - **B** (blocked): every content path is disallowed.
  - **P** (partial): some tested paths are disallowed but not all. This came out zero times.
  - **A** (allowed): nothing tested is disallowed.
  - **nf** (no file): HTTP 404. Under RFC 9309 this means no restrictions.
  - **err**: the file could not be fetched.
- **`!` marker:** the agent is named in a group of its own. No `!` means the verdict comes from the `*` group.

Column key: GPT=GPTBot, OAI-S=OAI-SearchBot, CG-U=ChatGPT-User, ClB=ClaudeBot, Cl-S=Claude-SearchBot, Cl-U=Claude-User, anth=anthropic-ai, PplxB=PerplexityBot, Pplx-U=Perplexity-User, G-Ext=Google-Extended, Gbot=Googlebot, Apl-E=Applebot-Extended, CC=CCBot, Byte=Bytespider, Meta=meta-externalagent, Amzn=Amazonbot. CF=response came through Cloudflare. CS=has a Content-Signal line; all 6 such lines read exactly `search=yes,ai-train=no,use=reference`, which is Cloudflare's managed robots.txt. Outlet names are as stored in the DB ("ar" is the Arabic edition of Libya Observer).

### Table
| Outlet | Domain | Scope | Arts | Fetch | GPT | OAI-S | CG-U | ClB | Cl-S | Cl-U | anth | PplxB | Pplx-U | G-Ext | Gbot | Apl-E | CC | Byte | Meta | Amzn | * | CF | CS |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Libya Observer | libyaobserver.ly | libyan | 8083 | ok | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | Y |  |
| Libya Review | libyareview.com | libyan | 6778 | ok | B! | A | A | B! | A | A | B! | A | A | B! | A | B! | B! | B! | B! | B! | A | Y | Y |
| عين ليبيا | eanlibya.com | libyan | 3947 | ok | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A |  |  |
| LANA | lana.gov.ly | libyan | 3062 | 404 | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf |  |  |
| Al Wasat | alwasat.ly | libyan | 2908 | ok | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | Y |  |
| Libya Akhbar | libyaakhbar.com | libyan | 2459 | ok | B! | B! | B! | B! | A | A | B! | B! | B! | A | A | B! | B! | B! | B! | B! | A | Y |  |
| lywitness | lywitness.com | libyan | 1988 | ok | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | Y |  |
| صحيفة الساعة 24 | alsaaa24.com | libyan | 1584 | ok | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | Y |  |
| akhbarlibya24 | akhbarlibya24.net | libyan | 1415 | ok | B! | A | B! | B! | A | A | B! | B! | A | B! | A | B! | B! | B! | B! | B! | A | Y | Y |
| Al Marsad | almarsad.co | libyan | 1182 | ok | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | Y |  |
| addresslibya | addresslibya.com | libyan | 1177 | ok | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A |  |  |
| Al Menassa | almenassa.ly | libyan | 1057 | ok | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | Y |  |
| Libya Herald | libyaherald.com | libyan | 979 | 404 | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf | Y |  |
| RNA (Reportage) | reportage.ly | libyan | 941 | ok | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A |  |  |
| Libya 24 | libya24.tv | libyan | 768 | ok | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A |  |  |
| Libya Al Ahrar TV | libyaalahrar.tv | libyan | 685 | ok | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | Y |  |
| Libya Update | libyaupdate.com | libyan | 359 | ok | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A |  |  |
| Libyan Express | libyanexpress.com | libyan | 294 | ok | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A |  |  |
| arraedlg | arraedlg.net | libyan | 199 | ok | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A |  |  |
| ar | ar.libyaobserver.ly | libyan | 175 | ok | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | Y |  |
| almashhadlibya | almashhadlibya.com | libyan | 154 | ok | B! | B! | B! | B! | A | A | B! | B! | B! | A | A | B! | B! | B! | B! | B! | A | Y |  |
| Al Sabaah | alsabaah.ly | libyan | 122 | ok | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A |  |  |
| sada | sada.ly | libyan | 74 | ok | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A |  |  |
| Abaad | abaad.news | libyan | 61 | ok | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A |  |  |
| libyanstand | libyanstand.ly | libyan | 51 | ok | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A |  |  |
| drooj | drooj.com.ly | libyan | 34 | ok | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A |  |  |
| lj-bc | lj-bc.tv | libyan | 14 | ok | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | Y |  |
| atlibya | atlibya.com | libyan | 8 | ok | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | Y |  |
| newslibya | newslibya.ly | libyan | 7 | ok | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A |  |  |
| ltv | ltv.ly | libyan | 6 | ok | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A |  |  |
| bahu.ly | bahu.ly | libyan | 4 | ok | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A |  |  |
| Dirham | dirham.ly | libyan | 4 | ok | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A |  |  |
| CBL | cbl.gov.ly | libyan | 4 | ok | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | Y |  |
| febp | febp.ly | libyan | 3 | ok | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A |  |  |
| alnnas | alnnas.ly | libyan | 2 | ok | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A |  |  |
| cjos.histr.edu.ly | cjos.histr.edu.ly | libyan | 2 | ok (cert unverified) | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A |  |  |
| bs.med.ly | bs.med.ly | libyan | 2 | ok | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A |  |  |
| journal.utripoli.edu.ly | journal.utripoli.edu.ly | libyan | 2 | ok | B! | A | A | A | A | A | A | A | A | A | A | A | A | B! | A | B! | A |  |  |
| dujhss.uod.edu.ly | dujhss.uod.edu.ly | libyan | 2 | ok | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A |  |  |
| parliament.ly | parliament.ly | libyan | 2 | ok | A | A | A | A | A | A | A | A | A | A | A! | A | A | A | A | A | A | Y |  |
| NOC | noc.ly | libyan | 2 | ok | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | Y |  |
| almusallh | almusallh.ly | libyan | 1 | ok | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A |  |  |
| avis.ly | avis.ly | libyan | 1 | ok | B! | A | A | B! | A | A | B! | A | A | B! | A | B! | B! | B! | B! | B! | A | Y | Y |
| jer.ly | jer.ly | libyan | 1 | 404 | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf |  |  |
| yellowpages.ly | yellowpages.ly | libyan | 1 | 404 | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf |  |  |
| journals.misuratau.edu.ly | journals.misuratau.edu.ly | libyan | 1 | 404 | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf | Y |  |
| dsdms.gov.ly | dsdms.gov.ly | libyan | 1 | ok | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A |  |  |
| dspace.su.edu.ly | dspace.su.edu.ly | libyan | 1 | TLS timeout | err | err | err | err | err | err | err | err | err | err | err | err | err | err | err | err | err |  |  |
| libyanjobs.ly | libyanjobs.ly | libyan | 1 | CF challenge 403 | err | err | err | err | err | err | err | err | err | err | err | err | err | err | err | err | err | Y |  |
| almadinamisurata.ly | almadinamisurata.ly | libyan | 1 | ok | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A |  |  |
| akhbarlibya.ly | akhbarlibya.ly | libyan | 1 | ok | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | Y |  |
| sebhau.edu.ly | sebhau.edu.ly | libyan | 1 | ok | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | Y |  |
| uoz.edu.ly | uoz.edu.ly | libyan | 1 | ok | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A |  |  |
| guide.refd.ly | guide.refd.ly | libyan | 1 | DNS fail | err | err | err | err | err | err | err | err | err | err | err | err | err | err | err | err | err |  |  |
| search.shabcenter.ly | search.shabcenter.ly | libyan | 1 | ok | B! | A | A | B! | A | A | B! | A | A | B! | A | B! | B! | B! | B! | B! | A | Y | Y |
| afjs.histr.edu.ly | afjs.histr.edu.ly | libyan | 1 | ok | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A |  |  |
| alwatan-ly | alwatan-ly.com | libyan | 0 | ok | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | Y |  |
| janaly | janaly.co | libyan | 0 | DNS fail | err | err | err | err | err | err | err | err | err | err | err | err | err | err | err | err | err |  |  |
| lananews | lananews.com | libyan | 0 | 404 | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf |  |  |
| alwow | alwow.ly | libyan | 0 | 404 (cert unverified) | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf |  |  |
| libyan-cna | libyan-cna.net | libyan | 0 | TLS timeout | err | err | err | err | err | err | err | err | err | err | err | err | err | err | err | err | err |  |  |
| libyaalahrar | libyaalahrar.net | libyan | 0 | TLS fail | err | err | err | err | err | err | err | err | err | err | err | err | err | err | err | err | err |  |  |
| fassatonews | fassatonews.net | libyan | 0 | ok | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A |  |  |
| elkhabar | elkhabar.ly | libyan | 0 | DNS fail | err | err | err | err | err | err | err | err | err | err | err | err | err | err | err | err | err |  |  |
| brnieq | brnieq.ly | libyan | 0 | 404 (cert unverified) | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf | nf |  |  |
| tanasuh | tanasuh.tv | libyan | 0 | CF challenge 403 | err | err | err | err | err | err | err | err | err | err | err | err | err | err | err | err | err | Y |  |
| zajel | zajel.tv | libyan | 0 | ok | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | Y |  |
| afrigatenews | afrigatenews.net | libyan | 0 | DNS fail | err | err | err | err | err | err | err | err | err | err | err | err | err | err | err | err | err |  |  |
| InfoMigrants | infomigrants.net | international | 1209 | ok | B! | B! | B! | B! | B! | B! | B! | B! | B! | B! | A | A | B! | A | A | A | A |  |  |
| Asharq Al-Awsat | aawsat.com | international | 1144 | ok | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | Y |  |
| Al Jazeera Arabic | aljazeera.net | international | 1002 | ok | B! | A | B! | B! | A | A | B! | B! | A | A | A | A | A | B! | A | A | A |  |  |
| Al-Araby Al-Jadeed | alaraby.co.uk | international | 954 | ok | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A |  |  |
| Al Arabiya | alarabiya.net | international | 693 | ok | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | Y |  |
| اليوم السابع | youm7.com | international | 502 | ok | A! | A! | A | A! | A | A | A | A! | A | A! | A! | A | A! | A | A! | A! | A | Y |  |
| France 24 | france24.com | international | 464 | ok | B! | B! | B! | B! | B! | B! | B! | B! | B! | B! | A! | A | B! | A | A | A | A |  |  |
| Anadolu Ajansı | aa.com.tr | international | 401 | ok | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A |  |  |
| Reuters | reuters.com | international | 399 | ok | B | A! | A! | B | B | B | B | B | B | B | A! | B! | B | B | B | B | B |  |  |
| العين الإخبارية | al-ain.com | international | 388 | ok | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | Y |  |
| اندبندنت عربية | independentarabia.com | international | 350 | ok | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | Y |  |
| Agenzia Nova | agenzianova.com | international | 342 | ok (cf-mitigated) | B! | A | A | B! | A | A | B! | A | A | B! | A | B! | B! | B! | B! | B! | A | Y | Y |
| الطاقة | attaqa.net | international | 336 | ok | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | Y |  |
| BBC Arabic | bbc.com | international | 318 | ok | B! | B! | B! | B! | A | A | B! | B! | B! | B! | A | B! | B! | B! | B! | B! | A |  |  |
| ميدل ايست اونلاين | middle-east-online.com | international | 318 | ok | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | Y |  |
| The Arab Weekly | thearabweekly.com | international | 303 | ok | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | Y |  |
| القدس العربي | alquds.co.uk | international | 284 | ok | B! | B! | B! | B! | B! | A | B! | B! | B! | B! | A | B! | B! | B! | B! | B! | A | Y |  |
| Al Jazeera | aljazeera.com | international | 273 | ok | B! | A | B! | B! | A | A | B! | B! | A | A | A | A | A | B! | A | A | A |  |  |
| سكاي نيوز عربية | skynewsarabia.com | international | 267 | ok | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A |  |  |
| Africanews English | africanews.com | international | 260 | ok | A | A | A | A | A | A | A | A | A | A | A! | A | A | A | A | A | A |  |  |
| ReliefWeb | reliefweb.int | international | 245 | ok | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A |  |  |
| التلفزيون العربي | alaraby.com | international | 225 | ok | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A |  |  |
| UN News | news.un.org | international | 179 | ok | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A |  |  |
| المصري اليوم | almasryalyoum.com | international | 173 | ok | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | Y |  |
| عربي21 | arabi21.com | international | 172 | ok | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | A | Y |  |

### Counts per agent
**Libyan outlets (n=68):** 51 served a robots.txt, 8 had none (404), 9 could not be fetched. No agent came out partial, and every block comes from a group naming that agent; no `*` group blocks the whole site. The last column is the share of the 40,615 Libyan articles from outlets that block the agent.

| Agent | Blocked | Allowed | No file | Error | Blocked share of Libyan articles |
|---|---|---|---|---|---|
| GPTBot | 7 | 44 | 8 | 9 | 26.6% |
| OAI-SearchBot | 2 | 49 | 8 | 9 | 6.4% |
| ChatGPT-User | 3 | 48 | 8 | 9 | 9.9% |
| ClaudeBot | 6 | 45 | 8 | 9 | 26.6% |
| Claude-SearchBot | 0 | 51 | 8 | 9 | 0% |
| Claude-User | 0 | 51 | 8 | 9 | 0% |
| anthropic-ai | 6 | 45 | 8 | 9 | |
| PerplexityBot | 3 | 48 | 8 | 9 | 9.9% |
| Perplexity-User | 2 | 49 | 8 | 9 | |
| Google-Extended | 4 | 47 | 8 | 9 | |
| Googlebot | 0 | 51 | 8 | 9 | |
| Applebot-Extended | 6 | 45 | 8 | 9 | |
| CCBot | 6 | 45 | 8 | 9 | |
| Bytespider | 7 | 44 | 8 | 9 | |
| meta-externalagent | 6 | 45 | 8 | 9 | |
| Amazonbot | 7 | 44 | 8 | 9 | |
| `*` | 0 | 51 | 8 | 9 | |

Libyan news outlets with at least 10 articles (n=27; 25 have a file, while LANA and Libya Herald return 404): blocked counts are GPTBot 4, OAI-SearchBot 2, ChatGPT-User 3, ClaudeBot 4, Claude-SearchBot 0, Claude-User 0, PerplexityBot 3, Perplexity-User 2, Google-Extended 2, Googlebot 0. All training bots (ClaudeBot, anthropic-ai, Applebot-Extended, CCBot, Bytespider, meta-externalagent, Amazonbot) are at 4.

**International (n=25):** all 25 served a robots.txt, and Reuters was the only partial-looking case before tracking parameters were removed. The bracketed figure is how many blocks come from a named group rather than `*`. The last column is the share of the 11,201 international articles from outlets that block the agent.

| Agent | Blocked | Allowed | Blocked share of international articles |
|---|---|---|---|
| GPTBot | 8 (7) | 17 | 38.3% |
| OAI-SearchBot | 4 (4) | 21 | 20.3% |
| ChatGPT-User | 6 (6) | 19 | |
| ClaudeBot | 8 (7) | 17 | 38.3% |
| Claude-SearchBot | 4 (3) | 21 | 21.0% |
| Claude-User | 3 (2) | 22 | |
| anthropic-ai | 8 (7) | 17 | |
| PerplexityBot | 7 (6) | 18 | 35.3% |
| Perplexity-User | 5 (4) | 20 | |
| Google-Extended | 6 (5) | 19 | |
| Googlebot | 0 | 25 | |
| Applebot-Extended | 4 (4) | 21 | |
| CCBot | 6 (5) | 19 | |
| Bytespider | 6 (5) | 19 | |
| meta-externalagent | 4 (3) | 21 | |
| Amazonbot | 4 (3) | 21 | |
| `*` | 1 (Reuters) | 24 | |

### Libyan outlets that block AI search bots, compared with training bots only
**Block search bots as well as training bots:**
- **Libya Akhbar** (libyaakhbar.com, 2,459 articles, Arabic) blocks OAI-SearchBot, PerplexityBot, ChatGPT-User and Perplexity-User, plus all training bots except Google-Extended.
- **almashhadlibya** (almashhadlibya.com, 154 articles) has the same block list. Its robots.txt is a near-identical copy of Libya Akhbar's, so it is probably the same developer or SEO template.
- **akhbarlibya24** (akhbarlibya24.net, 1,415 articles) blocks PerplexityBot and ChatGPT-User but **allows OAI-SearchBot**. It uses Cloudflare's managed training-bot block and Content-Signal, plus its own list.
- None of these three name Claude-SearchBot or Claude-User, so both are allowed.

**Training bots only (search bots allowed):**
- **Libya Review** (libyareview.com, 6,778 articles, the largest English Libyan outlet that blocks anything) uses Cloudflare's managed robots.txt. It blocks GPTBot, ClaudeBot, anthropic-ai, Google-Extended, Applebot-Extended, CCBot, Bytespider, meta-externalagent and Amazonbot. Its Content-Signal says `search=yes, ai-train=no`.
- **avis.ly** and **search.shabcenter.ly** (1 article each) use the same Cloudflare managed file.
- **journal.utripoli.edu.ly** (2 articles) blocks only GPTBot, Bytespider and Amazonbot.

**Block nothing:** Libya Observer (both editions), Ean Libya, Al Wasat, LY Witness, Al Saaa 24, Al Marsad, Address Libya, Al Menassa, Reportage, Libya 24, Libya Al Ahrar TV, Libya Update and Libyan Express. LANA and Libya Herald have no robots.txt at all.

**International, for contrast:**
- InfoMigrants and France 24 (same group) block every AI agent tested, including Claude-SearchBot and Claude-User.
- Al-Quds Al-Arabi blocks all of them, including Claude-SearchBot, except Claude-User.
- BBC blocks OAI-SearchBot and PerplexityBot but does not name either Claude search agent.
- Al Jazeera (Arabic and English) blocks training bots, ChatGPT-User and PerplexityBot but allows OAI-SearchBot and Claude-SearchBot.
- Reuters blocks every bot it doesn't name (`*`: Disallow /, Allow /plus/). It explicitly lets in OAI-SearchBot, ChatGPT-User and Googlebot, so Claude-SearchBot and PerplexityBot are blocked through `*`.
- Youm7 explicitly *allows* GPTBot, OAI-SearchBot, ClaudeBot, PerplexityBot, Google-Extended and CCBot by name.

### Caveats
- **robots.txt is a request, not enforcement.** Compliance is voluntary. According to the vendors' own crawler documentation, user-triggered fetchers (ChatGPT-User, Perplexity-User) may not apply robots.txt at all. Check the current wording before quoting it to the owner.
- **Cloudflare can block at its edge whatever robots.txt says.** Its AI-bot blocking runs on the network and can't be seen from robots.txt. 27 of the 68 Libyan hosts (14 of the 27 news outlets) and 12 of the 25 international hosts answered through Cloudflare.
  - Libya Herald, for example, has no robots.txt but sits behind Cloudflare and may still block AI agents.
  - Desert Watch's own user agent was challenged on libyanjobs.ly and tanasuh.tv (403 "Just a moment"). Agenzia Nova served its robots.txt with a `cf-mitigated: challenge` header, so the Desert Watch fetcher may be challenged there too.
- **Blocking a crawler is not the same as being absent from answers.** An assistant can cite a page through a search-engine index or a licensing feed without fetching it, so a block doesn't guarantee absence and an allow doesn't guarantee presence. Google-Extended does not cover AI Overviews in Google Search, which run on Googlebot, and Googlebot is allowed everywhere here.
- **Tokens differ by vendor.** Only exact tokens were matched. Old names such as Claude-Web and cohere-ai are named in several files but don't govern the current agents.
- **Single snapshot.** Taken 2026-10-18 with one request per host; robots files change. The 9 fetch errors are 4 DNS failures (janaly.co, elkhabar.ly, afrigatenews.net, guide.refd.ly), 2 TLS timeouts, 1 TLS handshake failure and 2 Cloudflare challenges. Almost all are outlets with 0 or 1 article, which looks like dead register entries rather than blocking.
- **Other limits.** The verdicts rest on real article paths from the DB, but for international outlets whose articles mostly arrive as Google News URLs only 0 to 4 own-host paths were available. news.un.org redirects robots.txt to /en/robots.txt, which was followed. almadinamisurata.ly's file is all on one line, so it is unparseable and counts as allowed.

### Files
Everything is in `C:\Users\paler\AppData\Local\Temp\claude\C--Users-paler-OneDrive-Documents-Claude-Project\babb8b1c-9a4b-4693-a2e6-64d085d499da\scratchpad\ai_audit\`:
- **Raw responses** (status, final URL, headers, body, attempts): `robots_raw.json`
- **Parsed results** (per-agent verdict, named or `*`, Content-Signal, Cloudflare flags, named AI tokens, robots text): `robots_results.json`
- **Outlet selection and article paths:** `outlets.json`
- **Scripts:** `select_outlets.py`, `fetch_robots.py`, `analyze_robots.py`

Nothing was written to the DB, and nothing was built, committed or deployed.