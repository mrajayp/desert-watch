# AI answers audit: scope

## Decisions taken (2026-10-18)

The owner read this draft and replied "Claude plus ChatGPT, $1 cap, build it". The build started the same day. Where this section and the draft below differ, this section holds.

- **Providers.** Claude, through the Anthropic Messages API with the basic web search tool (`web_search_20250305`), and ChatGPT, through the OpenAI Responses API with `web_search`. Perplexity, Gemini, Microsoft and Meta stay out. (Perplexity was added later the same day: see the second build below.)
- **Weekly cap.** USD 1.00 a week for both assistants together. 2 assistants × 8 questions × 2 languages make 32 answers a week, estimated at about USD 0.80. Before each answer the runner checks that this week's spend plus the estimate stays within the cap. If it would not, the remaining answers are recorded as `over_budget` and the run stops. Answers go by question, then language, then assistant, so a stop leaves coverage balanced.
- **Searches.** At most 2 per question (`max_uses` / `max_tool_calls` = 2). Sections 5, 6 and 8 assume 3.
- **Who sees results.** Admins only at first (`visible_to: admins` in `config/ai_audit.yaml`), until the owner changes it to `team`.
- **Keys.** Claude uses the digest's `ANTHROPIC_API_KEY` and is switched on in `config/ai_audit.yaml`. That replaces the `DW_AI_AUDIT_ANTHROPIC` switch in section 5. OpenAI waits for the owner to set `OPENAI_API_KEY` as a Fly secret, and shows "awaiting key" until then.
- **Taken as the draft recommends.** Arabic and English. Once a week, Monday 04:20 UTC. Location Tripoli, Libya. A one-line system prompt with today's date and nothing else. No domain filters. The assistant is never asked to cite. Answer text and `cited_text` are not stored. The audit stays unscored.

## Second build: team panel, browser sessions, Perplexity (agreed 2026-10-18)

After the first build was deployed (commit 451fc2f), the owner agreed to a second build in three parts ("yes", "ok, go ahead", "keep going, deploy when it's all tested"). Where this note and the rest of the document differ, this note holds.

- **Three origins, never mixed.** Every run and every answer carries an `origin`: `api` (the automatic weekly developer-API run), `panel` (logged by journalists from the apps on their own phones) or `browser` (a supervised browser session). No figure adds two origins together. The summary takes `origin=api|panel|browser` (default `api`), and the outlet panel's "cited in the last 4 weeks" line counts `api` only.
- **Journalist panel.** Each week the Contribute page shows the same 8 questions in Arabic and English. A journalist asks one or more in the consumer app they use on their own phone: ChatGPT app, Gemini, Google AI Overview or AI Mode, Meta AI (WhatsApp, Facebook, Instagram), Copilot, Perplexity app, Claude app, Grok, DeepSeek or other. They paste the source links the answer showed, or tick "no sources shown", and say whether they asked from Libya or elsewhere. The links go through the existing matcher (`ai_audit/matcher.py`) and are stored as `cited`, because an app shows the links its answer used. There are no searches, no searched rows and no answer text. Limits: contributors only, 40 entries per person per week, 30 links per entry. A journalist's identity is never shown to anyone else, and admins see the author only as "a team member". Deleting an account sets `logged_by` to null, and the data export includes the person's entries. This covers part of section 1's "what people see in the consumer apps", for a handful of accounts only, so it is a small, uneven sample.
- **Supervised browser sessions.** The owner signs in to a chatbot in a browser in London and Claude asks the questions while the owner watches. Claude logs only the source links, through the same entry path or `python -m app.cli ai-panel-import FILE --origin browser`, marked as asked from London. Only admins can log this origin. The answers show what a signed-in account in London saw, not what people in Libya see.
- **Perplexity.** Added through its developer Agent API (`POST https://api.perplexity.ai/v1/agent`, model `perplexity/sonar`, `web_search` tool), inside the same USD 1 weekly cap as Claude and ChatGPT. This replaces "Perplexity ... stay out" above. It waits for the owner to set `PERPLEXITY_API_KEY` as a Fly secret and shows "awaiting key" until then. Searched means its search results. Cited means the results that `[n]` markers point to, where an answer has any. The docs say markers appear only when the prompt asks for them and the audit never asks, so Perplexity's cited count is often empty and is not a measure of what it used. Searches are capped at 2 through `max_steps` and `max_tool_calls`. Location: country, region and city (the tool has no time zone field).
- **Cost.** With three assistants a week has 48 answers. Claude and ChatGPT should cost about USD 0.80 and Perplexity about USD 0.15 (an estimate from the dated price list, not yet measured), so a full week runs close to the cap. In an expensive week the last question or two can be recorded as `over_budget`. The pre-call estimate is deliberately high (USD 0.028 an answer for Claude and ChatGPT, USD 0.030 for Perplexity, `config/ai_audit.yaml`), so a dry run with all three shows only about 34 of the 48 answers fitting, while a real run usually gets through all or nearly all of them. Panel and browser entries hang off runs with cost 0 and never count against the cap.
- **Unchanged.** Results stay admin-only (`visible_to: admins`). Full URLs and titles stay admin-only, and everyone else sees outlet- and domain-level counts. Nothing writes `Item`, `ItemTheme` or `CellWeek`.
- **Open point for the owner: consumer terms in browser sessions.** Anthropic's Consumer Terms (effective 8 October 2025, section 3) bar using the services "through automated or non-human means, whether through a bot, script, or otherwise", with exceptions for API keys and uses Anthropic explicitly permits. A session in which Claude types the questions into the Claude app may fall under that, even with the owner watching. OpenAI's Terms of Use returned 403 on 18 October and were not re-read. Read each service's consumer terms before its first browser session. That clause does not touch the team panel, where people ask and copy the links by hand.

## Draft

Draft for the Desert Watch owner, 18 October 2026, written before anything was built. Figures marked "estimate" are worked out from list prices. Nobody has measured them yet. On 18 October I re-read the key Anthropic pricing and web-search pages, the OpenAI web-search guide and Google's Gemini API terms. The other provider facts come from research done earlier on the same day.

---

## 1. What it answers, and what it cannot

### What it answers

You asked three things. Each week the lens would ask a fixed set of Libya questions in Arabic and in English, and record the following.

1. **Where the AI searches.** It records the exact search queries the assistant wrote, and their language.
   - Claude returns every query.
   - OpenAI returns them in most cases, but its guide says not always.
   - Perplexity's Agent API returns a `queries` array.
2. **How many sources it uses.** It records two counts per answer, and they mean different things:
   - **searched**: every result the search tool returned;
   - **cited**: the links the answer actually points to.

   Prior audits show these two can differ a lot. In one EBU case Perplexity listed 19 URLs and used 3.
3. **Which newspapers.** Each domain is matched to the Desert Watch outlet register and tagged:
   - by scope: Libyan, diaspora or international;
   - by language: Arabic or English.

   The lens then shows which register outlets the assistants never cite.

### What it cannot answer

- **What people see in the consumer apps.** The lens measures developer-API answers only, and the gap is large:
  - In one study, the API and consumer ChatGPT shared no search queries, and only 12.3% of URLs overlapped (Genezio).
  - Another found that the Responses API plus Google Search recover only about a quarter of the URLs that ChatGPT Web cites (arXiv 2610.15382).
  - Claude.ai and ChatGPT add their own system prompts, IP-based location, memory and model routing. None of these are in the API.
