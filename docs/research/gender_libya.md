# Gender issues in Libya: research basis for the gender themes

Compiled 2026-10-12 from public sources (desk research; feeds probed with curl, Wikipedia
titles checked against the API). Term lists live in `config/themes.yaml` (group `gender`);
the dated events live in `config/countries/libya.yaml` → `events`.

## Matching rule
Never match bare المرأة / نساء / "women" / "female" alone: only multi-word phrases, always
under the Libya relevance guard. Libyan outlets cover Tunisia/Egypt heavily, so Arabic
gender phrases otherwise pull in foreign stories.

## Sub-themes and scope
1. **gender_violence**: femicide, domestic/sexual violence, online harassment/blackmail, the
   stalled VAW law. Femicide "rife" after the UN Special Rapporteur's Dec 2022 visit
   ([Arab News](https://arabnews.com/node/2220926/)); draft law stalled since 2017, 2021 revision
   adds online violence ([CIHRS](https://cihrs.org/libyas-draft-law-on-violence-against-women-a-long-awaited-step-forward-but-meaningless-without-tackling-lawlessness-and-impunity/?lang=en));
   Penal Code art. 424 lets rapists escape by marrying the survivor ([Amnesty 2024](https://www.amnesty.org/en/wp-content/uploads/2024/04/MDE1978582024ENGLISH.pdf)).
2. **gender_political_participation**: quotas, candidates, ministers, attacks on women
   politicians/activists. LPDF roadmap 30% floor ([UNSMIL](https://unsmil.unmissions.org/en/node/55766));
   municipal councils reserve ≥1 seat ([IDEA](https://www.idea.int/democracytracker/report/libya/november-2024)).
3. **gender_legal_status**: personal status, guardianship, child marriage, nationality for
   children of Libyan women married to foreigners (Law 24/2010 makes it optional:
   [HRW 2022](https://www.hrw.org/ar/news/2022/10/28/decree-libyan-womens-non-citizen-children-fails-discrimination-test);
   ~15,000 women affected per [Annahar](https://www.annahar.com/arab-world/north-africa/183280/)).
4. **gender_mobility_morality**: mahram travel rules, airport interrogation, compulsory
   hijab, morality police, ISA "virtue" campaigns ([LFJL](https://www.libyanjustice.org/news/crushing-liberty-relentless-restrictions-on-libyan-women-and-enforced-male-guardianship);
   [HRW](https://www.hrw.org/news/2024/11/13/libyan-ministers-morality-measures-would-violate-womens-rights);
   [ICJ](https://www.icj.org/libya-the-morality-police-must-not-be-reestablished/)).
5. **gender_migrant_detained_women**: sexual violence against migrant/detained women,
   trafficking, sexual slavery (UN FFM: crime against humanity, [UN News](https://news.un.org/en/node/1135052)).
6. **gender_economic_health**: women's work, maternal/reproductive health, GBV services
   ([UNFPA](https://unfpa.org/node/16304)).
7. **gender_lgbtq**: arrests, forced "confessions", prosecutions (ISA videos 28 Dec 2023,
   [Amnesty](https://www.amnesty.org/en/latest/news/2024/02/libya-internal-security-agency-must-end-abuses-in-name-of-guarding-virtue/)).

## Changes made to the researched term lists before import
- Removed as too ambiguous: bare `وزيرة` (catches any female minister abroad), `الطلاق` /
  "divorce", `جهاز الأمن الداخلي` (ISA appears in many non-gender stories), "Fact-Finding Mission".
- Removed country-name exclusions (تونس / مصر / غزة): the exclusion list vetoes on title +
  snippet and would drop Libyan stories that mention a neighbour; the Libya guard handles this.
- Added `المبعوثة الأممية` / "UN envoy" as exclusions for political participation.
- Pejorative terms (الشذوذ الجنسي / الشواذ) are kept **only for matching** because Libyan
  state statements and many headlines use them; never use them as UI labels.
- Unverified: `استمارة سفر النساء` is a coined phrase; verify against Al Wasat / 218 usage.

## Known false-positive risks
Bare المرأة / "women" / الطلاق / وزيرة; التحرش (general harassment); الإتجار بالبشر (mostly
smuggling with no gender angle); "rape" in foreign stories; شبكة دعارة (morality-framed raid
reports); women's sport; fashion/beauty; Tunisia/Egypt/Gaza coverage.

## Seasonal spikes (not events)
8 March, 25 November, the 16 Days (25 Nov–10 Dec), October breast-cancer month.

## Coverage blind spots
The south and east are under-reported; Libyan headlines often avoid naming GBV. Domestic
killings appear as `جريمة قتل` with no gender word, so recall undercounts violence.

## Safety
The ISA has targeted women human-rights defenders who criticised the travel rules
([UN News](https://news.un.org/en/story/2023/07/1138932)). Never surface names of victims or
private individuals from social media; treat ISA "confession" videos as coerced, not evidence.

## Feeds probed (2026-10-12)
Working and added: libyaalahrar.tv, sharikawalaken.media, daraj.media, raseef22.net,
kohljournal.press, cihrs.org, hrw.org (en, ar), unwomen.org, libya.unfpa.org, ohchr.org.
Failing: libyanjustice.org (404), lwpp.org (404), libyaobserver.ly (404), alwasat.ly (403),
218tv.net (406), amnesty.org (403), unsmil (404). Use Google News / Alerts `site:` queries.

## Not confirmed for 2025–26
House of Representatives action on the VAW law; municipal elections phase 2; nationality reform.
