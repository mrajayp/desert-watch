// Arabic for the AI answers audit (components/AiAnswers.jsx, AiAuditAdmin.jsx and the line in
// OutletPanel.jsx). Keys are the exact English strings passed to t()/tn()/N_(). Glossary (docs/i18n.md):
// AI assistant = مساعد ذكاء اصطناعي, cited source = مصدر مُستشهد به, appeared in search results =
// ظهر في نتائج البحث, question set = مجموعة الأسئلة, weekly cap = الحد الأسبوعي للإنفاق.
// Words the other screens already translate (Arabic, English, Scope, Status, Model, Week, Cancel, ok,
// error, partial, running, refused, Loading…, {from} to {to}) come from their files.
export default {
  // Outlets page card
  'What AI assistants cite': 'ما تستشهد به مساعدات الذكاء الاصطناعي',
  'Each week Claude and ChatGPT get the same set of questions about {country}, in Arabic and in English, with web search on. We count the sources they search and the sources they cite, per assistant.':
    'كل أسبوع يتلقى Claude وChatGPT مجموعة الأسئلة نفسها عن {country}، بالعربية والإنجليزية، مع تشغيل البحث على الويب. ونحصي المصادر التي تظهر في نتائج بحثهما والمصادر التي يستشهدان بها، لكل مساعد على حدة.',
  'Assistant': 'المساعد',
  'Both': 'كلاهما',
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
  'No answers in this window yet. The audit runs once a week, early on Monday (UTC).':
    'لا إجابات في هذه الفترة بعد. يجري التدقيق مرة في الأسبوع، في الساعات الأولى من يوم الاثنين (بالتوقيت العالمي المنسق).',
  'The two bars in each block use different units: monitored coverage counts articles we collected, cited counts links in the answers. Compare the shares, not the sizes.':
    'يستخدم الشريطان في كل خانة وحدتين مختلفتين: التغطية المرصودة تحصي المقالات التي جمعناها، وما استشهد به المساعد يحصي الروابط في الإجابات. تُقارَن الحصص لا الأحجام.',
  '{n} answers without a search': {
    zero: 'لا إجابات من دون بحث', one: 'إجابة واحدة من دون بحث', two: 'إجابتان من دون بحث',
    few: '{n} إجابات من دون بحث', many: '{n} إجابة من دون بحث', other: '{n} إجابة من دون بحث',
  },
  'Sources searched per answer, median (range)': 'المصادر التي ظهرت في نتائج البحث لكل إجابة، الوسيط (المدى)',
  'Sources cited per answer, median (range)': 'المصادر المُستشهد بها لكل إجابة، الوسيط (المدى)',
  '{median} (range {min}–{max})': '{median} (المدى {min}–{max})',
  'Monitored coverage': 'التغطية المرصودة',
  'share of articles, by outlet scope': 'حصة المقالات حسب نطاق الوسيلة الإعلامية',
  'No monitored articles in this window.': 'لا مقالات مرصودة في هذه الفترة.',
  'Cited by the assistant': 'ما استشهد به المساعد',
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
  'These answers come from the assistants’ developer APIs with web search on, not from the apps people use, which can answer differently. It is one fixed set of questions, so it says nothing about other topics. Each assistant is counted on its own and the counts are never added together, because the two services define searched and cited differently. Nothing here is part of any gap score. The answers themselves are not kept, only which sources were searched and cited.':
    'تأتي هذه الإجابات من الواجهات البرمجية التي يتيحها المساعدان للمطورين مع تشغيل البحث على الويب، لا من التطبيقات التي يستخدمها الناس، وقد تجيب التطبيقات بطريقة مختلفة. وهي مجموعة أسئلة ثابتة واحدة، فلا تقول شيئًا عن مواضيع أخرى. ويُحصى كل مساعد على حدة، ولا تُجمع أرقام المساعدَين أبدًا، لأن الخدمتين تقصدان شيئًا مختلفًا بنتائج البحث وبالاستشهاد. ولا يدخل شيء من هذا في أي درجة فجوة. ولا تُحفظ الإجابات نفسها، بل تُحفظ فقط المصادر التي ظهرت في نتائج البحث والمصادر المُستشهد بها.',

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
  'Each week the same questions go to Claude and ChatGPT, in Arabic and in English, with web search on. The search queries, URLs and titles below are shown on this page only, because they can carry private names. Everyone else sees counts per outlet and domain, and only once the audit is opened to the team.':
    'كل أسبوع تُطرح الأسئلة نفسها على Claude وChatGPT، بالعربية والإنجليزية، مع تشغيل البحث على الويب. ولا تظهر عمليات البحث والروابط والعناوين أدناه إلا في هذه الصفحة، لأنها قد تتضمن أسماء أفراد عاديين. أما الآخرون فيرون أعدادًا على مستوى الوسيلة الإعلامية والموقع، ولا يرونها إلا بعد إتاحة التدقيق للفريق.',
  'Refresh': 'تحديث',
  'This week (from {week}): {spent} of the {cap} cap': 'هذا الأسبوع (منذ {week}): {spent} من الحد الأسبوعي للإنفاق البالغ {cap}',
  'Spent this week against the cap': 'الإنفاق هذا الأسبوع مقارنة بالحد الأسبوعي',
  'Year to date: {ytd}': 'منذ بداية السنة: {ytd}',
  '${amount}': '{amount} دولار',
  'Both assistants': 'المساعدان كلاهما',
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
  'Domains the assistants searched or cited that match no outlet. They are candidates for the register: nothing is added on its own. Libyan .ly domains are marked.':
    'مواقع ظهرت في نتائج بحث المساعدَين أو استشهدا بها، ولا تطابق أي وسيلة إعلامية. وهي مرشحة للإدراج في السجل، ولا يُضاف شيء منها تلقائيًا. وتُميَّز المواقع الليبية ذات اللاحقة .ly.',
  'Domain': 'الموقع',
}