- **Meta AI in WhatsApp, Facebook, Instagram and Messenger.**
  - Meta AI launched in Arabic in Libya in February 2025.
  - Meta's developer API is a US-only preview, and Meta's Geographic Use Policy lists Libya as a Restricted Territory.
  - Meta does not say its API search matches the in-app assistant.
  - Use inside the apps creates no web referrals, so StatCounter cannot see it either.
- **Google AI Overviews and AI Mode.** Google has 99.91% of Google-vs-ChatGPT search share in Libya (StatCounter, September 2026). These are probably the AI answers most Libyans see, and they have no API.
- **Gemini and Copilot, unless their terms change.** Their API terms forbid the storing and analysis this lens needs (section 2).
- **Personalisation.** The API has no account history, memory or device location. At most the lens sees one location hint.
- **Whether an answer is true.** The lens counts sources and does not grade answers. An optional manual check is described in section 4.

---

## 2. What the providers expose today

### Who Libyans use

StatCounter's AI-chatbot referral share for Libya, September 2026:

| Assistant | Share |
|---|---|
| ChatGPT | 60.32% |
| Gemini | 30.69% |
| Copilot | 4.23% |
| Perplexity | 4.23% |
| Claude | 0.53% |

- These are shares of website visits that come from each chatbot, not shares of users or of answers.
- Copilot and Perplexity tie exactly, which suggests a small Libyan sample.
- Libya is **not** on Anthropic's supported-regions list (Egypt, Tunisia and the UK are). That fits Claude's small share. Claude matters more for international journalists covering Libya than for Libyan audiences.

### Anthropic Claude (Messages API, `web_search` server tool)

| | |
|---|---|
| Queries | Always returned. Each search is a `server_tool_use` block, and its `input.query` holds the exact query string. |
| All sources | Every result for every query: `url`, `title`, `page_age`. `page_age` is when the site was last updated, not a publication date. With the basic tool (`web_search_20250305`) and direct calls, every returned result goes into the model's context, so "searched" also means "consulted". Dynamic filtering (20260209 and later) breaks this, so the lens should not use it. |
| Citations | Always on: `web_search_result_location` with `url`, `title`, and `cited_text` of up to 150 characters. |
| Location / language | `user_location` takes city, region, ISO-2 country and timezone. The API rejects unsupported country codes with a 400 error and publishes no list. Libya is not an Anthropic-supported region, so `LY` may be rejected. There is no language parameter; the language of the question steers the queries. `max_uses` caps the searches per request. |
| Price per question | $10 per 1,000 searches, plus tokens; failed searches are not billed. Haiku 5.5 costs $0.10 in / $0.50 out per MTok for prompts up to 100k tokens, and $0.50 / $2.50 above that (re-read 18 Oct). The Batch API halves token prices but not the search fee, and it throttles web search, so it brings no real saving here. **Estimate:** a 3-search answer costs about $0.035, of which $0.03 is the search fee. |
| Storage / display terms | Anthropic's docs say output shown directly to end users must cite the original sources. Output that has been reprocessed or combined should carry citations as legal advice dictates. No clause was found that forbids storing URLs, titles or `cited_text`. The basic tool is eligible for zero data retention (ZDR). The Commercial Terms forbid using the services to build a competing product or to train competing models; this lens does neither. |
| Rate limits | Normal model limits, plus an organisation-level web-search limit that is shown in the Console but not published. Hitting it returns `too_many_requests` inside an HTTP 200 response. An admin can switch web search off for the organisation, and a request then fails with a 400 error. |
| Caveat | No support table confirms that Haiku 5.5 accepts web search: neither the tool reference nor the web-search page lists it. Read `capabilities.server_tools.web_search.supported` from the Models API before building. |

### OpenAI (Responses API, `web_search` tool)

| | |
|---|---|
| Queries | Returned in most cases, not always. A `web_search_call` has `action.query` / `queries`. `open_page` and `find_in_page` actions show which pages were opened. |
| All sources | Only on request: `include: ["web_search_call.action.sources"]` returns the complete list of URLs consulted, which is often longer than the citation list. These are URLs only, with no title, rank or snippet. Real-time feeds appear as `oai-sports`, `oai-weather` and `oai-finance` and should be dropped. |
| Citations | `url_citation` annotations: url, title, and the span of answer text that cites the source. |
| Location / language | `user_location` takes ISO-2 country, city, region and timezone. The API reference says it **defaults to the United States when omitted**, so it must be set explicitly. `search_context_size` is low, medium or high. There is no language parameter. Web search does not work on gpt-5 at minimal reasoning, so keep reasoning effort at low or above. |
| Price per question | $10 per 1,000 calls, plus search content tokens at model rates. gpt-6-luna costs $0.10 / $0.50 per MTok, and reasoning tokens are billed as output. **Estimate:** about $0.035 for 3 calls. The docs do not say whether `open_page` actions are billed as calls. The guide recommends gpt-5.5 ($5 / $30); gpt-6-luna's search quality has not been checked. |
| Storage / display terms | The guide requires inline citations to be visible and clickable wherever web results are shown to users. According to the earlier research, the Service Terms (updated 2026-10-16) withdraw the IP indemnity if citation features are ignored. That page returned 403 to one researcher, so this rests on a single reading. No storage clause specific to search was found. Application state is kept 30 days by default; send `store: false`. ZDR eligibility for web search is not documented. |
| Libya | Listed as a supported API country, but this was seen only in search snippets; the live page returned 403. |

### Perplexity (Agent API, `web_search` tool; Sonar Chat Completions support ended 27 September 2026)

| | |
|---|---|
| Queries | Yes. The `search_results` item carries a `queries` array. |
| All sources | Yes: `results[]` with url, title, snippet, date and source. `max_results` is 1-50 per call. |
| Citations | `[n]` markers that point to result ids. The docs say the markers depend on the prompt, and that the result list is the source of truth. In the docs' example the annotations array is empty. **So a "cited" count for Perplexity is unreliable.** Report searched results, and report cited links only where markers are present. |
| Location / language | `user_location` takes an ISO-2 country; whether `LY` is accepted is untested. `search_language_filter` (which includes `ar`) has **no Agent API equivalent**. Set the model to `perplexity/sonar`, because presets default to OpenAI models. |
| Price per question | $2.50 per 1,000 calls (`web`) or $1.00 per 1,000 (`fast`), plus perplexity/sonar tokens at $0.25 / $2.50 per MTok. **Estimate:** about $0.004-0.01 per question. |
| Rate limits | Tier 0 allows 1 request per second, so calls must run one after another, with a gap. |
| Storage / display terms | The customer owns the Output, and it may be shown only in the customer's own applications. There is no clause on caching or storing. Use in US-embargoed countries is barred. My reading is that Libya is under targeted sanctions, not a comprehensive embargo; this is not legal advice. |

### Google Gemini (grounding with Google Search)

| | |
|---|---|
| Queries | Yes: `webSearchQueries`. |
| All sources | Partly. `groundingChunks` are the sources the answer used, not every result. In `generateContent` the `uri` is a `vertexaisearch.cloud.google.com/grounding-api-redirect/...` link, and `title` holds only the domain. |
| Citations | Yes: `groundingSupports`, with segment indices. |
| Location / language | Works in all languages. No location parameter appears on the pages fetched. |
| Price per question | Gemini 3 and later: 5,000 free search queries a month on the paid tier, then $14 per 1,000. The free tier has no grounding for Gemini 3 and later. |
| Storage / display terms | **These terms block this design** (re-read 18 Oct). Grounded results may be shown only together with their Search Suggestions, and only to the end user who submitted the prompt. You may not "cache, frame, syndicate, resell, analyze, train on, or otherwise learn from Grounded Results". Collecting links by automated means is barred. Storage is allowed only for narrow purposes, for up to two years. Vertex section 20(k) says the same. Even with written permission, the display rule conflicts with showing tallies to other journalists. |

