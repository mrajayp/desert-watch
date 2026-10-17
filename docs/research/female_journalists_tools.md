# Tools for female journalists: proposal

Desert Watch is a coverage-gap tracker for journalists covering Libya. This note looks at what the app could add for the women on the team. The research shows five main pressures:

- **Smear campaigns aimed at reputation and "honour".** UNSMIL held a round table of 31 Libyan journalists. 92% of them had been harassed online. Women said they were attacked over nearly everything they published, whatever the topic ([UNSMIL, 3 Jun 2025](https://unsmil.unmissions.org/en/news/they-target-our-reputation-online-attacks-force-libyan-journalists-to-self-censor)).
- **Online abuse turns into offline harm.** OMCT and the Libyan Anti-torture Network document doxing, intimate images shared without consent and defamation campaigns that led on to detention and enforced disappearance. Since 2023 the Anti-Cybercrime Law has been used against women victims on "public morals" grounds ([OMCT/LAN, Nov 2025](https://www.omct.org/site-resources/legacy/Reclaiming-Digital-Safe-Space-for-Women-In-Libya-2025.pdf)).
- **Detention and pressure on families.**
  - In September 2024 the Benghazi Internal Security Agency (ISA) detained a woman TV journalist at her home and took her documents. It later arrested her parents. She was released after about 34 days ([Libya Security Monitor, 18 Sep 2024](https://libyasecuritymonitor.com/journalist-abducted-by-isa-in-the-east/); [22 Oct 2024](https://libyasecuritymonitor.com/?p=8502)).
  - A woman field journalist was made to sign pledges and to report on her colleagues ([Al Jazeera, 3 May 2025](https://www.aljazeera.net/politics/2025/5/3/%d9%8a%d9%88%d9%85-%d8%ad%d8%b1%d9%8a%d8%a9-%d8%a7%d9%84%d8%b5%d8%ad%d8%a7%d9%81%d8%a9-%d9%83%d9%8a%d9%81-%d9%8a%d8%a8%d8%af%d9%88-%d9%88%d8%a7%d9%82%d8%b9)).
- **Searches and questioning.** Phones are searched at checkpoints ([CPJ, 20 Sep 2023](https://cpj.org/2023/09/cpj-safety-advisory-covering-libyas-floods/)). The ISA still questions women who travel alone ([ICJ, 13 Nov 2024](https://www.icj.org/libya-the-morality-police-must-not-be-reestablished/)).
- **Self-censorship and isolation.** Women journalists decide in advance what they can publish, and they report almost no institutional support ([Hounna, 30 Mar 2026](https://hounna.net/%D8%B5%D8%AD%D9%81%D9%8A%D8%A7%D8%AA-%D9%84%D9%8A%D8%A8%D9%8A%D8%A7-%D8%AA%D8%AD%D8%AA-%D8%A7%D9%84%D8%B6%D8%BA%D8%B7-%D8%AA%D9%87%D8%AF%D9%8A%D8%AF-%D8%B1%D9%82%D9%85%D9%8A-%D9%88%D9%85%D9%8A%D8%AF/)). Most respondents to the LFJL survey did not know that complaint channels existed ([LFJL, 9 Mar 2021](https://www.libyanjustice.org/news/urgent-action-needed-to-address-shocking-levels-of-online-violence-against-libyan-women)).

A gap tracker cannot stop an attack, take down a post, give legal aid or run a helpline. It can do three things:

1. Send people quickly to the Arabic-speaking services that do that work.
2. Stop being a risk itself. Today one SQLite file holds who is working on which story and what each named user read. Much of that survives deletion.
3. Make under-covered gender stories visible with honest evidence, including attacks on women journalists.

The research suggests, as an inference, that low coverage of gender topics may partly reflect self-censorship for safety rather than low news value. The app should say so wherever it shows a gender gap.

One correction to the brief: Desert Watch has no TOTP today. There is no column, code or dependency for it.

---

## Build first

These four tools take about 22 days in total. Most of the work removes risks the app already carries.

### 1. Close existing leaks, and stop per-person logging on sensitive themes

**What it is.** Fixes to privacy and safety faults in current code. After that, the behaviour log stops storing per-person reading trails on sensitive gender themes.

**Need.**
- A Public Morality Protection Agency (created July 2024) has powers to monitor social media for "deviant" content ([Freedom House, 2025](https://freedomhouse.org/country/libya/freedom-net/2025); [CIHRS, 21 Nov 2024](https://cihrs.org/libya-new-morality-measures-will-impose-authoritarian-hegemony-over-society/?lang=en)).
- The cybercrime law has been used against women victims ([OMCT/LAN, Nov 2025](https://www.omct.org/site-resources/legacy/Reclaiming-Digital-Safe-Space-for-Women-In-Libya-2025.pdf)).
- An ISA forced confession exposed a journalist's sources, and two more people connected to the case were arrested ([US State Dept 2024 report](https://www.state.gov/wp-content/uploads/2025/07/624521_LIBYA-2024-HUMAN-RIGHTS-REPORT.pdf)).

If the server were seized, it would show what each named user read for up to 12 months. It would also show who is working on which theme and region.

**What changes.**

*Fixes to current behaviour (uncontroversial):*
- **Who can resolve a comment.** `backend/app/api/social.py` lines 72-73 let any account, viewers included, mark any comment resolved. Limit this to the author and admins.
- **Safety-tagged comments.** Show them only to the author and admins, and stop writing `{tag:'safety'}` into the event context.
- **Key events.** Show "added by the team" instead of the adder's display name (`backend/app/api/gaps.py` line 498). The Timeline delete button should check a `mine` flag, not compare display names.
- **Access log.** Add `--no-access-log` to the Dockerfile CMD (line 25). With `--proxy-headers`, uvicorn writes the real client IP plus the path and query string to Fly logs.
- **Secure delete.** Set `PRAGMA secure_delete=ON` in the `backend/app/db.py` connect hook, then run one VACUUM.
- **Nightly clean-up.** Delete expired `auth_session` rows. Blank `organisation` and `signup_note` for rejected applicants after 30 days.
- **Account deletion.** Complete `delete_me` in `backend/app/api/account.py`. It should also blank vote and assessment notes, claims, suggestions, feedback and gap-flag item titles. It should set `added_by` on outlet labels and key events to NULL, clear organisation and signup note, regenerate `pseudo_id` and end every session (today it ends only the current one). `export_me` should include the tables it now misses.
- **Stale opt-out text.** Remove it from README line 20, the comment in `frontend/src/api.js` and the `learning.py` docstring. Remove the dead `tracking_opt_out` field from PATCH /me.
- **Digest input.** Drop `recent_gender_headlines` from the Haiku input in `backend/app/digest.py` `build_facts`. This removes the chance of private names reaching the model and saves about 700-900 input tokens a week.

*Quiet logging and retention (your decisions):*
- **Sensitive flag.** Add `sensitive: true` to the sensitive themes in `config/themes.yaml`, as a `Theme.sensitive` column via `ADDED_COLUMNS`.
- **Implicit events.** In `backend/app/learning.py` `record_events`, store implicit events on sensitive themes with pseudo_id `anon`, no `session_id`, and the timestamp cut to the day. Ranking still learns from the aggregate counts.
- **Searches and filters.** Never store search text or filter context that matches a sensitive theme together with a pseudo_id.
- **Claims and comments.** Explicit claim and comment events on sensitive themes lose their `theme:region` key.
- **Correction labels.** Labelling events currently copy the article title, up to 300 characters, into `Event.context` and then `Label.value`. Stop copying it.
- **Retention.** Keep implicit events for 90 days instead of 365 (`RAW_EVENT_RETENTION_DAYS`). Clear `pseudo_id` from correction labels after 90 days.

**Builds on.** `purge_old_events` and `nightly()` in `backend/app/jobs.py`, the theme flag pattern (`strict`, `require_country`), the label anonymising already in `delete_me`, and the fact that no IPs or user agents are stored.

**Required safeguards.**
- Ship the fixes first and present retention and quiet logging as decisions. Before deciding, measure what share of implicit events falls on sensitive themes.
- Backups:
  - Set Fly snapshot retention to the minimum you accept.
  - Delete `/data/backups/pre_review_2026-10-16.db` once you agree.
  - Delete local copies of production in `C:/dev/desert-watch/data` after use, and never sync them to OneDrive.
- Run the VACUUM at a quiet hour with the scheduler paused. It needs free volume space at least as large as the file (about 150-200 MB).

**Effort.** About 6 days. The fixes take about 2.5 of them and can ship on their own.

**Needs from you.** Decisions 1-4 and 16. No keys.

### 2. Bilingual "Get help / مساعدة" page and per-theme "Reporting this safely" notes

**What it is.** One static, Arabic-first page organised by situation, plus short notes on sensitive themes that link into it. The content is human-written, with no model use.

**Need.**
- Most LFJL respondents did not know complaint channels existed ([LFJL, 2021](https://www.libyanjustice.org/news/urgent-action-needed-to-address-shocking-levels-of-online-violence-against-libyan-women)).
- At one UNSMIL training, 92% were concerned about the lack of protective training ([UNSMIL, 7 Aug 2025](https://unsmil.unmissions.org/en/node/56519)).
- One woman journalist removed names and altered details by hand to protect the women she interviewed ([Muwatin, 12 Feb 2026](https://muwatin.net/85639/violence-without-accountability-libyan-women-journalists/)).

**How it works.**

*The Help page, by situation:*
1. **Account hacked or suspended:** [SMEX Helpdesk](https://smex.org/the-digital-safety-helpdesk-at-smex/), [Access Now Helpline](https://www.accessnow.org/help/) (link the help page, not the email address), [Digital First Aid Kit (Arabic)](https://digitalfirstaid.org/ar/).
2. **Attacked online, smeared or doxed:** the Response Hub [documenting guide](https://onlineviolenceresponsehub.org/documenting-an-attack), the [PEN manual in Arabic](https://onlineharassmentfieldmanual.pen.org/ar/), [Totem's Arabic courses](https://totem-project.org/ar/).
   - Keep evidence on your own phone with [Tella](https://tella.app/) or [ProofMode](https://proofmode.org/) (ProofMode is beta). Never upload it to Desert Watch.
3. **Summoned, detained or charged:** [CPJ resources](https://cpj.org/resources/), [MiCT LibyaLegal](https://mict-international.org/project-libyalegal), [Media Defence](https://www.mediadefence.org/apply-for-case-support/) (it has an Arabic form), [LFJL](https://www.libyanjustice.org/).
4. **Emergency money or relocation:**
   - [RSF Assistance Desk](https://rsf.org/en/individual-support)
   - [Free Press Unlimited Reporters Respond](https://www.freepressunlimited.org/) (say plainly that its money can run out)
   - [JiD network](https://www.journalistsindistress.org/)
   - [Front Line Defenders / Security in a Box](https://securityinabox.org/ar/)
   - [Rory Peck Trust](https://rorypecktrust.org/) (home page only)
5. **Harassment in the newsroom:** the [Women in News Arabic toolkit](https://sexualharassment.womeninnews.org/ar/).
6. **Trauma and covering gender-based violence:** [GCJT](https://gcjt.org/), marked English only.

Each entry shows the organisation, its language, what it does and a "last checked" date. The links live in an editable `config/help_links.yaml`, so you can change them without a deploy.

*Per-theme notes* cover:
- Source protection.
- Legal exposure under Law 5/2022 and the 1972 Publications Law ([ARTICLE 19](https://www.article19.org/resources/libya-repeal-anti-cybercrime-law-now); [ARTICLE 19 joint statement, 2 May 2025](https://www.article19.org/ar/resources/libya-protect-press-freedom-support-media-reforms)).
- Digital safety.
- An honest paragraph on what Desert Watch itself records.

**Builds on.**
- The content-serving pattern of `backend/app/content/how_the_numbers_work.md` (`backend/app/api/admin.py` line 337), behind a new non-admin endpoint.
- `polite_get` in `backend/app/collectors/base.py` and the monthly cron slot in `backend/app/jobs.py`, for a link check.
- `rel='noreferrer noopener'` from `frontend/src/components/ArticleRow.jsx`.
- New: `frontend/src/pages/Help.jsx`, `backend/app/content/reporting_notes/<theme>.<lang>.md`, and a collapsible box in `frontend/src/components/GapPanel.jsx`.

**Required safeguards.**
- **Logging.** Drop /help events on the server in `record_events`, with a test. A client-side skip alone is not enough, because `frontend/src/App.jsx` line 34 sends a view event on every route change. Do not log clicks on the outbound safety links either.
- **Link check.** Store a content hash and page title for each link. Any change hides the link until an admin re-approves it, and so do 4xx/5xx responses, redirects to another domain and parked-domain markers.
- **Encryption law.** Put the note on Arts. 9 and 39 of Law 5/2022 above any tool list, in neutral wording. Never say "install X".
- **Legal lines.** Each carries a date, its source, "status unverified" where the research says so, and "Not legal advice".
- **Visibility.** Keep the page behind login.
- **Plain statements on the page:**
  - "Desert Watch is not a helpline; these organisations are."
  - Visiting these links leaves traces in browser history, so use a private window or a separate profile.
- **Review.** A Libyan reviewer checks the Arabic before release. Review the links every quarter.

**Effort.** About 5.5 days: about 2.5 for code and tests, about 3 for content in two languages.

**Needs from you.** Decision 12. Someone to review the Arabic and the legal lines. No keys.

### 3. Account lock-down kit

**What it is.**
- Quick exit.
- Sign out everywhere.
- An idle timeout.
- Password change.
- A login throttle.
- Optional TOTP.
- A freeze code that locks the account from any device.

**Need.**
- Devices are checked at checkpoints and on departure ([CPJ, 2023](https://cpj.org/2023/09/cpj-safety-advisory-covering-libyas-floods/); [US State Dept 2023 report](https://www.state.gov/wp-content/uploads/2024/02/528267_LIBYA-2023-HUMAN-RIGHTS-REPORT.pdf)).
- Documents were taken in the Benghazi detention ([Libya Security Monitor, 18 Sep 2024](https://libyasecuritymonitor.com/journalist-abducted-by-isa-in-the-east/)).
- Journalists report hacking attempts and fake accounts in their names ([Muwatin, 2026](https://muwatin.net/85639/violence-without-accountability-libyan-women-journalists/)).

Today a 14-day cookie with no idle timeout opens straight onto claims and comments. Login has no throttle. scrypt runs only for emails that exist (`backend/app/api/account.py` lines 62-65), so response time reveals who has an account.

**How it works.**
- **Quick exit.** A neutral control in the top bar, plus Esc pressed three times. It calls a new `POST /api/auth/logout-all`, clears browser storage and does `location.replace` to a site the user picks.
- **Sign out everywhere** on the Privacy page.
- **Idle timeout.** Uses a new `AuthSession.last_seen` column, with a "keep me signed in on this device" option.
- **Password change.** Needs the current password and ends all other sessions.
- **Login throttle.** Per-email backoff, plus a dummy scrypt check so unknown emails take the same time.
- **Optional TOTP.** Ported from `electoral-forensics/backend/app/totp.py`, which uses the standard library only, with recovery codes and an admin reset.
- **Freeze code.** Ends all sessions and disables the account until an admin re-enables it after checking with the user another way.

**Builds on.** scrypt hashing and hashed session tokens in `backend/app/auth.py`, the `_rate_limited` helper in `backend/app/api/account.py`, the admin disable that already deletes sessions, and `ADDED_COLUMNS`. The UI goes in `frontend/src/App.jsx`, `frontend/src/pages/Me.jsx` and `frontend/src/pages/Auth.jsx`.

**Required safeguards.**
- **last_seen.**
  - Store it only to the hour, and delete it with the session.
  - Never show it in the admin UI or the export.
  - Write it best-effort, so it never waits behind the hourly recompute.
- **TOTP secrets.** Encrypt them at rest with a key derived from an existing app secret. Fall back cleanly when no key is set, so the app still runs with zero keys.
- **Quick exit.** Use a neutral label or a plain X, and test it on mobile Chrome and Safari. The Privacy page states its limits: history, saved passwords and open tabs survive it.
- **Throttle design.** Throttle mainly per email. Keep any per-IP limit soft, because Libyan mobile networks share IPs. Put the dummy scrypt check (about 16 MB per hash) behind the throttle, given the 512 MB machine.
- **Admins.** Require TOTP for admins. Their accounts see every email, organisation and signup note.
- **Freeze code.**
  - It is optional, and storing it in a password manager is suggested.
  - The endpoint is rate-limited and gives no different response for a wrong code.
  - Only an admin can unfreeze.

**Effort.** About 6.5 days, in two slices:
- Slice 1, about 3 days: quick exit, sign out everywhere, password change, throttle and timing fix, idle timeout, session purge.
- Slice 2, about 3.5 days: TOTP and the freeze code.

**Needs from you.** Decisions 5-7. No keys.

### 4. "Who sees my name": visibility controls and expiring claims

**What it is.** Each claim, vote note, comment and outlet-label proposal can be named, shown as "a team member", or visible to admins only. "Working on this" claims lapse after 30 days. Viewers see no names.

**Need.**
- Attacks on women journalists go after reputation and honour ([UNSMIL, 3 Jun 2025](https://unsmil.unmissions.org/en/news/they-target-our-reputation-online-attacks-force-libyan-journalists-to-self-censor)).
- A detained journalist was made to report on colleagues ([Al Jazeera, 3 May 2025](https://www.aljazeera.net/politics/2025/5/3/%d9%8a%d9%88%d9%85-%d8%ad%d8%b1%d9%8a%d8%a9-%d8%a7%d9%84%d8%b5%d8%ad%d8%a7%d9%81%d8%a9-%d9%83%d9%8a%d9%81-%d9%8a%d8%a8%d8%af%d9%88-%d9%88%d8%a7%d9%82%d8%b9)).

Today a claim on LGBTQ+ or morality policing in a named city shows the claimant to every approved account, viewers included, and it never expires.

**How it works.**
- **New columns.** `visibility` on `gap_claim`, `gap_vote`, `comment` and `outlet_category`, and `expires_at` on `gap_claim`, all via `ADDED_COLUMNS`.
- **Default setting.** Each user sets a default on the Privacy page.
- **Display name.** The Privacy page gets a display-name field (PATCH /api/me already accepts it). The signup label changes from "Your name" to "Name shown to your team (a pseudonym is fine)", in Arabic and English.
- **Outlet-label history.** Non-admins see the proposer as "a team member". Evidence, dates and confidence stay as published.

**Builds on.**
- Claim POST and display in `backend/app/api/gaps.py` (lines 289-305 and 360).
- `_json` in `backend/app/api/social.py`.
- `outlet_history` in `backend/app/api/outlets.py` (line 71).
- The `mine` flag already in the JSON.
- `nightly()`, for lapsing claims.
- The UI in `GapPanel.jsx`, `Comments.jsx`, `OutletPanel.jsx`, `Me.jsx`, `Auth.jsx` and `Timeline.jsx`.

**Required safeguards** (the harm review asked for changes here).
- **Sensitive themes.** Viewers see nothing about claims. Contributors see "someone on the team is working on this", a yes or no rather than a count, because in a small team a count can point to one person.
- **Expired claims.** Hard-delete expired "working" claims and remind the user 3 days before.
- **Vote labels.** Strip `pseudo_id` from `gap_vote` labels on sensitive themes once they are in a training snapshot.
- **Viewers.** Viewers never see names anywhere, including comment authors and key events.
- **Admins.** Admins keep authorship for moderation, and the UI says so. Outlet labels keep the approving admin on record.
- **Honesty about limits.** Tell users plainly that whoever runs or seizes the server can still see who did what.

**Effort.** About 4 days. The display-name field and new signup label take about 0.25 day and can ship at once. Partner requests are under Build next.

**Needs from you.** Decisions 8-11. No keys.

---

## Build next

These seven tools take about 29 days in total.

### 5. Confidential "please contact me" safety requests (replaces the Safety concern tag)

**What it is.** A minimal request to a safety contact the reporter chooses. It replaces the public "Safety concern" tag, which today reaches nobody.

**Need.**
- Women journalists handle abuse alone and are their own first responders ([The Chilling, Nov 2022](https://eprints.goldsmiths.ac.uk/32542/7/ICFJ%20Unesco_TheChilling_OnlineViolence.pdf)).
- In the Arab-region newsroom survey (not Libya), the most common reason for not reporting harassment was that no reporting mechanism existed (26%). Coworkers were the perpetrators in 34% of cases ([Women in News, 2025](https://sexualharassment.womeninnews.org/research/wp-content/themes/win-sh-dashboard-2025/pdfs/Arab_Region.pdf)).

**How it works.**
- **The request.** Category and urgency only. No free text by default and no attachments.
- **Routing.** It goes to a contact the reporter picks from admins flagged `is_safety_contact`. A report about a contact never reaches that contact.
- **Notification.** A badge count in the admin nav. Optionally, a contentless email, but only if you set SMTP.
- **Her own view.** The author sees her requests at /safety/mine.

**Builds on.**
- The Feedback model (`backend/app/models.py` line 363).
- `/feedback/mine` and `/admin/feedback` in `backend/app/api/social.py` and `backend/app/api/admin.py`.
- The admin badge pattern in `frontend/src/App.jsx`.

**Required safeguards** (the harm review rated this high harm and asked for changes).
- **First line on the form:** "If this is urgent, contact SMEX or Access Now now; Desert Watch may not see this for days." State a realistic response window.
- **Contacts.** At least two safety contacts, each with TOTP required.
- **Storage.**
  - Purge requests 7 days after closure, with secure_delete.
  - Never log them.
  - Include them in the author's own export.
- **Protocol.** A short written protocol for contacts: do not contact her family or employer without consent, and refer to SMEX, Access Now or Media Defence.
- **Mass reporting.** Leave out the "ask colleagues to mass-report posts" option (see Not recommended).

**Effort.** About 3.5 days.

**Needs from you.** Decisions 13 and 18.

### 6. Attacks on journalists and women in public life as a tracked topic

**What it is.**
- Two new themes: `press_freedom`, and a strict gender theme for attacks on women journalists, activists and candidates.
- The keyless Libya Crimes Watch feeds as a need signal.
- A documented-incident tally that records roles, never names.

**Need.**
- At least 11 journalists were arrested in 2024-2025 ([Libya Security Monitor, 2 Nov 2025](https://libyasecuritymonitor.com/?p=9064)).
- Counts of violations are fragmented and not broken down by gender ([WJWC, 29 Oct 2024](https://www.wjwc.org/reports/press-freedom-in-libya-at-risk-of-disappearing-report); [LOFIM via Libya-Analysis, 11 May 2022](https://www.libya-analysis.com/blogs/lofim-report-media-violations-in-libya-may-2021-may-2022)).
- A woman TV journalist faced an online campaign after criticising the morality announcement on air ([CIHRS, 21 Nov 2024](https://cihrs.org/libya-new-morality-measures-will-impose-authoritarian-hegemony-over-society/?lang=en)).

Today the app catches these stories only when صحفية happens to sit near a violence word.

**How it works.**
- **Themes.** Add them to `config/themes.yaml` with co-occurrence and mask lists, for example masking مؤتمر صحفي and بيان صحفي. Check precision in `POST /api/themes/preview` first.
- **LCW feeds.** Add [LCW English](https://lcw.ngo/en/feed/) and [LCW Arabic](https://lcw.ngo/feed/) to `official_feeds` in `config/countries/libya.yaml` as `kind: report`, about 8 GETs a day.
- **Incident fields.** `KeyEvent` gains incident type, macro region (west, east, south, abroad or national) and the victim's sex only as the source states it (female, male or not stated). There is no name field.
- **Review.** New items go to the existing `gender_candidate` review lane.

**Builds on.**
- `backend/app/collectors/official.py`, `extra_alerts` and `backend/app/collectors/galerts.py`.
- `hydrate_items` in `backend/app/api/common.py`, for masking.
- `KeyEvent` and `/api/key-events`.
- `frontend/src/pages/Timeline.jsx`.
- `backend/app/api/labelling.py`.
- `backend/app/ml/train.py` line 150, so `press_freedom` stays rule-decided.

**Required safeguards** (the harm review asked for changes here).
- **LCW items.**
  - Store the feed's shortlink (`?p=NNNN`), never the URL slug, which can carry a victim's name.
  - Keep the matched terms, then drop the title and snippet. Retag then cannot revisit these items, but the stored terms allow hand checks.
- **Masking.** For other items in the gender attack theme, mask headlines server-side in `hydrate_items`. GapPanel prints need-signal titles directly (line 134). Show outlet, date and link only.
- **Incidents.** An incident counts only with a source from an allowlist of monitors (LCW, LCFP, Libya Security Monitor, RSF, CPJ, UN bodies, HRW, Amnesty, ICJ) and after admin approval.
- **Who sees what.**
  - Viewers see aggregates only, with cells under 3 suppressed.
  - Incident rows are for journalist and admin roles only.
  - Keep it out of social posts and the Haiku input.
- **Logging.** Mark both themes sensitive, so the quiet logging from tool 1 applies.
- **Labels and precision.** Label every tally "documented by the named monitors, not a count of all incidents". Check about 100 items for precision before showing scores.

**Effort.** About 6 days: themes and feed about 3, incident tally about 3.

**Cost.** Two more themes add about 15% to `cell_week` rows. Run the one-off retag off-peak. Volumes are tiny (20 of 143,229 local items have a journalist word and an attack word in the title), so expect "too few to judge" for months.

**Needs from you.** Decisions 14 and 15. An admin pastes back the Google Alerts RSS URLs. No keys.

### 7. Gender coverage profile: a pooled gender gap plus who covers gender

**What it is.**
- One pooled "gender (all)" cell, scored with the same lenses, so the group can be judged when single themes cannot.
- Monthly shares of gender coverage by outlet scope, type and language, with Wilson intervals.
- Gender key events overlaid on the trend.

**Need.** Women journalists self-censor on gender topics ([Hounna, 2026](https://hounna.net/%D8%B5%D8%AD%D9%81%D9%8A%D8%A7%D8%AA-%D9%84%D9%8A%D8%A8%D9%8A%D8%A7-%D8%AA%D8%AD%D8%AA-%D8%A7%D9%84%D8%B6%D8%BA%D8%B7-%D8%AA%D9%87%D8%AF%D9%8A%D8%AF-%D8%B1%D9%82%D9%85%D9%8A-%D9%88%D9%85%D9%8A%D8%AF/); [UNSMIL, 3 Jun 2025](https://unsmil.unmissions.org/en/news/they-target-our-reputation-online-attacks-force-libyan-journalists-to-self-censor)). At about 10 gender articles a week nationally, most gender cells are "too few expected to judge".

**Builds on.**
- `compute`, `_outlet_dims` and `NOT_FOR_TRENDS` in `backend/app/scoring.py`. The pooled cell is an inactive Theme row with a virtual flag, so the roughly 44 `Theme.active` filters keep it out of collectors, retag and training automatically.
- `CellWeek.breakdown`, `KeyEvent`, the group filter in `frontend/src/components/Filters.jsx`, and `frontend/src/pages/Trends.jsx`.
- A new `/api/gender/profile`, cached daily.

**Required safeguards.**
- **Logging.** Treat the profile route as sensitive under quiet logging.
- **Public footprint.** Keep the profile team-only and out of social posts. Public Arabic labels use قضايا المرأة, not جندر: Dar al-Ifta banned the term "gender" in government documents in October 2023 ([Amnesty, Apr 2024](https://www.amnesty.org/en/wp-content/uploads/2024/04/MDE1978582024ENGLISH.pdf)).
- **Honest slices.**
  - Show the per-theme cells, an explicit "unlabelled outlets" slice (only 41 type labels exist locally) and the Facebook blind spot.
  - Show n on every bar.
  - Present the self-censorship note as a cited hypothesis.
- **Virtual theme.** Exclude it from classify, retag, train and sync-themes, with a test.

**Effort.** About 6.5 days. It adds about 8% to `cell_week` rows.

**Needs from you.** Decision 22.

### 8. Gender evidence-quality strip and a targeted recall sample

**What it is.**
- A weekly sample of about 40 articles for review, drawn from three groups:
  - 20 with women-words but no gender theme.
  - 10 at random.
  - 10 with crime words and no gender word.
- Precision and weighted recall per gender theme, shown as one line on each gender gap.

**Need.** Recall of the gender word lists has never been measured. The 16 Oct review found 1 gender item in 160 random articles. Killings reported as جريمة قتل with no gender word are missed. The UN Women Libya study shows how much abuse escapes simple keyword detection ([UN Women, Jun 2023](https://arabstates.unwomen.org/sites/default/files/2023-06/BigDataAnalytics_OVAW_Libya_Jun2023_single-page.pdf)).

**Builds on.**
- `review_queue` and `_WOMEN_RE` in `backend/app/api/labelling.py`.
- `backend/app/ml/labels.py`.
- The 100-label gate in `backend/app/ml/train.py`.
- A new `recall_draw` table that records stratum and weight.
- Progress bars in `frontend/src/pages/Contribute.jsx` and `frontend/src/pages/Admin.jsx`.

**Required safeguards.**
- Store labels on sensitive themes without `pseudo_id`, or with a per-snapshot id that is discarded afterwards.
- Make the crime stratum opt-in, with a content warning and a cap of 10 a visit.
- Double-label 10% of items.
- Use plain-language intervals, and show "not yet measured" until n is adequate.

**Effort.** About 4.5 days. About 400 human labels are needed, which may take months, since the local copy has 1 explicit label.

**Needs from you.** Decision 3.

### 9. Pitch pack: an evidence brief for one gap

**What it is.** A one- to two-page brief built in the browser from data the gap panel already receives. Output is copy-as-text or print.

**Need.** Freelancers without contacts lose out ([The Chilling, 2022](https://eprints.goldsmiths.ac.uk/32542/7/ICFJ%20Unesco_TheChilling_OnlineViolence.pdf)). Journalists lack job security, and critics lose work ([RSF, 2026](https://rsf.org/en/country/libya); [Hounna, 2026](https://hounna.net/%D8%B5%D8%AD%D9%81%D9%8A%D8%A7%D8%AA-%D9%84%D9%8A%D8%A8%D9%8A%D8%A7-%D8%AA%D8%AD%D8%AA-%D8%A7%D9%84%D8%B6%D8%BA%D8%B7-%D8%AA%D9%87%D8%AF%D9%8A%D8%AF-%D8%B1%D9%82%D9%85%D9%8A-%D9%88%D9%85%D9%8A%D8%AF/)).

**Builds on.**
- `gap_detail`, `/api/timeline` and `/api/official` in `backend/app/api/gaps.py`.
- The "times less coverage than expected" calculation in `digest.py` `build_facts`.
- `/outlets/blind-spots`.
- The caveats in `how_the_numbers_work.md`.
- A new `frontend/src/components/PitchPack.jsx`, opened from `GapPanel.jsx` and `Contribute.jsx`.

**Required safeguards.**
- **Document traces.**
  - Add print CSS with `@page { margin: 0 }` to suppress browser headers and footers.
  - Put no app name or URL in the content, suggest a neutral filename, and prefer copy-as-text.
- **Honest numbers.** Always print confidence and "insufficient" labels, and never state a multiple for insufficient cells.
- **Outlets.** Name outlets only by group. Omit the Facebook register list.
- **Sensitive themes.** Articles appear as outlet, date and link only.
- **Team judgement.** Show it as counts only. `gap_detail` already sends voters' names to the browser, so the pack must not use them.
- **Logging.** Log pack generation as an event type only.

**Effort.** About 3.5 days. No keys.

### 10. National "heightened attention this week" indicator on sensitive themes

**What it is.** A factual line on a sensitive theme's gap panel, for example "Coverage and Wikipedia reading are 3x their usual level this week". It triggers on a sourced key event in the last 14 days, or on a ratio to the 8-week median above a minimum count. Election phases are added as key events.

**Need.** Women who criticised the November 2024 morality announcement faced online campaigns and death threats ([CIHRS, 21 Nov 2024](https://cihrs.org/libya-new-morality-measures-will-impose-authoritarian-hegemony-over-society/?lang=en)). Attacks on women candidates were reported higher around elections ([Asharq Al-Awsat, 10 Dec 2025](https://aawsat.com/node/5218082)). The HNEC figures behind that report were not seen.

**Builds on.** `KeyEvent`, `/api/timeline`, the audience-lens pageview items, `GapPanel.jsx`, `Overview.jsx` and `digest.py` `build_facts` (counts only).

**Required safeguards** (the harm review asked for changes here).
- **Framing.** Present it as an attention measure, never as a predicted risk.
- **Every sensitive theme carries:** "Absence of this indicator does not mean lower risk."
- **Advice.** Keep "prepare before publishing" advice in the static notes (tool 2), not generated by the algorithm.
- **Gaps.** Never hide or down-rank a gap.
- **Scope.** National only, with minimum counts.
- **HNEC figure.** Cite it only as reported and marked unverified, or leave it out.

**Effort.** About 2.5 days. Build the key-event trigger first, since the ratio will rarely fire on current volumes. Adds about 30 input tokens a week to the digest.

### 11. Co-reporting requests on claims

**What it is.** A claimant can mark a claim "open to a partner". Another contributor can then send "I could help". If she accepts, they move to a channel outside the app. There is no in-app chat.

**Need.**
- Exiled reporters are targeted remotely and find returning risky ([Hounna, 2026](https://hounna.net/%D8%B5%D8%AD%D9%81%D9%8A%D8%A7%D8%AA-%D9%84%D9%8A%D8%A8%D9%8A%D8%A7-%D8%AA%D8%AD%D8%AA-%D8%A7%D9%84%D8%B6%D8%BA%D8%B7-%D8%AA%D9%87%D8%AF%D9%8A%D8%AF-%D8%B1%D9%82%D9%85%D9%8A-%D9%88%D9%85%D9%8A%D8%AF/)).
- CPJ advises not working alone ([CPJ, 2023](https://cpj.org/2023/09/cpj-safety-advisory-covering-libyas-floods/)).

**Builds on.** `GapClaim`, the author-only `/feedback/mine` pattern, and `frontend/src/pages/Me.jsx`. A new `partner_request` table.

**Required safeguards.**
- **Limits.** Contributors only, 3 requests a day, and none on a cell the requester has not opened.
- **Notes.** No free text by default. An optional capped note carries a warning against locations and source names.
- **Deletion.** Hard-delete on decline or after 14 days.
- **Admins.** Admins cannot see the request graph.

**Effort.** About 2.5 days.

---

## Later or with partners

These seven tools take about 25 days in total.

### 12. Gender evidence pack for editors and advocates

**What it is.** Charts with caveats burned in, a CSV of the aggregates and a bilingual method note, drawn from tools 6, 7 and 13. It needs tool 7, and ideally tool 8's recall figure, before exports leave the app. The digest change already ships in tool 1.

**Need.** Counts are fragmented ([WJWC, 2024](https://www.wjwc.org/reports/press-freedom-in-libya-at-risk-of-disappearing-report)), and international complaints are slow ([CIVICUS Monitor, 30 Aug 2024](https://monitor.civicus.org/explore/online-violence-against-women-intimidation-of-journalists-foster-climate-of-fear/)).

**Builds on.** `exportSvg` in `frontend/src/charts/util.js` and a new `/api/gender/evidence`.

**Required safeguards.**
- Same export rules as tool 9.
- Suppress cells under 5. LGBTQ+ is off by default.
- Stamp each pack with its date, method version and theme versions.
- Show third-party figures only in a separate "as published elsewhere" block, never on the same axis. For example, [GMMP 2025](https://whomakesthenews.org/) reports women are 26% of people in the news globally (monitored 6 May 2025). That is never a Libya baseline.

**Effort.** About 2.75 days.

### 13. Who is quoted: an anonymous 50:50-style count

**What it is.** An optional coding section on the article-rating form and Add-article: women, men and can't-tell counts of people quoted, coded from the article's own grammatical forms, never from names. It also records whether the main subject is a woman and a role for the women quoted. It uses the method of [BBC 50:50](https://www.bbc.co.uk/5050) and [GMMP](https://whomakesthenews.org/).

**Need.** There is no Libya data on women as sources. GMMP has no Libya report, and Libya is not in the Women in News surveys.

**Builds on.** A new `voice_code` table (ArticleAssessment's fields are NOT NULL), the "rate articles" queue in `backend/app/api/contribute.py`, `ItemPanel.jsx` and `AddArticle.jsx`.

**Required safeguards.**
- Never write coded values to the event log.
- On sensitive themes, drop `user_id` after aggregation.
- Suppress slices under 30 people.
- Show results by outlet group only, team-only.
- Show "can't tell" as its own bar.
- Never ask for or record the coder's gender.

**Effort.** About 4.5 days. It depends on contributors taking part; the local copy has zero assessments.

### 14. Private record of published work

**What it is.** A page visible only to its owner, listing her linked pieces with before-and-after coverage in the cell, worded "followed by", never "caused". Add-article and "Mark published" ask every time whether to link the item to her.

**Need.** Critics lose professional opportunities ([Hounna, 2026](https://hounna.net/%D8%B5%D8%AD%D9%81%D9%8A%D8%A7%D8%AA-%D9%84%D9%8A%D8%A8%D9%8A%D8%A7-%D8%AA%D8%AD%D8%AA-%D8%A7%D9%84%D8%B6%D8%BA%D8%B7-%D8%AA%D9%87%D8%AF%D9%8A%D8%AF-%D8%B1%D9%82%D9%85%D9%8A-%D9%88%D9%85%D9%8A%D8%AF/)). Journalists can be dismissed arbitrarily ([RSF, 2026](https://rsf.org/en/country/libya)).

**Builds on.** `Item.added_by`, `GapClaim.published_url`, `/api/coverage-history`, `ItemEngagement`, and `add_article_core` in `backend/app/api/items.py`.

**Required safeguards.**
- "Don't link" is the default on sensitive themes. It also leaves `GapClaim.published_url` unlinked, writes no `pseudo_id` on labels, and skips `extra.confirmed_by_user`.
- The record sits behind a confirm click.
- The impact note carries no app name or URL.

**Effort.** About 3.5 days.

**Needs from you.** Decision 21.

### 15. Calendar of pegs and application deadlines

**What it is.** Seeded pegs (8 Mar, 3 May, 2 Nov, 25 Nov to 10 Dec) and funder deadlines with eligibility as published, shown on Timeline, in the gap panel and on the Digest page outside the generated text. Election risk windows sit in tool 10.

**Need.** Insecure jobs ([RSF, 2026](https://rsf.org/en/country/libya)). Some funds are closed to Libyans: the [IWMF emergency fund](https://www.iwmf.org/programs/emergency-fund/) cannot currently support journalists outside the US.

**Builds on.** `KeyEvent` (new kind, end_day and recurring columns, built once alongside tool 10), `/api/timeline`, and the events list in `libya.yaml`.

**Required safeguards.**
- Deadlines only from allowlisted funder domains or after admin approval, because phishing is a named threat.
- Do not log funder link clicks. Being recorded clicking foreign funding calls feeds the "foreign agent" line used against women rights defenders ([UN SR on HRDs, 24 Jun 2025](https://srdefenders.org/?p=10366)).
- Anniversaries only for events about public officials or institutions.

**Effort.** About 3.5 days.

### 16. Source desk: institutions with a gender mandate

**What it is.** A config list of institutions, never people, with themes, a link to the institution's own page, languages and a "last verified" date. Their public statements come in as links. It also links the [Who Is She](https://whoisshe.lau.edu.lb/) directory as a regional model. No Libyan directory of women experts was found.

**Need.** Safe access to women as sources ([Muwatin, 2026](https://muwatin.net/85639/violence-without-accountability-libyan-women-journalists/)).

**Builds on.** `official_feeds`, `backend/app/collectors/official.py`, `gnews_social.py`, Suggestion kind `source`, and the contested-label fields for which authority a state body belongs to.

**Required safeguards.**
- NGOs are listed only with their consent. Civic space rules make a list of rights groups risky for them ([HRW, 27 Jan 2025](https://www.hrw.org/news/2025/01/27/libya-civic-space-crushed)).
- Each state body carries the note "asking this body tells <authority> about your story".
- Feeds come only from pages linked from the institution's verified website.
- Hide entries not re-verified in 6 months.
- Never add individuals.

**Effort.** About 4 days: about 2 for code, about 2 for verification.

**Needs from you.** Decision 17.

### 17. Outlet "women's affairs focus" dimension

**What it is.** A non-contested taxonomy dimension with the values "women's affairs focus (self-described)", "regular women's section", "general" and "unknown". It feeds a "where gender coverage comes from" slice on the profile.

**Need.** A monopolised, faction-funded sector ([RSF, 2026](https://rsf.org/en/country/libya)).

**Builds on.** `config/outlet_taxonomy.yaml`, `_outlet_dims` in `backend/app/scoring.py`, the outlet queue in `backend/app/api/contribute.py`, and `OutletPanel.jsx`.

**Required safeguards** (the harm review asked for changes here).
- Use neutral values. The app never assigns "feminist" to an in-country Libyan outlet.
- Evidence comes only from the outlet's own about page.
- Team-only.
- Show "never covers gender" as a count by outlet group, never as a list of names.

**Effort.** About 2.5 days. Low priority.

### 18. Before-you-publish check for drafts and photos

**What it is.** A browser-only page. It highlights phone numbers, handles, small places and kinship patterns in a pasted draft, and strips EXIF metadata from a photo by re-encoding it.

**Need.**
- Defamation pages posted women's photos and screenshots from closed women-only groups ([UN Women, 2023](https://arabstates.unwomen.org/sites/default/files/2023-06/BigDataAnalytics_OVAW_Libya_Jun2023_single-page.pdf)).
- A forced confession exposed sources ([US State Dept 2024](https://www.state.gov/wp-content/uploads/2025/07/624521_LIBYA-2024-HUMAN-RIGHTS-REPORT.pdf)).

**Builds on.** `PlaceAlias`, and the normalisation rules in `backend/app/textnorm.py`, partly ported to JavaScript.

**Required safeguards** (the harm review asked for changes here).
- **Separate page.** Build a separate static page (`/check.html`) served with its own header CSP, `connect-src 'none'`. A per-route CSP inside the single-page app does not work.
- **No pass state.** Present it as a checklist of questions, and say at the top what it cannot detect.
- **No stored drafts.** Clear the field on pagehide. Warn that browser session restore and extensions can still capture text.
- **Photos.** Say the original photo and cloud backups still hold the location.

**Effort.** About 4 days. Value is modest: the gazetteer has only 149 aliases, and HEIC photos often will not decode. Start with the photo strip and the checklist.

**Needs from you.** Decision 20.

---

## Not recommended

- **Automatic text measure of women's voices** (counting feminine verbs and titles in fetched article pages). The harm review said drop it:
  - Every fetch advertises desert-watch.fly.dev to Libyan outlets.
  - Arabic feminine agreement with non-human plurals and institutions makes the measure unreliable.
  - It cannot be validated until tool 13 has 200 hand-coded articles.
  - Revisit only then.
- **"Ask colleagues to mass-report these posts".**
  - It posts abuse links, which may name her, to every account, including a hostile insider.
  - It builds a dossier of attacks on her.
  - Platforms can treat it as coordinated inauthentic behaviour.
- **Storing harassment evidence in Desert Watch, or running a Tella Web server.** It would put the most sensitive material on one small machine every admin can read. Point people to Tella or ProofMode on their own phones instead.
- **Gender inference from names, bylines or display names; byline counts.** This processes private names, works badly for Arabic names, and a byline count would mostly measure pseudonyms.
- **A named roster of Libyan women experts.** It conflicts with the rule on private individuals and would be a target list. Link Who Is She instead.
- **An outlet value "women-led", or an app-assigned "feminist" label.** For a small outlet it points at one editor, and it labels outlets that avoid the word for safety.
- **Framing the attention indicator as a risk forecast.** A quiet week would read as "safe", and the evidence is one case plus an unverified figure.
- **Linking these services:**
  - The IWMF emergency fund: closed to non-US applicants.
  - TrollBusters: its domain is now parked, so a link could lead to a page someone else controls.
  - Perspective API and Harassment Manager: shutting down 31 Dec 2026, and they need keys.
  - DocuSAFE: discontinued.
  - I Will Not Stay Silent: dormant since 2020; recheck before linking.
  - SheSource and Women Also Know Stuff: US-centred.
  - The government reporting mechanisms for violence against women: unverified.
  - Old dartcenter.org links: replaced by GCJT in July 2025.

---

## Safeguards to adopt regardless

1. **The behaviour log decides whether any anonymity is real.** Every new feature declares its logging: none, type only, or an aggregate counter. A server-side denylist in `record_events`, with tests, enforces it.
2. **One sensitive flag on themes drives every rule.** Covers LGBTQ+, morality and mobility, gender-based violence, detained migrant women, and the new attack and press-freedom themes. The rules: quiet logging, labels without `pseudo_id`, link-only headlines, exclusion from social posts and the Haiku input, and anonymous-by-default claims.
3. **Assume seizure.** Anything stored with a `user_id` or `pseudo_id` is readable from the volume, its snapshots, backups and local copies. Minimise what is stored, hard-delete, keep retention short and use secure_delete.
4. **Access log off.** Turn off uvicorn's access log.
5. **Admin and safety-contact TOTP.** Require it, with secrets encrypted at rest. One compromised admin defeats every visibility control.
6. **Viewers.** Viewers, the least-vetted role, see aggregates only. No names, no claims on sensitive themes, no safety content, no incident rows.
7. **Gender-neutral public footprint.** Social posts and indexed pages never show attack, incident, LGBTQ+ or "who covers gender" content. Public Arabic labels avoid جندر.
8. **No gender inference.** Count women only where the text states it. Never ask for or record a user's gender. Write this into the design notes as a rule.
9. **Link-only for victims.** On sensitive themes, show outlet, date and link. Prefer shortlinks over slugs.
10. **Every outbound safety, legal or funder link:**
    - `rel='noopener noreferrer'`.
    - An admin-curated allowlist.
    - A monthly check that compares content hash and title, so a hijacked page on the same domain is hidden until re-approved.
11. **Safety controls state their limits on screen.** External helplines come first, never the app.
12. **Exports leave the trust boundary.**
    - No print headers, no app name or URL, neutral filenames.
    - Small cells suppressed and caveats burned in.
    - Outlets named only by group.
13. **Team-added content the app shows with authority needs allowlisted sources and admin approval.** This covers incidents, key events, deadlines and outlet labels.
14. **Encryption-law note.** State Arts. 9 and 39 of Law 5/2022 as published and neutrally, above any tool mention.
15. **Psychosocial load.** Use content warnings, opt-in and caps wherever volunteers handle killings, gender-based violence or abuse material.
16. **User-Agent.** Consider a per-host policy: send the contact URL only where a host such as Wikimedia requires it.

---

## Decisions for you

1. Store implicit events on sensitive themes without a person (`anon`, no session, day-level time)? This partly reverses your 13 Oct choice.
2. Cut implicit-event retention from 365 to 90 days?
3. Clear `pseudo_id` from correction labels after 90 days, and from sensitive-theme labels once they are in a training snapshot?
4. Delete `/data/backups/pre_review_2026-10-16.db`? What is the minimum Fly snapshot retention you accept? Should local production copies be deleted after use?
5. Make TOTP mandatory for admins and safety contacts?
6. Idle timeout length: 12 hours, or another value?
7. Approve the `segno` package for TOTP QR codes, or ship text-secret entry only?
8. Make claims anonymous by default on sensitive themes only, or on all themes?
9. Should viewers see no names anywhere?
10. Should "working on this" claims lapse after 30 days unless renewed?
11. Which themes are sensitive? Proposed: LGBTQ+, morality and mobility, gender-based violence, detained migrant women, and the two new attack themes.
12. Keep the Help page behind login only, or also link a public copy from the login page?
13. Who are the two or more safety contacts, and what response time do you state (for example 48 hours on working days)?
14. Remove the 2025-11-21 event in `config/countries/libya.yaml` that names a blogger? If yes, remove it from config and delete the database row.
15. Let Libya Crimes Watch reports feed the humanitarian lens, or add a separate violations lens later?
16. Drop `recent_gender_headlines` from the Haiku digest input?
17. List NGOs in the source desk only with their consent?
18. Do you want to set SMTP for a contentless "new safety request" email? (You set the key. The app works without it.)
19. Adopt a per-host User-Agent policy that hides the app URL where not required?
20. If the before-you-publish check is built, approve a small EXIF-reading npm package, or a hand-written JPEG parser?
21. Accept that articles added as "don't link me" no longer teach the classifier?
22. Approve the wording of the self-censorship caveat on gender gaps?

---

## Sources

**Research** (organisation, date)

- UNSMIL, 3 Jun 2025: https://unsmil.unmissions.org/en/news/they-target-our-reputation-online-attacks-force-libyan-journalists-to-self-censor
- UNSMIL, 7 Aug 2025: https://unsmil.unmissions.org/en/node/56519
- OMCT and Libyan Anti-torture Network, Nov 2025: https://www.omct.org/site-resources/legacy/Reclaiming-Digital-Safe-Space-for-Women-In-Libya-2025.pdf
- Libya Security Monitor, 18 Sep 2024: https://libyasecuritymonitor.com/journalist-abducted-by-isa-in-the-east/
- Libya Security Monitor, 22 Oct 2024: https://libyasecuritymonitor.com/?p=8502
- Libya Security Monitor (reporting Libyan Crime Watch), 2 Nov 2025: https://libyasecuritymonitor.com/?p=9064
- Al Jazeera, 3 May 2025: https://www.aljazeera.net/politics/2025/5/3/%d9%8a%d9%88%d9%85-%d8%ad%d8%b1%d9%8a%d8%a9-%d8%a7%d9%84%d8%b5%d8%ad%d8%a7%d9%81%d8%a9-%d9%83%d9%8a%d9%81-%d9%8a%d8%a8%d8%af%d9%88-%d9%88%d8%a7%d9%82%d8%b9
- Committee to Protect Journalists, 20 Sep 2023: https://cpj.org/2023/09/cpj-safety-advisory-covering-libyas-floods/
- International Commission of Jurists, 13 Nov 2024: https://www.icj.org/libya-the-morality-police-must-not-be-reestablished/
- Hounna, 30 Mar 2026: https://hounna.net/%D8%B5%D8%AD%D9%81%D9%8A%D8%A7%D8%AA-%D9%84%D9%8A%D8%A8%D9%8A%D8%A7-%D8%AA%D8%AD%D8%AA-%D8%A7%D9%84%D8%B6%D8%BA%D8%B7-%D8%AA%D9%87%D8%AF%D9%8A%D8%AF-%D8%B1%D9%82%D9%85%D9%8A-%D9%88%D9%85%D9%8A%D8%AF/
- Lawyers for Justice in Libya, 9 Mar 2021: https://www.libyanjustice.org/news/urgent-action-needed-to-address-shocking-levels-of-online-violence-against-libyan-women
- Muwatin Media Network, 12 Feb 2026: https://muwatin.net/85639/violence-without-accountability-libyan-women-journalists/
- US Department of State, Libya 2024 Human Rights Report (published 2025): https://www.state.gov/wp-content/uploads/2025/07/624521_LIBYA-2024-HUMAN-RIGHTS-REPORT.pdf
- US Department of State, Libya 2023 Human Rights Report (published 2024): https://www.state.gov/wp-content/uploads/2024/02/528267_LIBYA-2023-HUMAN-RIGHTS-REPORT.pdf
- Freedom House, Freedom on the Net 2025: https://freedomhouse.org/country/libya/freedom-net/2025
- CIHRS, 21 Nov 2024: https://cihrs.org/libya-new-morality-measures-will-impose-authoritarian-hegemony-over-society/?lang=en
- ARTICLE 19, undated page (law in force 27 Sep 2022): https://www.article19.org/resources/libya-repeal-anti-cybercrime-law-now
- ARTICLE 19 and Libyan press-freedom groups, 2 May 2025: https://www.article19.org/ar/resources/libya-protect-press-freedom-support-media-reforms
- Amnesty International, Apr 2024: https://www.amnesty.org/en/wp-content/uploads/2024/04/MDE1978582024ENGLISH.pdf
- Women Journalists Without Chains, 29 Oct 2024: https://www.wjwc.org/reports/press-freedom-in-libya-at-risk-of-disappearing-report
- Libya-Analysis (summarising LOFIM), 11 May 2022: https://www.libya-analysis.com/blogs/lofim-report-media-violations-in-libya-may-2021-may-2022
- WAN-IFRA Women in News / BBC Media Action / City St George's, 2025: https://sexualharassment.womeninnews.org/research/wp-content/themes/win-sh-dashboard-2025/pdfs/Arab_Region.pdf
- UNESCO / ICFJ, The Chilling, Nov 2022: https://eprints.goldsmiths.ac.uk/32542/7/ICFJ%20Unesco_TheChilling_OnlineViolence.pdf
- UN Women, Jun 2023: https://arabstates.unwomen.org/sites/default/files/2023-06/BigDataAnalytics_OVAW_Libya_Jun2023_single-page.pdf
- Asharq Al-Awsat, 10 Dec 2025: https://aawsat.com/node/5218082
- Reporters Without Borders, 2026 index: https://rsf.org/en/country/libya
- Human Rights Watch, 27 Jan 2025: https://www.hrw.org/news/2025/01/27/libya-civic-space-crushed
- UN Special Rapporteur on Human Rights Defenders, 24 Jun 2025: https://srdefenders.org/?p=10366
- CIVICUS Monitor, 30 Aug 2024: https://monitor.civicus.org/explore/online-violence-against-women-intimidation-of-journalists-foster-climate-of-fear/

**Services, feeds and methods** (checked 2026-10-17 unless noted)

- Access Now Digital Security Helpline: https://www.accessnow.org/help/
- SMEX Digital Safety Helpdesk: https://smex.org/the-digital-safety-helpdesk-at-smex/
- IWMF/ICFJ Online Violence Response Hub, documenting guide (footer 2026): https://onlineviolenceresponsehub.org/documenting-an-attack
- PEN America / NDI, Online Harassment Field Manual, Arabic (about Nov 2022; blocks automated checks): https://onlineharassmentfieldmanual.pen.org/ar/
- Free Press Unlimited and Greenhost, Totem Project, Arabic catalogue: https://totem-project.org/ar/
- RaReNet / CiviCERT, Digital First Aid Kit, Arabic: https://digitalfirstaid.org/ar/
- Front Line Defenders, Security in a Box, Arabic (posts to May 2026): https://securityinabox.org/ar/
- Committee to Protect Journalists, resources (2026): https://cpj.org/resources/
- Reporters Without Borders, Assistance Desk (2025 figures): https://rsf.org/en/individual-support
- Free Press Unlimited, Reporters Respond: https://www.freepressunlimited.org/
- Journalists in Distress network: https://www.journalistsindistress.org/
- Media Defence, case support: https://www.mediadefence.org/apply-for-case-support/
- MiCT, T_LibyaLegal (phase 2, undated): https://mict-international.org/project-libyalegal
- Lawyers for Justice in Libya (statements to 13 Oct 2026): https://www.libyanjustice.org/
- Global Center for Journalism and Trauma (items Aug-Sep 2026): https://gcjt.org/
- Rory Peck Trust (application route not verified): https://rorypecktrust.org/
- WAN-IFRA Women in News, sexual harassment toolkit, Arabic: https://sexualharassment.womeninnews.org/ar/
- Horizontal, Tella: https://tella.app/
- Guardian Project, ProofMode (beta builds to Jul 2026): https://proofmode.org/
- IWMF emergency fund (closed to non-US applicants): https://www.iwmf.org/programs/emergency-fund/
- Libya Crimes Watch, English feed (updated 13 Oct 2026): https://lcw.ngo/en/feed/
- Libya Crimes Watch, Arabic feed (updated 14 Oct 2026): https://lcw.ngo/feed/
- WACC, Global Media Monitoring Project (2025 report, Dec 2025): https://whomakesthenews.org/
- BBC 50:50 Project: https://www.bbc.co.uk/5050
- Arab Institute for Women, Lebanese American University, Who Is She (footer 2025): https://whoisshe.lau.edu.lb/