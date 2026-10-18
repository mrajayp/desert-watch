// Arabic for the AI answers audit (components/AiAnswers.jsx, AiAuditAdmin.jsx, AiPanelTask.jsx and the
// line in OutletPanel.jsx). Keys are the exact English strings passed to t()/tn()/N_(). Glossary (docs/i18n.md):
// AI assistant = مساعد ذكاء اصطناعي, cited source = مصدر مُستشهد به, appeared in search results =
// ظهر في نتائج البحث, question set = مجموعة الأسئلة, weekly cap = الحد الأسبوعي للإنفاق.
// The three origins: developer services = خدمات المطورين (automatic), the team's log from the apps
// (journalist panel) = سجل الفريق, browser session = جلسة متصفح (supervised = بإشراف). An AI app people
// use on a phone = تطبيق ذكاء اصطناعي, or التطبيق. "Origin" is طريقة الجمع, never مصدر (that is a news source).
// Words the other screens already translate (Arabic, English, Scope, Status, Model, Week, Cancel, ok,
// error, partial, running, refused, Loading…, {from} to {to}) come from their files.
export default {
  // Outlets page card
  'What AI assistants cite': 'ما تستشهد به مساعدات الذكاء الاصطناعي',
  'Where the answers come from': 'من أين تأتي الإجابات',
  'Automatic: developer services': 'آليًا: خدمات المطورين',
  'Logged by the team: apps': 'سجل الفريق: التطبيقات',
  'Browser sessions: London': 'جلسات المتصفح: لندن',
  'Each week the same set of questions about {country} goes to AI assistants through their developer services, in Arabic and in English, with web search on. We count the sources they search and the sources they cite, per assistant.':
    'كل أسبوع تُطرح مجموعة الأسئلة نفسها عن {country} على مساعدات الذكاء الاصطناعي عبر خدماتها المتاحة للمطورين، بالعربية والإنجليزية، مع تشغيل البحث على الويب. ونحصي المصادر التي تظهر في نتائج بحثها والمصادر التي تستشهد بها، لكل مساعد على حدة.',
  'Each week team members ask the same questions about {country} in the AI apps they use on their own phones, in Arabic or in English, and log the source links each answer showed. We count those links per app.':
    'كل أسبوع يطرح أعضاء الفريق الأسئلة نفسها عن {country} في تطبيقات الذكاء الاصطناعي التي يستخدمونها على هواتفهم، بالعربية أو بالإنجليزية، ويسجلون روابط المصادر التي أظهرتها كل إجابة. ونحصي هذه الروابط لكل تطبيق على حدة.',
  'In supervised browser sessions an admin signs in to an AI assistant’s website and the same questions about {country} are asked while the admin watches. Only the source links are logged, per app.':
    'في جلسات المتصفح بإشراف، يسجّل أحد المشرفين الدخول إلى موقع مساعد ذكاء اصطناعي، وتُطرح الأسئلة نفسها عن {country} أثناء متابعة المشرف. ولا تُسجَّل إلا روابط المصادر، لكل تطبيق على حدة.',
  'App': 'التطبيق',
  'All assistants': 'كل المساعدات',
  'All apps': 'كل التطبيقات',
  'Assistant': 'المساعد',
  'Language of the question': 'لغة السؤال',
  'Both languages': 'اللغتان',
  'Window': 'الفترة',
  '{n} weeks': {
    zero: '{n} أسبوع', one: 'أسبوع واحد', two: 'أسبوعان', few: '{n} أسابيع', many: '{n} أسبوعًا', other: '{n} أسبوع',
  },
  'last run complete': 'اكتمل آخر تشغيل',
  'last run partly complete': 'اكتمل آخر تشغيل جزئيًا',
  'last run stopped at the weekly cost cap': 'توقف آخر تشغيل عند الحد الأسبوعي للإنفاق',
  'last run failed': 'فشل آخر تشغيل',
  'waiting for an API key': 'بانتظار مفتاح الواجهة البرمجية',
  'switched off': 'معطّل',
  'not run yet': 'لم يُشغَّل بعد',
  'running now': 'قيد التشغيل الآن',
  '{n} answers': {
    zero: 'لا إجابات', one: 'إجابة واحدة', two: 'إجابتان', few: '{n} إجابات', many: '{n} إجابة', other: '{n} إجابة',
  },
  'No answers logged by the team in this window yet. Team members log them on the Contribute page.':
    'لم يسجل الفريق إجابات في هذه الفترة بعد. يجري التسجيل من صفحة المساهمة.',
  'No browser sessions in this window yet.': 'لا جلسات متصفح في هذه الفترة بعد.',
  'No answers in this window yet. The audit runs once a week, early on Monday (UTC).':
    'لا إجابات في هذه الفترة بعد. يجري التدقيق مرة في الأسبوع، في الساعات الأولى من يوم الاثنين (بالتوقيت العالمي المنسق).',
  'The two bars in each block use different units: monitored coverage counts articles we collected, cited counts links in the answers. Compare the shares, not the sizes.':
    'يستخدم الشريطان في كل خانة وحدتين مختلفتين: التغطية المرصودة تحصي المقالات التي جمعناها، وما استشهد به المساعد يحصي الروابط في الإجابات. تُقارَن الحصص لا الأحجام.',
  '{n} answers without a search': {
    zero: 'لا إجابات من دون بحث', one: 'إجابة واحدة من دون بحث', two: 'إجابتان من دون بحث',
    few: '{n} إجابات من دون بحث', many: '{n} إجابة من دون بحث', other: '{n} إجابة من دون بحث',
  },
  '{n} answers showed no sources': {
    zero: 'لا إجابات من دون مصادر', one: 'إجابة واحدة لم تُظهر مصادر', two: 'إجابتان لم تُظهرا مصادر',
    few: '{n} إجابات لم تُظهر مصادر', many: '{n} إجابة لم تُظهر مصادر', other: '{n} إجابة لم تُظهر مصادر',
  },
  'Asked from London: {london}': 'طُرحت من لندن: {london}',
  'Asked from {country}: {ly}. From elsewhere: {other}.': 'طُرحت من {country}: {ly}. ومن مكان آخر: {other}.',
  'Sources searched per answer, median (range)': 'المصادر التي ظهرت في نتائج البحث لكل إجابة، الوسيط (المدى)',
  'Sources cited per answer, median (range)': 'المصادر المُستشهد بها لكل إجابة، الوسيط (المدى)',
  '{median} (range {min}–{max})': '{median} (المدى {min}–{max})',
  'Monitored coverage': 'التغطية المرصودة',
  'share of articles, by outlet scope': 'حصة المقالات حسب نطاق الوسيلة الإعلامية',
  'No monitored articles in this window.': 'لا مقالات مرصودة في هذه الفترة.',
  'Cited by the assistant': 'ما استشهد به المساعد',
  'Cited in the app': 'ما استشهد به التطبيق',
  'share of cited links, by outlet scope': 'حصة الروابط المُستشهد بها حسب نطاق الوسيلة الإعلامية',
  'No cited links in this window.': 'لا روابط مُستشهد بها في هذه الفترة.',
  'Not in the register': 'غير مدرجة في السجل',
  'Cited sources by language: Arabic {ar}%, English {en}%, other {other}%': 'المصادر المُستشهد بها حسب اللغة: العربية {ar}%، الإنجليزية {en}%، لغات أخرى {other}%',
  'Cited sources by language: none yet': 'المصادر المُستشهد بها حسب اللغة: لا شيء بعد',
  'Its own searches by language: Arabic {ar}%, English {en}%, other {other}%': 'لغة عمليات البحث التي أجراها المساعد: العربية {ar}%، الإنجليزية {en}%، لغات أخرى {other}%',
  'Its own searches by language: none yet': 'لغة عمليات البحث التي أجراها المساعد: لا شيء بعد',
  'Most cited outlets and domains': 'وسائل الإعلام والمواقع الأكثر استشهادًا بها',
  'One column per assistant. Choose one assistant to see how often each source also appeared in search results.':
    'عمود لكل مساعد. ولمعرفة عدد مرات ظهور كل مصدر في نتائج البحث أيضًا، يمكن اختيار مساعد واحد.',
  'One column per app. The apps show the links an answer used, so there are no search results to count.':
    'عمود لكل تطبيق. تُظهر التطبيقات الروابط التي استخدمتها الإجابة، فلا توجد نتائج بحث لإحصائها.',
  'Outlet or domain': 'الوسيلة الإعلامية أو الموقع',
  'Cited': 'مرات الاستشهاد',
  'Searched': 'في نتائج البحث',
  'Times it appeared in search results': 'عدد مرات الظهور في نتائج البحث',
  'Cited by {assistant}': 'استشهادات {assistant}',
  'Open {domain}': 'فتح {domain}',
  'not in the register': 'غير مدرج في السجل',
  'Libyan outlets never cited ({n})': 'وسائل إعلام ليبية لم يُستشهد بها ({n})',
  'Libyan outlets in the register with articles in the last 12 weeks that no answer in this window cited. With only {n} answers this is weak evidence about any single outlet.':
    'وسائل إعلام ليبية مدرجة في السجل لها مقالات في آخر 12 أسبوعًا، ولم تستشهد بها أي إجابة في هذه الفترة. وعدد الإجابات {n} فقط، لذلك فهذا دليل ضعيف بشأن أي وسيلة إعلامية بعينها.',
  'Every Libyan outlet with recent articles was cited at least once.': 'استُشهد بكل وسيلة إعلامية ليبية لها مقالات حديثة مرة واحدة على الأقل.',
  'Appeared in search results, never cited ({n})': 'ظهرت في نتائج البحث ولم يُستشهد بها ({n})',
  'Never appeared in search results ({n})': 'لم تظهر في نتائج البحث ({n})',
  'None.': 'لا شيء.',
  'Show all {n}': 'عرض الكل ({n})',
  'Show fewer': 'عرض عدد أقل',
  '{n} articles in 12 weeks': {
    zero: 'لا مقالات في 12 أسبوعًا', one: 'مقال واحد في 12 أسبوعًا', two: 'مقالان في 12 أسبوعًا',
    few: '{n} مقالات في 12 أسبوعًا', many: '{n} مقالًا في 12 أسبوعًا', other: '{n} مقال في 12 أسبوعًا',
  },
  'These answers come from the assistants’ developer services with web search on, not from the apps people use, which can answer differently. It is one fixed set of questions, so it says nothing about other topics. Each assistant is counted on its own and the counts are never added together, because the services define searched and cited differently. The team’s log from the apps and the browser sessions are shown apart and never mixed in. Nothing here is part of any gap score. The answers themselves are not kept, only which sources were searched and cited.':
    'تأتي هذه الإجابات من خدمات المساعدات المتاحة للمطورين مع تشغيل البحث على الويب، لا من التطبيقات التي يستخدمها الناس، وقد تجيب التطبيقات بطريقة مختلفة. وهي مجموعة أسئلة ثابتة واحدة، فلا تقول شيئًا عن مواضيع أخرى. ويُحصى كل مساعد على حدة، ولا تُجمع أرقام المساعدات أبدًا، لأن الخدمات تقصد أشياء مختلفة بنتائج البحث وبالاستشهاد. أما سجل الفريق من التطبيقات وجلسات المتصفح فيُعرضان منفصلين ولا يُخلطان بهذه الأرقام أبدًا. ولا يدخل شيء من هذا في أي درجة فجوة. ولا تُحفظ الإجابات نفسها، بل تُحفظ فقط المصادر التي ظهرت في نتائج البحث والمصادر المُستشهد بها.',
  'These links come from a small, uneven sample: the team’s own phones and accounts, the apps each person uses, and whichever questions they had time to ask. The apps tailor answers to the account, the place and earlier chats, so the same question can get other sources for someone else. Each app is counted on its own, and nothing here is added to the automatic audit or the browser sessions. Nothing here is part of any gap score. The answers themselves are not kept, only the source links, and no one’s name is shown.':
    'تأتي هذه الروابط من عينة صغيرة وغير متوازنة: هواتف أعضاء الفريق وحساباتهم، والتطبيقات التي يستخدمها كل منهم، والأسئلة التي اتسع وقتهم لطرحها. وتكيّف التطبيقات إجاباتها حسب الحساب والمكان والمحادثات السابقة، فقد يحصل شخص آخر على مصادر أخرى للسؤال نفسه. ويُحصى كل تطبيق على حدة، ولا يُضاف شيء من هذا إلى التدقيق الآلي أو إلى جلسات المتصفح. ولا يدخل شيء من هذا في أي درجة فجوة. ولا تُحفظ الإجابات نفسها، بل روابط المصادر فقط، ولا يظهر اسم أي أحد.',
  'These questions were asked from London in a signed-in account. They show what the assistant answered there and then, not what people in {country} see, since the apps tailor answers to the place and the account. Each app is counted on its own, and nothing here is added to the automatic audit or the team’s log. Nothing here is part of any gap score. The answers themselves are not kept, only the source links.':
    'طُرحت هذه الأسئلة من لندن بحساب مسجَّل الدخول. وهي تبيّن ما أجاب به المساعد هناك في ذلك الوقت، لا ما يراه الناس في {country}، لأن التطبيقات تكيّف إجاباتها حسب المكان والحساب. ويُحصى كل تطبيق على حدة، ولا يُضاف شيء من هذا إلى التدقيق الآلي أو إلى سجل الفريق. ولا يدخل شيء من هذا في أي درجة فجوة. ولا تُحفظ الإجابات نفسها، بل روابط المصادر فقط.',

  // Outlet panel
  'Cited by AI assistants: {n} times in 4 weeks': {
    zero: 'لم تستشهد بها مساعدات الذكاء الاصطناعي في آخر 4 أسابيع',
    one: 'استشهدت بها مساعدات الذكاء الاصطناعي مرة واحدة في آخر 4 أسابيع',
    two: 'استشهدت بها مساعدات الذكاء الاصطناعي مرتين في آخر 4 أسابيع',
    few: 'استشهدت بها مساعدات الذكاء الاصطناعي {n} مرات في آخر 4 أسابيع',
    many: 'استشهدت بها مساعدات الذكاء الاصطناعي {n} مرة في آخر 4 أسابيع',
    other: 'استشهدت بها مساعدات الذكاء الاصطناعي {n} مرة في آخر 4 أسابيع',
  },

  // Admin card
  'AI answers audit': 'تدقيق إجابات الذكاء الاصطناعي',
  'Each week the same questions go to Claude, ChatGPT and Perplexity through their developer services, in Arabic and in English, with web search on. Team members can also log the links the AI apps on their phones showed, and an admin can log a supervised browser session. The three origins are listed and counted apart, and only the automatic runs cost money. The search queries, URLs and titles below are shown on this page only, because they can carry private names. Everyone else sees counts per outlet and domain, and only once the audit is opened to the team.':
    'كل أسبوع تُطرح الأسئلة نفسها على Claude وChatGPT وPerplexity عبر خدماتها المتاحة للمطورين، بالعربية والإنجليزية، مع تشغيل البحث على الويب. ويمكن لأعضاء الفريق أيضًا تسجيل الروابط التي أظهرتها تطبيقات الذكاء الاصطناعي على هواتفهم، ويمكن للمشرف تسجيل جلسة متصفح بإشراف. وتُعرض الطرق الثلاث وتُحصى كل منها على حدة، ولا يكلّف المال إلا التشغيل الآلي. ولا تظهر عمليات البحث والروابط والعناوين أدناه إلا في هذه الصفحة، لأنها قد تتضمن أسماء أفراد عاديين. أما الآخرون فيرون أعدادًا على مستوى الوسيلة الإعلامية والموقع، ولا يرونها إلا بعد إتاحة التدقيق للفريق.',
  'Origin': 'طريقة الجمع',
  'Assistant or app': 'المساعد أو التطبيق',
  'developer API': 'واجهة المطورين البرمجية',
  'team, apps': 'سجل الفريق، التطبيقات',
  'browser session': 'جلسة متصفح',
  'Not counted against the cap': 'لا يُحتسب ضمن الحد الأسبوعي للإنفاق',
  'Refresh': 'تحديث',
  'This week (from {week}): {spent} of the {cap} cap': 'هذا الأسبوع (منذ {week}): {spent} من الحد الأسبوعي للإنفاق البالغ {cap}',
  'Spent this week against the cap': 'الإنفاق هذا الأسبوع مقارنة بالحد الأسبوعي',
  'Year to date: {ytd}': 'منذ بداية السنة: {ytd}',
  '${amount}': '{amount} دولار',
  'Run again even if it already ran this week': 'إعادة التشغيل حتى لو سبق تشغيله هذا الأسبوع',
  'Plan this week’s run': 'تخطيط تشغيل هذا الأسبوع',
  'Planned answers: {n}. Estimated cost {cost}. Spent this week {spent}, weekly cap {cap}.':
    'عدد الإجابات المخطط لها: {n}. التكلفة المقدّرة {cost}. ما أُنفق هذا الأسبوع {spent}، والحد الأسبوعي للإنفاق {cap}.',
  'Only {fits} of the {n} planned answers fit under the cap. The run stops there and records the rest as over budget.':
    'لا يتسع الحد الأسبوعي للإنفاق إلا لعدد {fits} من الإجابات المخطط لها البالغ عددها {n}. يتوقف التشغيل عند ذلك، وتُسجَّل الإجابات المتبقية على أنها تجاوزت الميزانية.',
  'Skipped: {list}': 'تم تخطي: {list}',
  'already ran this week': 'سبق تشغيله هذا الأسبوع',
  'not an assistant this audit knows': 'مساعد لا يعرفه هذا التدقيق',
  'no questions in the country config': 'لا أسئلة في إعدادات البلد',
  '{n} over budget': 'تجاوزت الميزانية: {n}',
  'the wording has changed since': 'تغيّرت صياغة السؤال منذ ذلك الحين',
  'Run now': 'التشغيل الآن',
  'Run the AI answers audit now? Planned answers: {n}. Estimated cost {cost}. Spent this week: {spent} of the {cap} cap. The run stops before it would pass the cap.':
    'هل يُشغَّل تدقيق إجابات الذكاء الاصطناعي الآن؟ عدد الإجابات المخطط لها: {n}. التكلفة المقدّرة {cost}. ما أُنفق هذا الأسبوع: {spent} من الحد الأسبوعي للإنفاق البالغ {cap}. ويتوقف التشغيل قبل أن يتجاوز الحد.',
  'Started. Answers are asked one at a time and take a few minutes. Refresh to see them.':
    'بدأ التشغيل. تُطرح الأسئلة واحدًا تلو الآخر، ويستغرق ذلك بضع دقائق. ويمكن التحديث لرؤية الإجابات.',
  'Runs': 'عمليات التشغيل',
  'No runs yet. The audit runs every Monday at 04:20 UTC, or from the button above.':
    'لا عمليات تشغيل بعد. يجري التدقيق كل يوم اثنين في الساعة 04:20 بالتوقيت العالمي المنسق (UTC)، أو بالزر أعلاه.',
  'Answers': 'الإجابات',
  'Hide answers': 'إخفاء الإجابات',
  'Cost': 'التكلفة',
  'forced': 'مفروض',
  'awaiting key': 'بانتظار المفتاح',
  'over budget': 'تجاوز الميزانية',
  'answered without searching': 'أجاب من دون بحث',
  'rate limited': 'تجاوز حد الطلبات',
  'language unclear': 'لغة غير محددة',
  'matched by path': 'مطابقة بقسم الموقع',
  'matched by host': 'مطابقة بالموقع نفسه',
  'matched by parent domain': 'مطابقة بالموقع الأعلى',
  'matched social account': 'مطابقة بحساب على وسائل التواصل',
  'Location sent:': 'الموقع الجغرافي المُرسَل:',
  'up to {n} searches per answer': {
    zero: 'من دون بحث', one: 'عملية بحث واحدة كحد أقصى لكل إجابة', two: 'عمليتا بحث كحد أقصى لكل إجابة',
    few: '{n} عمليات بحث كحد أقصى لكل إجابة', many: '{n} عملية بحث كحد أقصى لكل إجابة', other: '{n} عملية بحث كحد أقصى لكل إجابة',
  },
  'server region {region}': 'منطقة الخادم {region}',
  'date line sent': 'أُرسل سطر التاريخ',
  'no date line': 'من دون سطر التاريخ',
  '{from} to {to} UTC': 'من {from} إلى {to} (UTC)',
  'No answers recorded for this run.': 'لم تُسجَّل إجابات لهذا التشغيل.',
  '{searched} searched, {cited} cited': '{searched} في نتائج البحث، {cited} مُستشهد بها',
  'Its own search queries': 'عمليات البحث التي أجراها المساعد',
  'Cited ({n})': 'مُستشهد بها ({n})',
  'Searched ({n})': 'في نتائج البحث ({n})',
  '{n} citations': {
    zero: 'لا استشهادات', one: 'استشهاد واحد', two: 'استشهادان', few: '{n} استشهادات', many: '{n} استشهادًا', other: '{n} استشهاد',
  },
  'Domains not in the register (12 weeks)': 'مواقع غير مدرجة في السجل (12 أسبوعًا)',
  'Domains in the answers, searched or cited, that match no outlet, for one origin at a time. They are candidates for the register: nothing is added on its own. Libyan .ly domains are marked.':
    'مواقع وردت في الإجابات، في نتائج البحث أو في الاستشهادات، ولا تطابق أي وسيلة إعلامية، لكل طريقة جمع على حدة. وهي مرشحة للإدراج في السجل، ولا يُضاف شيء منها تلقائيًا. وتُميَّز المواقع الليبية ذات اللاحقة .ly.',
  'Domain': 'الموقع',
  'Perplexity marks the links it used only when a question asks for numbered sources, and these questions never do. So its cited figures are often zero and say little about what it used.':
    'لا يحدد Perplexity الروابط التي استخدمها إلا حين يطلب السؤال مصادر مرقّمة، وهذه الأسئلة لا تطلب ذلك أبدًا. لذا كثيرًا ما تكون أرقام الاستشهاد لديه صفرًا، ولا تدل كثيرًا على ما استخدمه.',
  'no sources shown': 'لم تظهر مصادر',
  'from {country}': 'من {country}',
  'from elsewhere': 'من مكان آخر',
  'from London': 'من لندن',
  'A supervised browser session from London, in a signed-in account. Only the source links were logged. Not counted against the cap.':
    'جلسة متصفح بإشراف من لندن، بحساب مسجَّل الدخول. لم تُسجَّل إلا روابط المصادر. ولا تُحتسب ضمن الحد الأسبوعي للإنفاق.',
  'Logged by team members in the apps on their own phones. Only the source links were logged. Not counted against the cap.':
    'سجّلها أعضاء الفريق من التطبيقات على هواتفهم. لم تُسجَّل إلا روابط المصادر. ولا تُحتسب ضمن الحد الأسبوعي للإنفاق.',
  '{n} links, {matched} matched to an outlet': 'الروابط: {n}، المطابقة لوسيلة إعلامية: {matched}',
  'Logged in a supervised browser session': 'سُجّل في جلسة متصفح بإشراف',
  'Logged by a team member': 'سجّله أحد أعضاء الفريق',
  'Links ({n})': 'الروابط ({n})',
  'Delete entry': 'حذف الإدخال',
  'your entry': 'إدخالك',
  'no sources shown: {n}': 'لم تظهر مصادر: {n}',
  'Delete this entry? Its links are taken out of the audit.': 'هل يُحذف هذا الإدخال؟ تُزال روابطه من التدقيق.',

  // Contribute page task (AiPanelTask.jsx): the team's own log from the AI apps on their phones
  'Ask an AI assistant': 'سؤال مساعد ذكاء اصطناعي',
  'Many people now get news about {country} from AI apps. Ask one or more of this week’s questions in the AI app you use on your phone, and paste the source links the answer showed. Desert Watch matches them to the outlet register, so we can see which outlets these apps send people to. The automatic audit sees only the developer services, which can answer differently.':
    'يتلقى كثيرون اليوم أخبار {country} من تطبيقات الذكاء الاصطناعي. يمكن طرح سؤال أو أكثر من أسئلة هذا الأسبوع في تطبيق الذكاء الاصطناعي المستخدَم على الهاتف، ثم لصق روابط المصادر التي أظهرتها الإجابة. ويطابق Desert Watch هذه الروابط مع سجل وسائل الإعلام، فنعرف إلى أي وسائل إعلام توجّه هذه التطبيقات الناس. أما التدقيق الآلي فلا يرى إلا الخدمات المتاحة للمطورين، وقد تجيب بطريقة مختلفة.',
  'entries this week (limit {limit})': 'إدخالات هذا الأسبوع (الحد {limit})',
  'Ask in your own app, as you normally would. Paste only the source links, one per line. Do not paste the answer text or anything that names a private person. Your name is never shown with your entries.':
    'يُطرح السؤال في التطبيق الشخصي كما في الاستخدام المعتاد. تُلصق روابط المصادر فقط، رابط في كل سطر. لا يُلصق نص الإجابة ولا أي شيء يذكر اسم فرد عادي. ولا يظهر اسم صاحب الإدخال معه أبدًا.',
  'This week’s questions (from {week})': 'أسئلة هذا الأسبوع (منذ {week})',
  'Copy the question in Arabic': 'نسخ السؤال بالعربية',
  'Copy the question in English': 'نسخ السؤال بالإنجليزية',
  'Copied': 'نُسخ',
  'Copy failed. Select the text and copy it by hand.': 'تعذّر النسخ. يمكن تحديد النص ونسخه يدويًا.',
  'Your account is read-only, so you cannot log answers yet.': 'هذا الحساب للقراءة فقط، لذا لا يمكن تسجيل الإجابات بعد.',
  'How the answer was asked': 'طريقة طرح السؤال',
  'Team panel: an app on a phone': 'سجل الفريق: تطبيق على الهاتف',
  'Supervised browser session': 'جلسة متصفح بإشراف',
  'App…': 'التطبيق…',
  'Question': 'السؤال',
  'Question…': 'السؤال…',
  'Asked': 'طُرح السؤال',
  'Where it was asked from': 'مكان طرح السؤال',
  'A browser session is recorded as asked from London, in a signed-in account. Its results are shown apart from the team’s and from the automatic audit.':
    'تُسجَّل جلسة المتصفح على أنها من لندن، بحساب مسجَّل الدخول. وتُعرض نتائجها منفصلة عن سجل الفريق وعن التدقيق الآلي.',
  'Source links, one per line': 'روابط المصادر، رابط في كل سطر',
  'https://… (one link per line)': 'https://… (رابط في كل سطر)',
  'No sources shown': 'لم تظهر مصادر',
  'No web links found. Each link must start with http:// or https://.': 'لم يُعثر على روابط ويب. يجب أن يبدأ كل رابط بـ http:// أو https://.',
  '{n} links found': {
    zero: 'لم يُعثر على روابط', one: 'عُثر على رابط واحد', two: 'عُثر على رابطين',
    few: 'عُثر على {n} روابط', many: 'عُثر على {n} رابطًا', other: 'عُثر على {n} رابط',
  },
  'At most {max} links per entry.': 'الحد الأقصى {max} رابطًا لكل إدخال.',
  'Only the links are sent. The rest of the text is left out.': 'لا تُرسل إلا الروابط، ويُترك باقي النص.',
  'The weekly limit of {limit} entries is reached.': 'بلغت الإدخالات الحد الأسبوعي ({limit}).',
  'Save entry': 'حفظ الإدخال',
  'Saved, with no sources shown.': 'تم الحفظ: لم تظهر مصادر.',
  'Saved. Links: {links}. Matched to an outlet: {matched}. Not in the register: {unknown}.':
    'تم الحفظ. الروابط: {links}. المطابقة لوسيلة إعلامية: {matched}. غير المدرجة في السجل: {unknown}.',
  'Your entries this week': 'إدخالاتك هذا الأسبوع',
  'No entries yet this week.': 'لا إدخالات هذا الأسبوع بعد.',
  'Links: {links}, matched: {matched}': 'الروابط: {links}، المطابقة: {matched}',
  'Show the links': 'عرض الروابط',
}