### Microsoft (Grounding with Bing Search, Foundry Agent Service)

| | |
|---|---|
| Queries | Yes: the Bing query URL in the run-step details. |
| All sources | No. The docs say the tool output is not returned to developers; only cited URLs come back. |
| Citations | `url_citation`. |
| Location / language | `market` and `set_lang`. No domain filters. |
| Price per question | $14 per 1,000 transactions, plus tokens. |
| Storage / display terms | **These terms block this design.** They forbid copying, storing, caching or building a database of the output, and using it to evaluate AI models. References must be shown exactly as Microsoft provides them. |

### Meta (Model API, Muse Spark)

| | |
|---|---|
| Queries | Not documented. |
| All sources | Opt-in, through `web_search_call.results`, which the docs describe as every source the model considered. |
| Citations | `url_citation`. |
| Price per question | $2.50 per 1,000 searches, plus tokens. |
| Storage / display terms | **Excluded.** It is a US-only developer preview, and Libya is a Restricted Territory: no products may be made available to end users located there. |

### xAI Grok, DeepSeek, Mistral

| | xAI Grok | DeepSeek | Mistral |
|---|---|---|---|
| Queries | Partly (tool-call arguments) | Only the query you send to its standalone Search API | Not documented |
| All sources | `citations` lists every source encountered | No source list for chat answers | Not documented |
| Citations | `url_citation` | No | `tool_reference` chunks |
| Price | $5 per 1,000 calls plus tokens | $0.75 per 1,000 (standalone search only) | Unconfirmed |
| Terms | Not checked | Not checked | Not checked |
| Libya share | Not listed by StatCounter | Not listed | Not listed |

### Which to include first

1. **Claude first.** The digest already has `ANTHROPIC_API_KEY`, so Claude needs only an on-switch. It returns every query, every result and every citation, and the basic tool is ZDR-eligible. Its weakness is relevance: 0.53% of Libyan referrals, and no official availability in Libya.
2. **OpenAI second.** ChatGPT accounts for about 60% of Libyan chatbot referrals. Its API returns queries (in most cases), the full list of consulted sources, and citations. It needs a new key, and the US default for `user_location` must be overridden.
3. **Perplexity third.** It is the cheapest, and it returns queries plus results with snippets. Its terms do not block storing domain tallies. Its share is small (4.23%), its "cited" signal is unreliable, and the move from Sonar to the Agent API is recent.
4. **Leave out for now:**
   - **Gemini and Microsoft:** their terms forbid storing and analysing results. Google also requires its Search Suggestions to be displayed, and only to the user who asked.
   - **Meta:** Libya is restricted.
   - **DeepSeek:** chat answers come with no sources.
   - **xAI and Mistral:** their terms are unchecked, and they have no Libyan share.

---

## 3. The Libyan robots.txt finding

On 18 October 2026 I fetched one `robots.txt` per host with the desert-watch user agent. That covered 68 Libyan web domains from the register and the 25 international outlets with the most articles. The full table is in `docs/research/ai_crawlers_robots_2026-10-18.md`.

### Headline counts

- **7 of 68** Libyan web domains block at least one AI agent. Only **4** of those are real news outlets: Libya Review, Libya Akhbar, akhbarlibya24 and almashhadlibya.
- **AI search bots**, the agents that decide whether a site can appear in AI answers:
  - **OAI-SearchBot** is blocked by **2** Libyan outlets, Libya Akhbar and almashhadlibya, which hold 6.4% of Libyan articles.
  - **PerplexityBot** is blocked by **3** (9.9% of Libyan articles).
  - **Claude-SearchBot and Claude-User** are blocked by **0**.
- **Training bots:** GPTBot is blocked by 7 (26.6% of Libyan articles) and ClaudeBot by 6 (26.6%). Libya Review, the largest of these, uses Cloudflare's managed file. It blocks training bots and allows search bots (`Content-Signal: search=yes, ai-train=no`).
- **Libyan outlets that block nothing:** Libya Observer (both editions), Ean Libya, Al Wasat, LY Witness, Al Saaa 24, Al Marsad, Address Libya, Al Menassa, Reportage, Libya 24, Libya Al Ahrar TV, Libya Update, Libyan Express and others. LANA and Libya Herald have no robots.txt.
- **International outlets block more.** Of the 25:
  - OAI-SearchBot is blocked by 4 (20.3% of international articles), Claude-SearchBot by 4 (21.0%) and PerplexityBot by 7 (35.3%).
  - InfoMigrants and France 24 block every AI agent tested.
  - Reuters blocks Claude-SearchBot and PerplexityBot through its `*` rule, and lets OAI-SearchBot in by name.
  - BBC blocks OAI-SearchBot and PerplexityBot.
  - Al Jazeera allows OAI-SearchBot and Claude-SearchBot.

### What it means for AI answers about Libya

If the lens finds Libyan outlets missing from answers, robots.txt opt-outs explain very little of it. For Claude they explain nothing, as far as robots.txt shows. The likelier reasons are these:

- **The outlet is not in the search index the assistant uses.** Third-party reports name Brave as Claude's search provider. Peec AI's research names Google results scrapers and Microsoft among ChatGPT's providers.
- **Cloudflare blocks at its edge, and robots.txt does not show it.**
  - 27 of the 68 Libyan hosts answered through Cloudflare, including 14 of the 27 news outlets.
  - Cloudflare has blocked known AI crawlers by default on new domains since July 2025 (secondary source).
  - So an absence can be a hosting default, not the outlet's choice.
- **The assistant prefers other sources.** Examples are English Wikipedia and pan-Arab outlets. The Stanford study found English Wikipedia among the top 3 domains for Arabic questions.

### Caveats

- **robots.txt is a request, not enforcement.** OpenAI says its rules may not apply to ChatGPT-User. Perplexity says Perplexity-User generally ignores them.
- **Blocking does not mean absence.** A vendor study (BuzzStream) found 82.4% of sites that block OAI-SearchBot were still cited. Pages also reach assistants through syndicated copies and third-party indexes.
- **This is a single snapshot.** 9 Libyan hosts could not be fetched (DNS, TLS and two Cloudflare challenges). Almost all of them have 0-1 articles, which looks like dead register entries.
- **Keep it as a column.** The lens should store each outlet's robots stance as an explanatory column, refreshed rarely. Then "never cited" can be read as blocked, not indexed, or not chosen.

---

## 4. Method

### Question set

- **Size and structure.** 8 topics: the six themes (security, migration, economy, services, health, governance), one gender question and one place question.
  - MVP: one plain wording per topic, in Arabic and in English.
  - Fuller option: a second, short search-style wording per topic, since EBU built its questions from real audience search queries.
- **Wording rules.**
  - Neutral wording that does not assume a crisis.
  - No person is named.
  - The assistant is never asked to cite. EBU and Stanford both warn that telling the model to cite, or to use certain sources, changes which outlets appear.
- **Who writes them.** The owner writes the final list. A native speaker checks the Arabic against the glossary in `docs/i18n.md`.
- **Draft examples:**

| # | Theme | English | Arabic |
|---|---|---|---|
| 1 | Security | What is the current security situation in Libya? | ما هو الوضع الأمني الحالي في ليبيا؟ |
| 2 | Migration | What is the latest on migrants and refugees in Libya this month? | ما آخر المستجدات بشأن المهاجرين واللاجئين في ليبيا هذا الشهر؟ |
| 3 | Economy | What is the latest on the Libyan dinar exchange rate and cash availability at banks? | ما آخر المستجدات بشأن سعر صرف الدينار الليبي وتوفّر السيولة النقدية في المصارف؟ |
| 4 | Services | What is the state of electricity and water supply in Libya at the moment? | ما وضع إمدادات الكهرباء والمياه في ليبيا حاليًا؟ |
| 5 | Health | What is the state of hospitals and health services in southern Libya? | ما وضع المستشفيات والخدمات الصحية في جنوب ليبيا؟ |
| 6 | Governance | What is the latest news on elections in Libya? | ما آخر الأخبار عن الانتخابات في ليبيا؟ |
| 7 | Gender | What are the latest developments on women's rights in Libya? | ما آخر التطورات المتعلقة بحقوق المرأة في ليبيا؟ |
| 8 | Place | What is the latest news from Kufra? | ما آخر الأخبار من الكفرة؟ |
| 9 | Place (alt) | What is happening in the Fezzan region this week? | ماذا يحدث في منطقة فزان هذا الأسبوع؟ |
| 10 | Search-style wording (fuller option) | Libya fuel supply | إمدادات الوقود في ليبيا |

- **Framing arm.** Prior audits compared neutral and leading wording on contested topics (ISD, Gazzetta). I do not recommend one in v1. On contested Libyan topics it is sensitive, and your three questions do not need it.

### Repeats and variation

Answers vary a lot from run to run:

- Citation overlap between two identical runs was only 13-31% (Gazzetta).
- Weekly domain replacement was 56-74% (SISTRIX).
- Lists of named sources almost never repeat exactly, but whether a given source appears at all is fairly stable (SparkToro).

So the lens:

- asks each question in each language once a week in the MVP, and twice in the fuller option;
- runs the first (pilot) week twice anyway, to measure run-to-run overlap. That run is manual and goes outside the weekly cap, or the cap is raised for that week, because two MVP runs cost about $1.12;
- reports **presence over rolling 4-week windows**, never ranks or single snapshots;
- always shows n. The MVP gives 64 answers per 4 weeks per assistant, so "never cited" is weak evidence about any single outlet.

### Location and request settings

- **Location.**
  - Set `user_location` to Libya (Tripoli, `Africa/Tripoli`) wherever the API accepts it. One Phase 0 call per provider settles whether `LY` is accepted.
  - If Claude rejects `LY`, send city and timezone without a country, since at least one field is required. Record what was sent.
  - OpenAI must be given a location explicitly, or it defaults to the US.
- **Server location.** The server runs in London (Fly region `lhr`, `fly.toml`). No provider documents whether the calling server's IP shapes API search results. Record the region on each run. In Phase 0, compare one call with `user_location` and one without.
- **Baseline.** Fuller option: add one baseline country other than Libya. Language and location act separately (arXiv 2608.30052).
- **Request rules.**
  - A new conversation for every question.
  - No domain filters.
  - No instruction about sources. The only exception is one line giving today's date, which Anthropic's Haiku 5.5 guide recommends when the model has a search tool, and which the "this week" and "this month" questions need. Whether to add it is an owner decision.
- **Direct calls only.** Call each provider's own API, never a gateway. The first Persian audit was retracted because OpenRouter silently fell back to another search index.
- **Pacing.** Calls run one after another, with at least 1 second between them (Perplexity Tier 0 allows 1 request per second).

### Recorded per answer

- **Provider and settings:** provider, model ID, tool version, settings (location sent, `max_uses` / `max_tool_calls`), Fly region, timestamp, question ID and version, and the language asked.
- **Status:** ok; `no_search` (answered without searching, which is a finding in itself); refused; rate_limited; or error.
- **Queries:** the assistant's own search queries, with a language tag. **These stay admin-only**, because the model may search for a person's name even when the question names no one. Journalists see only counts.
- **Searched list:** each item's URL, title (where the API gives one; OpenAI does not), `page_age` or date, and list position.
- **Cited list:** each link's URL and the number of citation spans pointing at it.
- **Answer:** its language and length, worked out in memory. **The answer text itself is not stored**, because of the private-names rule, copyright and the provider terms. `cited_text` is not stored either.
- **Usage and cost:** tokens, number of searches and cost.
- Raw responses are dropped once parsed.

### Mapping domains to outlets

A new read-only matcher reuses `ingest.domain_of`, `normalise_url`, `social_outlet`, `galerts.unwrap` and `dedupe.outlet_families`. It must not use `ingest.resolve_outlet`, because that function creates `Outlet` rows for unknown domains (`ingest.py:163-172`). The matcher works in this order:

1. Unwrap Google `url?q=` and AMP links, and remove tracking parameters. `utm_source` is already in `_TRACKING`; add `srsltid`.
2. Match path outlets (`hrw.org/ar`), then the exact host, then the parent domain, longest known suffix first. So `arabic.cnn.com` becomes `cnn.com`, never `co.uk`. The existing fallback tries only the last two labels.
3. Map social posts to the register account. Unlisted accounts are stored as the platform only, so a private person's account is never stored.
4. Treat a website and its own social accounts as one outlet family.
5. Keep unknown domains with no outlet, and flag unregistered `.ly` domains. **Never create an Outlet.**
6. Tag each link's language from its title, then from URL markers, then from the outlet's languages. OpenAI's searched list has no titles, so it uses the last two only. Language editions stay separate (aljazeera.net vs aljazeera.com, ar. vs en.wikipedia).
7. Re-run the matching over stored rows when the register changes.
8. One register fix is needed first. `bbc.com` is registered as "BBC Arabic" with languages `[ar]` (`libya.yaml:163`), so English BBC links would be counted as Arabic.

### Metrics (all per assistant, never added across assistants)

- **Sources per answer:** searched and cited, as median and range. For Perplexity, cited is shown only where markers are present.
- **Share of cited sources by scope:** Libyan / diaspora / international / unknown / not in register. This sits next to Desert Watch's own monitored-coverage mix, labelled as a different unit.
- **Arabic vs English:**
  - the language of the queries;
  - the language of the cited sources, split by the language the question was asked in;
  - the rate of answers with no search, and of answers with no direct link, per language.
- **Outlets never cited:** Libyan register outlets with counted articles in the last 12 weeks that no assistant cited in the window. Each is split into "appeared in results but was never cited" and "never appeared in results".
- **Blocking vs citation:** each outlet's robots stance (section 3) next to its citation count.
- **Citation stability:** overlap of cited domains week to week. Within a week, this needs the second run (pilot week or fuller option).
- **Optional check that a cited page supports the sentence:** a small manual sample on the Admin page.
  - It is coded with the EBU toolkit's sourcing categories, with about 10% double-coded, as the Reuters Institute did.
  - It needs the answer text, and Claude's `cited_text`, kept admin-only for a short time (decision 8).
  - OpenAI returns no source text.

### What stays unscored

The audit writes only its own tables. It never writes `Item`, `ItemTheme` or `CellWeek`, so gap scores, lenses and the digest cannot see it. A test checks that the `item` and `cell_week` counts are unchanged after a run. There are no composite visibility scores and no league tables.

---

## 5. How it fits Desert Watch

### Data model

Four new tables, created by `create_all`:

| Table | Holds |
|---|---|
| `ai_question` | The bilingual question set, versioned. Seeded from an `ai_audit:` block in `config/countries/libya.yaml`. |
| `ai_run` | One row per assistant per week: model, tool, settings, Fly region, status (ok / partial / error / awaiting_key / over_budget), usage, `cost_usd`, and `price_basis` with an `as_of` date. |
| `ai_answer` | One row per question per language per run: status, answer language, queries (admin-only), searched and cited counts. |
| `ai_source` | One row per searched or cited link: role, rank, URL, domain, outlet and family, match type, title (admin-only), language, date. |

**What each API calls "searched" and "cited":**

| Provider | Searched | Cited |
|---|---|---|
| Claude | `web_search_result` items | `web_search_result_location` |
| OpenAI | `action.sources` (URLs only) | `url_citation` |
| Perplexity | `search_results` | `[n]` markers, where present |

Because the definitions differ, counts are never summed across assistants.

### Job and schedule

- **When:** Monday 04:20 UTC, through the existing APScheduler in `jobs.py`. That is after the nightly full recompute at 03:30 and before the Monday digest at 06:00. The digest also re-runs Tuesday to Thursday at 06:00.
  - The full recompute or the hourly jobs (:07 collectors, :45 recompute) may still hold `_LOCK` when the audit is ready to write. The write phase then waits, with a timeout.
- **Manual runs:**
  - An Admin button with a cost confirmation.
  - `python -m app.cli ai-audit [--provider X] [--force] [--dry-run]`. A dry run lists the planned calls and the estimated cost without making any call.
- **Lock handling:** the API calls run outside `_LOCK`, and each assistant's results are written in one short locked transaction. `weekly_digest` is different: it is wrapped in `@_locked` and holds the lock through its model call. Copying that would hold up the hourly collectors for the whole run.
- **Repeat runs:** one run per (week, assistant, model) unless forced.
- **Caps:**
  - `max_uses` 3 per question;
  - a weekly dollar cap;
  - 15 minutes per assistant;
  - stop an assistant after 3 refused or rate-limited requests in a row (`collectors/base.py` `STOP_AFTER`).

### UI (bilingual, every string through `t()` / `tr()`)

- **Outlets page:** a new `AiAnswers.jsx` card below Blind Spots.
  - Controls: assistant; asked in Arabic / English / both; 4 or 12 weeks.
  - Two scope bars: monitored coverage vs cited sources, labelled as different units.
  - A top-sources table listing outlets and domains (not individual URLs, whose slugs can carry names). It links to the outlet's site and opens the existing outlet panel.
  - "Never cited" chips and a language line.
  - Caveat text: these are developer-API answers, not the apps; one fixed question set; counts per assistant; unscored; the answers are not kept.
- **Outlet panel:** one line, for example "Cited by AI assistants: 3 times in 4 weeks".
- **Admin page:**
  - a runs and costs table;
  - a per-answer drill-down showing the queries and the searched and cited URLs with titles;
  - an unknown-domains list;
  - the run button.
- **Health strip:** one `EXTRA_HEALTH` entry per assistant, stale after 8 days.
- **Overview, Trends and digest:** nothing in v1.
- **New glossary terms,** to be agreed in `docs/i18n.md` and reviewed by a native speaker: مساعد ذكاء اصطناعي, مصدر مُستشهد به, ظهر في نتائج البحث, مجموعة الأسئلة.

### Keys and cost display

- **New keys:** `OPENAI_API_KEY` and `PERPLEXITY_API_KEY`. Each shows "awaiting key" until the owner sets it as a Fly secret. Claude never sets keys.
- **Claude switch:** the digest's `ANTHROPIC_API_KEY` must not start the audit on its own. The audit needs an explicit `DW_AI_AUDIT_ANTHROPIC=1`, off by default, and until then the status says so.
- **Costs:** a dated price table in `config/ai_audit.yaml` drives three things:
  - `cost_usd` per run;
  - the weekly cap;
  - a year-to-date total on Admin.

  No dollar cost is shown anywhere today: the digest stores tokens only (`digest.py:206`). The same table can give the digest a cost figure (0.25 day).

### Reuse

| Need | Existing code |
|---|---|
| Run log, awaiting key | `collectors/base.py` (`AwaitingKey`, `refused`, `STOP_AFTER`, `polite_get`); `jobs.weekly_digest` |
| Scheduling, manual runs | `jobs.py` (`start_scheduler`, `JOBS`, `_LOCK`, `model_job`); `api/admin.py` job runner; `cli.py` |
| Anthropic client | `digest.py` (`_client`, usage capture, refusal handling) |
| URLs and domains | `ingest.py`, `galerts.unwrap`, `dedupe.outlet_families` |
| Google News headline match | `resolve.title_score` / `best_copy` |
| Language | `textnorm.detect_lang` |
| UI pieces | `MixBar`, `DIMENSIONS`, `BlindSpots.jsx` card pattern, `openOutlet` |

OpenAI and Perplexity calls go through plain `httpx`, so there are no new dependencies.

### Server load (one 512 MB machine, 1 GB swap)

- **Memory:** responses are about 50-300 KB of JSON each, parsed one at a time, for a peak of about 10-30 MB. No local model. An optional child process gives the memory back afterwards (0.25 day).
- **CPU:** negligible.
- **Disk (estimate):** Claude alone in the MVP writes about 500-600 source rows a week (48 searches × up to about 10 results, plus citations). That is about 30k rows and under 10 MB a year. The fuller option, with 120 answers a week, is roughly 150-200k rows and 50-80 MB a year.
- **Network:** 16 API calls a week in the MVP, up to about 120 in the fuller option, plus any `pause_turn` continuations.
- **Lock:** held for under a second per assistant.

---

## 6. Cost

Per-answer figures are estimates. They assume 3 searches and about 30k input tokens per answer; the token volume per search is not documented. A month is taken as 4.33 weeks.

| Option | Provider (model) | Answers / week | Est. $ / answer | $ / week | $ / month |
|---|---|---|---|---|---|
| **MVP** | Claude (Haiku 5.5), `max_uses` 3 | 8 q × 2 lang × 1 = 16 | ~0.035 | ~0.56 (search fees ≤0.48) | **~2.40** |
| MVP + ChatGPT | + OpenAI (gpt-6-luna) | +16 | ~0.035 | +0.56 | **~4.85** total |
| **Fuller** | Claude | 10 q × 2 lang × 2 = 40 | ~0.035 | ~1.40 | ~6.05 |
| | OpenAI | 40 | ~0.035 | ~1.40 | ~6.05 |
| | Perplexity (sonar) | 40 | ~0.004-0.01 | ~0.16-0.40 | ~0.70-1.75 |
| | **Fuller total** | 120 | | ~2.96-3.20 | **~12.80-13.85** |
| Leanest Claude | Claude, 6 q × 2 lang × 1, `max_uses` 3 | 12 | ~0.035 | ~0.42 (search fees ≤0.36) | ~1.80 |

The pilot week's double run costs about $1.12 for Claude, so it must sit outside a $1 weekly cap (section 4). The OpenAI figure is the least certain: reasoning tokens bill as output, and the docs do not say whether `open_page` actions bill as calls.

### Compared with the digest

The digest is one Haiku 5.5 call a week, with output capped at 4,000 tokens (`digest.py:196`) and a small facts dict as input. The local DB copy has no digest usage rows, so its real size cannot be quoted. Even at its 4,000-token output cap, the digest costs well under $0.01 a week.

The MVP makes 16 calls a week at an estimated ~30k input tokens each, about 0.5M input tokens a week. That is roughly 25 to 100 times the digest's tokens, depending on its real size. In dollars it is about $0.56 a week against well under $0.01, and most of it is the per-search fee, not tokens.

### Fitting the near-zero rule

**The audit would be by far the app's largest use of a language model.** It is a deliberate exception to "almost no tokens", and only the owner can approve it.

The smallest defensible version is the MVP:

- Claude only, 16 answers, `max_uses` 3;
- a hard weekly cap of $1;
- off until `DW_AI_AUDIT_ANTHROPIC=1` is set;
- matching and metrics in plain code, with no further model calls.

Its weakness is that it measures the assistant Libyans use least. Adding OpenAI doubles the cost and covers about 60% of Libyan chatbot referrals.

---

## 7. Phases and effort

Day figures come from the codebase review (developer-days including tests) unless marked as my estimate.

| Phase | Contents | Days |
|---|---|---|
| **0. Checks** | A small probe script (part of the CLI) that the owner runs with their own keys, locally or with `fly ssh console`. Claude writes it but never holds or sets keys. It checks that Haiku 5.5 accepts `web_search` (Models API), that `user_location` `LY` is accepted, the effect of sending no location, and the real response shapes. Then a 5-question pilot per language per provider. | 0.5-0.75 (my estimate) |
| **1. MVP (Claude, admin-only view)** | Tables, config and question seed (0.75); domain matcher with rematch CLI (2.0); Claude adapter (1.0); weekly job, keys, cost table, cap, dry-run (1.25); API routes plus the unscored and privacy tests (1.25); Admin runs, costs and drill-down (0.75); Arabic catalogues and glossary (0.75); method doc in `how_the_numbers_work`, both languages (0.5); first live run, real fixtures, fixes (0.75) | **9.0** |
| **2. Show it to journalists, add ChatGPT** | Outlets card and outlet-panel line (1.75); OpenAI adapter (0.75) | 2.5 |
| **3. Fuller method** | Perplexity Agent API adapter (0.5-0.75; the codebase review's 0.5 assumed the older Sonar shape); second weekly run, the stability metric and a non-Libya location baseline (about 0.5, my estimate); robots stance column with a monthly polite refresh, reusing the survey scripts (about 1.0, my estimate) | ~2.0-2.25 |
| **4. Options** | Digest cost display 0.25; child-process job 0.25; local-run plus import route 0.5; over-time view after 8+ weeks (about 1.0, my estimate); manual support-check sample on Admin (about 1.0, my estimate) | up to 3.0 |

**Totals:**

| Scope | Days |
|---|---|
| Phases 0-1 | ~9.5-9.75 |
| Phases 0-2 | ~12-12.25 |
| Phases 0-3 | ~14-14.5 |

For comparison, the codebase review's own totals were 10.75 days for Claude only, 11.5 for Claude + OpenAI, and 13.0 for four assistants. The 13.0 figure included a Gemini adapter, which this scope leaves out.

---

## 8. Risks and limits

| Risk | Mitigation |
|---|---|
| **Terms of service.** Gemini and Bing forbid storing and analysing results, and Google also restricts how and to whom results are displayed. OpenAI requires visible, clickable citations. Anthropic requires cited sources when output is shown. Perplexity has an embargo clause. | Leave Gemini and Bing out. Show outlet names with links to the outlets. Never show or store answer text. Re-read the terms before each new provider is switched on. |
| **Terms against competing or evaluating.** Anthropic, OpenAI and Google bar using outputs to build competing models. Microsoft also bars using output to evaluate AI models. | Desert Watch builds no model, so the risk is low. Re-read each provider's terms before publishing any comparison of assistants. Bing stays excluded. |
| **Provider region rules.** Libya is not an Anthropic-supported region. Meta restricts Libya outright. | The server and owner are in the UK, and journalists in Libya already see the Haiku digest. The audit shows them only derived counts. The owner should confirm the account terms are comfortable with this, as they already are for the digest. |
| **Answer variance.** Run-to-run citation overlap is 13-31%, and weekly domain churn is 56-74%. | Rolling 4-week presence, n always shown, no ranks. Stability is reported as a metric in its own right. |
| **Hallucinated or wrong citations.** The Tow Center found over 60% of answers wrong on citation. EBU found sourcing problems in 31% of answers, including "ceremonial citations" that do not support the claim. | Count only URLs the API returned as results or citations. Keep searched and cited separate. Use the optional manual support check. Present the lens as "what they cite", not "what is true". |
| **Model updates.** | Log the model ID and tool version on every run. Treat a change as a break in the series and mark it in the UI. Store `price_basis` with each run. |
| **Consumer-vs-API gap.** | Label the lens "developer-API answers" everywhere. Do not claim it shows what users see. Say plainly that Meta AI, AI Overviews and Gemini are not covered. |
| **Location confound.** The server is in London. OpenAI defaults to the US. Claude may reject `LY`. | Record the location sent and the Fly region on every run. Phase 0 compares calls with and without a location. Never compare runs made with different location settings. |
| **Rate limits.** Anthropic's organisation web-search limit is unpublished and returns `too_many_requests` inside an HTTP 200. Perplexity Tier 0 allows 1 request per second. | Run calls one after another with gaps. Record `rate_limited` as a status. Stop after 3 in a row. Unbilled failed searches cost nothing. |
| **Cost creep.** | `max_uses` 3. A weekly dollar cap that stops the job and marks it `over_budget`. A dry-run estimate before manual runs. Year-to-date cost on Admin. Haiku 5.5 prompts kept under the 100k-token price step. Each provider is opt-in by key or switch. Set a low spend limit in each provider's console where it allows one. |
| **Sensitive themes and private names.** Answers, the assistant's own queries, result titles and URL slugs may name private individuals, or touch on armed groups and migrants. | Questions name no person. Answer text and `cited_text` are not stored. Queries, titles and URLs are admin-only, and journalists see outlet- and domain-level counts. Unlisted social accounts are stored as the platform only. Refusals are recorded as a status and not retried with new wording. |
| **The app becoming a target.** Published tallies of which outlets AI cites could draw pressure from outlets or authorities, or invite attempts to game the lens. | Invite-only as now. Admin-only for the first 4 weeks. Publish the method, not rankings. Any public release of findings is a separate owner decision. |
| **Leaked or misused keys.** | Keys live only in Fly secrets, which the owner sets. The Phase 0 probe is run by the owner. |
| **Untrusted text in search results.** | Do not enable `web_fetch` (Anthropic warns of exfiltration risk), and put nothing secret in prompts. |
| **Small samples.** EBU warns that about 30 answers per assistant per language is not robust. | No comparison between languages or assistants is presented as a ranking. "Never cited" is shown as presence over a window, with n. |

---

## 9. Decisions for the owner

1. **The token exception:** do you accept the audit as a deliberate exception to "almost no tokens" (section 6)?
2. **Providers for the MVP:** Claude only, or Claude plus OpenAI?
3. **Keys and switches you will set:** `DW_AI_AUDIT_ANTHROPIC=1` (uses the digest's key), `OPENAI_API_KEY`, `PERPLEXITY_API_KEY`. Which, and when?
4. **Weekly dollar cap:** $1 suggested for the MVP, with the pilot week's double run allowed outside it.
5. **Phase 0 probe:** will you run it with your keys (recommended), locally or on Fly?
6. **Question themes:** the six themes plus gender plus one place (Kufra or Fezzan). Approve or edit? Who checks the Arabic?
7. **Languages:** Arabic and English both? (Recommended.)
8. **How often:** one run a week, or two (better for variance, double the cost)?
9. **Answer text:** not kept (recommended), or kept admin-only for 28 days so the manual support check is possible?
10. **Location:** set `user_location` to Libya? Add a baseline from another country later?
11. **Date line:** may the request include a one-line system prompt giving today's date and nothing else?
12. **Who sees results:** admins only for the first 4 weeks, then all journalists?
13. **Publishing:** publish the method and question set? Publish findings, and if so, when?
14. **Gemini:** leave it out (recommended, since both the storage and the display terms conflict), or ask Google for written permission?
15. **Register fix:** split `bbc.com` from "BBC Arabic", for example by adding a `bbc.com/arabic` path outlet?
16. **Digest:** may a later digest mention the audit? (Not in v1.)

---

## 10. Sources

**Anthropic** (all accessed 2026-10-18 unless dated; the web search, pricing and tool reference pages were re-read on 18 Oct)
- Web search tool: https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool
- Server tools, domain filters, ZDR, pause_turn: https://platform.claude.com/docs/en/agents-and-tools/tool-use/server-tools
- Web fetch tool: https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-fetch-tool
- Tool versions: https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-reference
- Pricing: https://platform.claude.com/docs/en/about-claude/pricing
- Haiku 5.5 overview (released 2026-10-07): https://platform.claude.com/docs/en/models/haiku-5-5/overview
- Haiku 5.5 prompting guide: https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-haiku-5-5
- Models API capabilities: https://platform.claude.com/docs/en/models/overview
- Rate limits: https://platform.claude.com/docs/en/api/rate-limits
- Multilingual support: https://platform.claude.com/docs/en/build-with-claude/multilingual-support
- Supported regions (Libya absent): https://platform.claude.com/docs/en/api/supported-regions
- Consumer system prompts (2026-09-22): https://platform.claude.com/docs/en/release-notes/system-prompts/claude-opus-5-5
- Claude.ai web search help: https://support.claude.com/en/articles/10684626
- Crawlers (updated 2026-04-07): https://support.claude.com/en/articles/8896518
- Commercial Terms (effective 2025-06-17): https://www.anthropic.com/legal/commercial-terms
- Service Specific Terms (effective 2026-08-31): https://www.anthropic.com/legal/service-specific-terms
- Brave as search provider, third-party report (2025-03-21): https://techcrunch.com/2025/03/21/anthropic-appears-to-be-using-brave-to-power-web-searches-for-its-claude-chatbot/
- turbopuffer, third-party analysis: https://xponent21.com/insights/claude-web-search-brave-turbopuffer/

**OpenAI**
- Web search guide (re-read 18 Oct): https://developers.openai.com/api/docs/guides/tools-web-search
- Responses create reference: https://developers.openai.com/api/reference/resources/responses/methods/create
- Pricing: https://developers.openai.com/api/docs/pricing
- gpt-6-luna: https://developers.openai.com/api/docs/models/gpt-6-luna
- gpt-5-nano: https://developers.openai.com/api/docs/models/gpt-5-nano
- Models list: https://developers.openai.com/api/docs/models
- Service Terms (updated 2026-10-16): https://openai.com/policies/service-terms/
- Your data: https://developers.openai.com/api/docs/guides/your-data
- Launch post (2025-03-11): https://openai.com/index/new-tools-for-building-agents/
- ChatGPT search help: https://help.openai.com/en/articles/9237897-chatgpt-search
- Bots: https://developers.openai.com/api/docs/bots
- Supported countries (via search snippets): https://help.openai.com/en/articles/5347006-openai-supported-countries-and-territories

**Perplexity**
- Migration overview: https://docs.perplexity.ai/docs/agent-api/migrate-from-sonar/overview.md
- Migration how-to: https://docs.perplexity.ai/docs/agent-api/migrate-from-sonar/how-to.md
- Web search tool: https://docs.perplexity.ai/docs/agent-api/tools/web-search.md
- Pricing: https://docs.perplexity.ai/docs/getting-started/pricing.md
- Rate limits: https://docs.perplexity.ai/docs/admin/rate-limits-usage-tiers.md
- Language filter: https://docs.perplexity.ai/docs/search/filters/language-filter.md
- API Terms (2026-01-23): https://www.perplexity.ai/hub/legal/perplexity-api-terms-of-service
- Acceptable Use Policy (2025-07-08): https://www.perplexity.ai/hub/legal/aup
- Bots: https://docs.perplexity.ai/guides/bots

**Google**
- Grounding (generateContent, 2026-10-13): https://ai.google.dev/gemini-api/docs/generate-content/google-search
- Grounding (Interactions API): https://ai.google.dev/gemini-api/docs/google-search
- Pricing (2026-10-16): https://ai.google.dev/gemini-api/docs/pricing
- Gemini API terms (2026-04-28; re-read 18 Oct): https://ai.google.dev/gemini-api/terms
- Google Cloud service terms, section 20(k) (2026-10-12): https://cloud.google.com/terms/service-terms
- Vertex grounding: https://docs.cloud.google.com/vertex-ai/generative-ai/docs/grounding/grounding-with-google-search
- Redirect-URL feature request (2025-10-12): https://discuss.ai.google.dev/t/feature-request-provide-actual-source-urls-in-grounding-metadata/107352
- Available regions: https://ai.google.dev/gemini-api/docs/available-regions
- AI Overviews expansion (2025-05-20): https://blog.google/products/search/ai-overview-expansion-may-2025-update/
- Google crawlers: https://developers.google.com/search/docs/crawling-indexing/google-common-crawlers
- AI features and your site: https://developers.google.com/search/docs/appearance/ai-features

**Microsoft, Meta, xAI, DeepSeek, Mistral**
- Bing grounding (2026-07-11): https://learn.microsoft.com/en-us/azure/ai-foundry/agents/how-to/tools/bing-grounding
- Bing grounding terms (2025-11): https://www.microsoft.com/en-us/bing/apis/grounding-legal
- Bing APIs pricing: https://www.microsoft.com/en-us/bing/apis
- Meta search grounding: https://dev.meta.ai/docs/search-grounding.md
- Meta pricing: https://dev.meta.ai/docs/pricing-rate-limits.md
- Muse Spark preview (2026-07-08): https://dev.meta.ai/resources/blog/build-with-muse-spark/
- Meta Geographic Use Policy (2026-10-12): https://dev.meta.ai/legal/geographic-use-policy
- Meta AI in Arabic (2025-02-25): https://anba.com.br/en/meta-ai-launched-in-arabic/
- xAI citations: https://docs.x.ai/developers/tools/citations.md
- xAI web search: https://docs.x.ai/developers/tools/web-search.md
- xAI pricing: https://docs.x.ai/developers/pricing.md
- DeepSeek search: https://api-docs.deepseek.com/guides/search
- DeepSeek Anthropic-compatible API: https://api-docs.deepseek.com/guides/anthropic_api
- Mistral web search: https://docs.mistral.ai/agents/connectors/websearch/
- Mistral pricing: https://mistral.ai/pricing

**Usage data**
- StatCounter Libya chatbots (September 2026): https://gs.statcounter.com/ai-chatbot-market-share/all/libya
- StatCounter Libya Google vs ChatGPT: https://gs.statcounter.com/google-vs-chatgpt-market-share/all/libya
- StatCounter Africa chatbots: https://gs.statcounter.com/ai-chatbot-market-share/all/africa
- StatCounter Egypt chatbots: https://gs.statcounter.com/ai-chatbot-market-share/all/egypt
- StatCounter Tunisia chatbots: https://gs.statcounter.com/ai-chatbot-market-share/all/tunisia
- StatCounter on referral shares (2026-04-02): https://gs.statcounter.com/press/google-gemini-overtakes-perplexity-to-become-second-largest-source-of-ai-chatbot-referrals-to-websites
- DataReportal Libya 2026: https://datareportal.com/reports/digital-2026-libya
- Reuters Institute Digital News Report 2026: https://reutersinstitute.politics.ox.ac.uk/digital-news-report/2026/dnr-executive-summary

**Prior audits**
- Tow Center (March 2025): https://www.cjr.org/tow_center/we-compared-eight-ai-search-engines-theyre-all-bad-at-citing-news.php
- Tow Center (November 2024): https://www.cjr.org/tow_center/how-chatgpt-misrepresents-publisher-content.php
- EBU/BBC report (October 2025): https://www.ebu.ch/research/open/report/news-integrity-in-ai-assistants
- EBU/BBC toolkit: https://www.ebu.ch/research/open/report/news-integrity-in-ai-assistants-toolkit
- Reuters Institute, UK election chatbots (September 2024): https://reutersinstitute.politics.ox.ac.uk/how-generative-ai-chatbots-responded-questions-and-fact-checks-about-2024-uk-general-election
- Reuters Institute, Generative AI and News 2025: https://reutersinstitute.politics.ox.ac.uk/generative-ai-and-news-report-2025-how-people-think-about-ais-role-journalism-and-society
- Stanford / Together AI (May 2026): https://arxiv.org/abs/2605.22785
- Factnameh, first run (retracted): https://factnameh.substack.com/p/how-five-ai-models-source-iran-related
- Gazzetta, rebuilt run (August 2026): https://www.gazzetta.xyz/iran-ai-updated.md
- ISD (2025-10-27): https://www.isdglobal.org/?p=25635
- University of Zurich / Konstanz (secondary): https://swissinfo.ch/eng/science/swiss-study-finds-language-distorts-chatgpt-information-on-armed-conflicts/88332931
- "The Language of the Question Selects the Market": https://arxiv.org/abs/2608.30052
- "Sources of Truth": https://arxiv.org/abs/2609.00319
- Profound, citation patterns: https://www.tryprofound.com/blog/ai-platform-citation-patterns
- Profound, citation drift: https://tryprofound.com/blog/ai-search-volatility
- Peec AI, ChatGPT providers: https://docs.peec.ai/research/chatgpt-search-result-providers
- SparkToro (secondary): https://www.searchenginejournal.com/ai-recommendations-change-with-nearly-every-query-sparktoro/566242
- SISTRIX (2026-05-01): https://www.sistrix.com/blog/ai-citation-drift/
- Genezio: https://genezio.com/research/zero-query-overlaps/
- arXiv 2610.15382: https://arxiv.org/abs/2610.15382
- AfricTivistes / DRI: https://africtivistes.com/en/ai-in-elections-and-the-challenge-to-information-integrity/
- BuzzStream: https://www.buzzstream.com/?p=11713
- Cloudflare on Perplexity: https://blog.cloudflare.com/perplexity-is-using-stealth-undeclared-crawlers-to-evade-website-no-crawl-directives/
- Cloudflare Content Signals: https://blog.cloudflare.com/content-signals-policy/

**Desert Watch evidence (local)**
- Robots survey, 2026-10-18: `docs/research/ai_crawlers_robots_2026-10-18.md` (method and full table) and `docs/research/ai_crawlers_robots_2026-10-18.json` (per-host results)
- Codebase read at `C:\dev\desert-watch`, `main` at ca4f220:
  - `backend/app/digest.py:196,206`
  - `backend/app/settings.py:26,33`
  - `backend/app/ingest.py:14,153-172`
  - `backend/app/jobs.py:14-22,191-210,237-245`
  - `backend/app/collectors/base.py:19,56`
  - `config/countries/libya.yaml:163`
  - `fly.toml` (`primary_region = "lhr"`, 512 MB, 1 GB swap)

---

## Review notes

**Facts re-checked (18 Oct 2026):**
- Anthropic's web-search and pricing pages confirm $10 per 1,000 searches, Haiku 5.5 at $0.10/$0.50 (with the 100k price step), `cited_text` of up to 150 characters, and the citation-display note.
- The tool reference and the web-search page still do not list Haiku 5.5 as supporting web search, so the Models API check stays.
- The OpenAI guide confirms that queries come in most cases but not always, that `action.sources` is the complete list of consulted URLs, the clickable-citation rule, and the minimal-reasoning caveat. The guide itself gives no `user_location` default, so the US default is now credited to the API reference.
- Google's Gemini API terms confirm the display, no-analysis and link-collection bans.

**Arithmetic and estimates fixed:**
- Leanest Claude option: 12 × $0.035 is $0.42 a week, not "≤0.40". The old figure counted search fees only.
- Fuller per-provider monthly cost: $1.40 × 4.33 is $6.06, not $6.10. Totals adjusted.
- Network calls: the fuller option makes up to about 120 a week, not "16-80".
- Disk: row counts re-estimated per option. The fuller option is about 50-80 MB a year, not under 15 MB.
- The pilot week's double run (about $1.12) would have hit the proposed $1 cap. It is now run outside the cap.

**Claims corrected:**
- Perplexity: removed the claim that `LY` is a documented example.
- Perplexity's "cited" count is flagged as unreliable, because its markers depend on the prompt.
- OpenAI's searched list has no titles, so title-based language tagging does not apply to it.
- `page_age` is labelled as a last-updated time, not a publication date.
- The Gemini free-tier note is fixed.
- The OpenAI Service Terms point is marked as resting on a single reading.

**Codebase checks:**
- The server is in London (`fly.toml` lhr), so the IP and location confound is added.
- The digest also re-runs Tuesday to Thursday, and the hourly :07 and :45 jobs and the 03:30 recompute can hold `_LOCK`, so the write phase now waits with a timeout.
- `utm_source` is already in `_TRACKING`; only `srsltid` needs adding.
- The Perplexity adapter estimate is raised to 0.5-0.75 days, because the review assumed the older Sonar response shape.

**Owner rules:**
- The audit is now stated plainly as a token exception that needs explicit approval. The draft had said the MVP "uses no model tokens beyond the audit calls", which hid the issue.
- Phase 0 is now run by the owner with their own keys through a probe script. "Approve Claude making them with your keys" is gone, because Claude never handles keys.
- The assistant's queries, result titles and URLs are admin-only, because the model can search for or surface private names even when the question names no one. Journalists see outlet- and domain-level counts.

**Questions:**
- Removed presuppositions: "the cash shortage" became "cash availability", "power cuts or water shortages?" became "state of electricity and water supply", and "fuel shortage" became "fuel supply".
- Widened Q1 from Tripoli to Libya, so the place questions carry the regional angle.

**Risks added:**
- terms against competing models or evaluating AI;
- provider region rules (Anthropic and Libya);
- the location and IP confound;
- rate limits (the unpublished Anthropic org limit, Perplexity's 1 request per second);
- Google's display requirements, written into the Gemini exclusion;
- `store: false` for OpenAI.

**Copyright:** most verbatim quotes from provider docs are now paraphrased, and one short quote from Google's terms is kept.