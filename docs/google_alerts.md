# Google Alerts to create

Create each alert at https://www.google.com/alerts → *Show options*, with these settings:

- **How often:** As-it-happens
- **Sources:** Automatic
- **Language:** Arabic for (AR) alerts, English for (EN) alerts
- **Region:** Any region
- **How many:** All results
- **Deliver to:** RSS feed

Then copy each alert's RSS feed URL (the RSS icon next to the alert) and paste lines of
`<key> <feed url>` into **Admin → Google Alerts**. Alerts only collect from the day they are created.

## Districts (tag results to the district)

| Key | Label | Query (paste exactly) |
|---|---|---|
| `district:al_wahat:ar` | Al Wahat (AR) | `("الواحات" OR "أجدابيا" OR "اجدابيا") ليبيا` |
| `district:al_wahat:en` | Al Wahat (EN) | `("Al Wahat" OR Ajdabiya OR Jalu) Libya` |
| `district:benghazi:ar` | Benghazi (AR) | `"بنغازي" ليبيا` |
| `district:benghazi:en` | Benghazi (EN) | `Benghazi Libya` |
| `district:butnan:ar` | Butnan (AR) | `("البطنان" OR "طبرق" OR "البردية") ليبيا` |
| `district:butnan:en` | Butnan (EN) | `(Butnan OR Tobruk OR Tubruq) Libya` |
| `district:derna:ar` | Derna (AR) | `"درنة" ليبيا` |
| `district:derna:en` | Derna (EN) | `(Derna OR Darnah) Libya` |
| `district:ghat:ar` | Ghat (AR) | `"غات" ليبيا` |
| `district:ghat:en` | Ghat (EN) | `Ghat Libya` |
| `district:jabal_al_akhdar:ar` | Jabal al Akhdar (AR) | `("الجبل الأخضر" OR "البيضاء" OR "شحات") ليبيا` |
| `district:jabal_al_akhdar:en` | Jabal al Akhdar (EN) | `("Jabal al Akhdar" OR Bayda OR Al-Bayda) Libya` |
| `district:jabal_al_gharbi:ar` | Jabal al Gharbi (AR) | `("الجبل الغربي" OR "غريان" OR "الزنتان") ليبيا` |
| `district:jabal_al_gharbi:en` | Jabal al Gharbi (EN) | `("Jabal al Gharbi" OR Gharyan OR Zintan) Libya` |
| `district:jafara:ar` | Jafara (AR) | `("الجفارة" OR "العزيزية" OR "قصر بن غشير") ليبيا` |
| `district:jafara:en` | Jafara (EN) | `(Jafara OR Aziziya OR Al-Aziziya) Libya` |
| `district:jufra:ar` | Jufra (AR) | `("الجفرة" OR "هون" OR "ودان") ليبيا` |
| `district:jufra:en` | Jufra (EN) | `(Jufra OR Hun OR Houn) Libya` |
| `district:kufra:ar` | Kufra (AR) | `"الكفرة" ليبيا` |
| `district:kufra:en` | Kufra (EN) | `(Kufra OR Al-Kufra) Libya` |
| `district:marj:ar` | Marj (AR) | `"المرج" ليبيا` |
| `district:marj:en` | Marj (EN) | `(Marj OR Al-Marj) Libya` |
| `district:misrata:ar` | Misrata (AR) | `("مصراتة" OR "بني وليد") ليبيا` |
| `district:misrata:en` | Misrata (EN) | `(Misrata OR Misurata OR "Bani Walid") Libya` |
| `district:murqub:ar` | Murqub (AR) | `("المرقب" OR "الخمس" OR "زليتن") ليبيا` |
| `district:murqub:en` | Murqub (EN) | `(Murqub OR Khoms OR Al-Khums) Libya` |
| `district:murzuq:ar` | Murzuq (AR) | `("مرزق" OR "القطرون") ليبيا` |
| `district:murzuq:en` | Murzuq (EN) | `(Murzuq OR Murzuk OR Qatrun) Libya` |
| `district:nalut:ar` | Nalut (AR) | `("نالوت" OR "غدامس" OR "وازن") ليبيا` |
| `district:nalut:en` | Nalut (EN) | `(Nalut OR Ghadames OR Wazzin) Libya` |
| `district:nuqat_al_khams:ar` | Nuqat al Khams (AR) | `("النقاط الخمس" OR "زوارة" OR "رأس اجدير") ليبيا` |
| `district:nuqat_al_khams:en` | Nuqat al Khams (EN) | `("Nuqat al Khams" OR Zuwara OR Zuwarah) Libya` |
| `district:sabha:ar` | Sabha (AR) | `"سبها" ليبيا` |
| `district:sabha:en` | Sabha (EN) | `(Sabha OR Sebha) Libya` |
| `district:sirte:ar` | Sirte (AR) | `("سرت" OR "راس لانوف" OR "بن جواد") ليبيا` |
| `district:sirte:en` | Sirte (EN) | `(Sirte OR Sirt OR "Ras Lanuf") Libya` |
| `district:tripoli:ar` | Tripoli (AR) | `("طرابلس" OR "تاجوراء" OR "جنزور") ليبيا` |
| `district:tripoli:en` | Tripoli (EN) | `(Tripoli OR Tajoura OR Janzour) Libya` |
| `district:wadi_al_hayaa:ar` | Wadi al Hayaa (AR) | `("وادي الحياة" OR "أوباري" OR "اوباري") ليبيا` |
| `district:wadi_al_hayaa:en` | Wadi al Hayaa (EN) | `("Wadi al Hayaa" OR Ubari OR Awbari) Libya` |
| `district:wadi_al_shatii:ar` | Wadi al Shatii (AR) | `("وادي الشاطئ" OR "براك" OR "براك الشاطئ") ليبيا` |
| `district:wadi_al_shatii:en` | Wadi al Shatii (EN) | `("Wadi al Shatii" OR Brak OR "Brak al-Shati") Libya` |
| `district:zawiya:ar` | Zawiya (AR) | `("الزاوية" OR "صبراتة" OR "صرمان") ليبيا` |
| `district:zawiya:en` | Zawiya (EN) | `(Zawiya OR Zawia OR Sabratha) Libya` |

## Themes (national)

| Key | Label | Query (paste exactly) |
|---|---|---|
| `theme:economy:ar` | Oil & economy (AR) 1/3 | `ليبيا ("النفط" OR "نفط" OR "حقل نفطي" OR "المؤسسة الوطنية للنفط" OR "مصرف ليبيا المركزي" OR "المصرف المركزي" OR "الدينار" OR "الميزانية")` |
| `theme:economy:ar:2` | Oil & economy (AR) 2/3 | `ليبيا ("المرتبات" OR "الرواتب" OR "الوقود" OR "المحروقات" OR "التضخم" OR "الصادرات" OR "مصفاة" OR "إنتاج النفط")` |
| `theme:economy:ar:3` | Oil & economy (AR) 3/3 | `ليبيا ("سعر الصرف" OR "السيولة" OR "الصرف الأجنبي")` |
| `theme:economy:en` | Oil & economy (EN) 1/3 | `Libya (oil OR crude OR oilfield OR "oil field" OR NOC OR "National Oil Corporation" OR "central bank" OR CBL)` |
| `theme:economy:en:2` | Oil & economy (EN) 2/3 | `Libya (dinar OR budget OR salaries OR fuel OR inflation OR exports OR refinery OR "oil output")` |
| `theme:economy:en:3` | Oil & economy (EN) 3/3 | `Libya ("oil production" OR "exchange rate" OR liquidity)` |
| `theme:gender_economic_health:ar` | Gender: women's economic & health rights (AR) 1/2 | `ليبيا ("المرأة العاملة" OR "النساء العاملات" OR "عمل المرأة" OR "تشغيل النساء" OR "رائدات الأعمال" OR "سيدات الأعمال" OR "التمكين الاقتصادي للمرأة" OR "إجازة الأمومة")` |
| `theme:gender_economic_health:ar:2` | Gender: women's economic & health rights (AR) 2/2 | `ليبيا ("صحة الأم" OR "وفيات الأمهات" OR "الصحة الإنجابية" OR "القابلات" OR "سرطان الثدي" OR "صحة المرأة" OR "الأرامل" OR "الأسر التي تعولها نساء")` |
| `theme:gender_economic_health:en` | Gender: women's economic & health rights (EN) 1/2 | `Libya ("women workers" OR "working women" OR "women's employment" OR "female unemployment" OR "maternity leave" OR "women entrepreneurs" OR businesswomen OR "women's economic empowerment")` |
| `theme:gender_economic_health:en:2` | Gender: women's economic & health rights (EN) 2/2 | `Libya ("maternal health" OR "maternal mortality" OR "reproductive health" OR midwives OR "breast cancer" OR "women's health" OR "female-headed households" OR widows)` |
| `theme:gender_legal_status:ar` | Gender: legal status, family & nationality law (AR) 1/3 | `ليبيا ("قانون الأحوال الشخصية" OR "الأحوال الشخصية" OR "الولاية على المرأة" OR "زواج القاصرات" OR "زواج الأطفال" OR "الزواج المبكر" OR "تعدد الزوجات" OR "الحضانة")` |
| `theme:gender_legal_status:ar:2` | Gender: legal status, family & nationality law (AR) 2/3 | `ليبيا ("النفقة" OR "أبناء الليبيات" OR "أبناء الليبيات المتزوجات من أجانب" OR "الليبيات المتزوجات من أجانب" OR "زواج الليبيات من أجانب" OR "قانون الجنسية" OR "منح الجنسية لأبناء" OR "سيداو")` |
| `theme:gender_legal_status:ar:3` | Gender: legal status, family & nationality law (AR) 3/3 | `ليبيا ("المساواة بين الجنسين" OR "ميراث المرأة" OR "المادة 424")` |
| `theme:gender_legal_status:en` | Gender: legal status, family & nationality law (EN) 1/2 | `Libya ("personal status law" OR "family law" OR "male guardianship" OR "child marriage" OR "underage marriage" OR "early marriage" OR polygamy OR "child custody")` |
| `theme:gender_legal_status:en:2` | Gender: legal status, family & nationality law (EN) 2/2 | `Libya ("marital rape" OR "children of Libyan mothers" OR "Libyan women married to foreigners" OR "nationality law" OR "citizenship for children" OR CEDAW OR "gender equality" OR "inheritance rights")` |
| `theme:gender_lgbtq:ar` | Gender: LGBTQ+ persecution (AR) 1/2 | `ليبيا ("المثلية الجنسية" OR "المثليين" OR "المثليون" OR "مثليي الجنس" OR "مجتمع الميم" OR "العابرين جنسياً" OR "التحول الجنسي" OR "الشذوذ الجنسي")` |
| `theme:gender_lgbtq:ar:2` | Gender: LGBTQ+ persecution (AR) 2/2 | `ليبيا ("الشواذ" OR "الترويج للمثلية" OR "الترويج للشذوذ" OR "علم المثليين" OR "الميول الجنسية" OR "الهوية الجندرية")` |
| `theme:gender_lgbtq:en` | Gender: LGBTQ+ persecution (EN) 1/2 | `Libya (LGBT OR LGBTQ OR LGBTI OR homosexuality OR homosexual OR same-sex OR transgender OR queer)` |
| `theme:gender_lgbtq:en:2` | Gender: LGBTQ+ persecution (EN) 2/2 | `Libya ("sexual orientation" OR "gender identity" OR "rainbow flag" OR "promoting homosexuality")` |
| `theme:gender_migrant_detained_women:ar` | Gender: migrant, trafficked & detained women (AR) 1/2 | `ليبيا ("المهاجرات" OR "النساء المهاجرات" OR "مهاجرات غير نظاميات" OR "اللاجئات" OR "المحتجزات" OR "سجن النساء" OR "السجينات" OR "الاستعباد الجنسي")` |
| `theme:gender_migrant_detained_women:ar:2` | Gender: migrant, trafficked & detained women (AR) 2/2 | `ليبيا ("الاستغلال الجنسي" OR "الاتجار بالنساء" OR "الإتجار بالنساء" OR "الإكراه على الدعارة" OR "شبكة دعارة" OR "اغتصاب مهاجرات" OR "استعباد جنسي" OR "عبودية جنسية")` |
| `theme:gender_migrant_detained_women:en` | Gender: migrant, trafficked & detained women (EN) 1/2 | `Libya ("migrant women" OR "female migrants" OR "refugee women" OR "women detainees" OR "female detainees" OR "women's prison" OR "sexual slavery" OR "sexual exploitation")` |
| `theme:gender_migrant_detained_women:en:2` | Gender: migrant, trafficked & detained women (EN) 2/2 | `Libya ("trafficking of women" OR "sex trafficking" OR "forced prostitution" OR "rape in detention" OR "pregnant migrants" OR "sex slaves" OR "sex slavery")` |
| `theme:gender_mobility_morality:ar` | Gender: mobility, dress & 'morality' policing (AR) 1/3 | `ليبيا ("بدون محرم" OR "دون محرم" OR "سفر المرأة" OR "سفر النساء" OR "إذن ولي الأمر" OR "موافقة ولي الأمر" OR "استمارة سفر النساء" OR "فرض الحجاب")` |
| `theme:gender_mobility_morality:ar:2` | Gender: mobility, dress & 'morality' policing (AR) 2/3 | `ليبيا ("الحجاب الإلزامي" OR "إلزام النساء بالحجاب" OR "شرطة الآداب" OR "حماية الآداب العامة" OR "الشرطة النسائية" OR "منع الاختلاط" OR "الاختلاط" OR "اللباس المحتشم")` |
| `theme:gender_mobility_morality:ar:3` | Gender: mobility, dress & 'morality' policing (AR) 3/3 | `ليبيا "حماية الفضيلة"` |
| `theme:gender_mobility_morality:en` | Gender: mobility, dress & 'morality' policing (EN) 1/2 | `Libya (mahram OR "male guardian" OR "women travelling alone" OR "women traveling alone" OR "travel restrictions on women" OR "travel form for women" OR "compulsory hijab" OR "mandatory hijab")` |
| `theme:gender_mobility_morality:en:2` | Gender: mobility, dress & 'morality' policing (EN) 2/2 | `Libya ("morality police" OR "Public Morality Protection" OR "gender mixing" OR "guarding virtue")` |
| `theme:gender_political_participation:ar` | Gender: women's political & public participation (AR) 1/4 | `ليبيا ("المشاركة السياسية للمرأة" OR "مشاركة المرأة" OR "تمثيل المرأة" OR "الكوتا النسائية" OR "حصة المرأة" OR "المقاعد المخصصة للمرأة" OR "المترشحات" OR "المرشحات")` |
| `theme:gender_political_participation:ar:2` | Gender: women's political & public participation (AR) 2/4 | `ليبيا ("الناخبات" OR "النائبة" OR "عضوة مجلس النواب" OR "شؤون المرأة" OR "تمكين المرأة" OR "المدافعات عن حقوق الإنسان" OR "الناشطات" OR "المرأة والسلام والأمن")` |
| `theme:gender_political_participation:ar:3` | Gender: women's political & public participation (AR) 3/4 | `ليبيا ("القرار 1325" OR "سهام سرقيوة" OR "حنان البرعصي" OR "سلوى بوقعيقيص" OR "أول امرأة" OR "المنقوش" OR "نجلاء المنقوش" OR "ليلى بن خليفة")` |
| `theme:gender_political_participation:ar:4` | Gender: women's political & public participation (AR) 4/4 | `ليبيا ("مرشحة للرئاسة" OR "مرشحة رئاسية")` |
| `theme:gender_political_participation:en` | Gender: women's political & public participation (EN) 1/4 | `Libya ("women candidates" OR "female candidates" OR "women's quota" OR "gender quota" OR "seat reserved for women" OR "women's representation" OR "women's political participation" OR "women voters")` |
| `theme:gender_political_participation:en:2` | Gender: women's political & public participation (EN) 2/4 | `Libya ("women MPs" OR "female lawmaker" OR "woman minister" OR "women's affairs" OR "women human rights defenders" OR "women activists" OR "Women, Peace and Security" OR "Resolution 1325")` |
| `theme:gender_political_participation:en:3` | Gender: women's political & public participation (EN) 3/4 | `Libya ("women's empowerment" OR Sergiwa OR Barassi OR Bughaighis OR "first woman" OR Mangoush OR "Najla El Mangoush" OR "Leila Ben Khalifa")` |
| `theme:gender_political_participation:en:4` | Gender: women's political & public participation (EN) 4/4 | `Libya ("Ben Khalifa" OR "woman candidate" OR "female presidential candidate")` |
| `theme:gender_violence:ar` | Gender: violence against women & girls (AR) 1/3 | `ليبيا ("العنف ضد المرأة" OR "العنف ضد النساء" OR "العنف القائم على النوع الاجتماعي" OR "العنف الأسري" OR "العنف المنزلي" OR "تعنيف امرأة" OR "تعنيف زوجته" OR "قتل زوجته")` |
| `theme:gender_violence:ar:2` | Gender: violence against women & girls (AR) 2/3 | `ليبيا ("مقتل امرأة" OR "مقتل سيدة" OR "قتل النساء" OR "جرائم الشرف" OR "الاغتصاب" OR "التحرش الجنسي" OR "الابتزاز الإلكتروني" OR "ابتزاز فتاة")` |
| `theme:gender_violence:ar:3` | Gender: violence against women & girls (AR) 3/3 | `ليبيا ("العنف الرقمي" OR "قانون مناهضة العنف ضد المرأة" OR "قانون مكافحة العنف ضد المرأة" OR "اليوم الدولي للقضاء على العنف ضد المرأة")` |
| `theme:gender_violence:en` | Gender: violence against women & girls (EN) 1/3 | `Libya ("violence against women" OR "gender-based violence" OR GBV OR "domestic violence" OR femicide OR "killing of women" OR "woman killed" OR "honour killing")` |
| `theme:gender_violence:en:2` | Gender: violence against women & girls (EN) 2/3 | `Libya ("honor killing" OR "sexual violence" OR rape OR "sexual harassment" OR "online harassment" OR "cyber blackmail" OR sextortion OR doxxing)` |
| `theme:gender_violence:en:3` | Gender: violence against women & girls (EN) 3/3 | `Libya ("16 Days of Activism" OR "Elimination of Violence against Women" OR "law on violence against women" OR "Article 424")` |
| `theme:governance:ar` | Governance & elections (AR) 1/3 | `ليبيا ("الانتخابات" OR "انتخابات" OR "المفوضية الوطنية العليا للانتخابات" OR "مجلس النواب" OR "المجلس الأعلى للدولة" OR "حكومة الوحدة الوطنية" OR "المجلس الرئاسي" OR "المجلس البلدي")` |
| `theme:governance:ar:2` | Governance & elections (AR) 2/3 | `ليبيا ("الفساد" OR "ديوان المحاسبة" OR "الدستور" OR "البرلمان" OR "الحكومة" OR "وزير" OR "إضراب" OR "احتجاج")` |
| `theme:governance:ar:3` | Governance & elections (AR) 3/3 | `ليبيا ("احتجاجات" OR "الانتخابات البلدية" OR "المبعوثة الأممية" OR "البعثة الأممية")` |
| `theme:governance:en` | Governance & elections (EN) 1/3 | `Libya (election OR elections OR HNEC OR "House of Representatives" OR "High Council of State" OR "Government of National Unity" OR GNU OR "Presidential Council")` |
| `theme:governance:en:2` | Governance & elections (EN) 2/3 | `Libya ("municipal council" OR corruption OR "Audit Bureau" OR constitution OR parliament OR minister OR "general strike" OR "teachers strike")` |
| `theme:governance:en:3` | Governance & elections (EN) 3/3 | `Libya ("workers strike" OR protest OR protests OR "municipal elections")` |
| `theme:health:ar` | Health (AR) 1/3 | `ليبيا ("مستشفى" OR "المستشفيات" OR "وزارة الصحة" OR "الأدوية" OR "أدوية" OR "المستلزمات الطبية" OR "تفشي" OR "الكوليرا")` |
| `theme:health:ar:2` | Health (AR) 2/3 | `ليبيا ("التطعيم" OR "إضراب الأطباء" OR "مرضى الأورام" OR "طبي" OR "طبية" OR "الأطباء" OR "أطباء" OR "لقاح")` |
| `theme:health:ar:3` | Health (AR) 3/3 | `ليبيا ("لقاحات" OR "اللقاحات" OR "مرض" OR "وباء" OR "الإمداد الطبي" OR "الصيدلة")` |
| `theme:health:en` | Health (EN) 1/3 | `Libya (hospital OR hospitals OR "health ministry" OR medicines OR "medical supplies" OR "disease outbreak" OR "cholera outbreak" OR cholera)` |
| `theme:health:en:2` | Health (EN) 2/3 | `Libya (vaccination OR "doctors strike" OR "cancer patients" OR medical OR doctors OR nurses OR vaccine OR vaccines)` |
| `theme:health:en:3` | Health (EN) 3/3 | `Libya (disease OR epidemic OR pharmaceutical OR "medical staff")` |
| `theme:migration:ar` | Migration & detention (AR) 1/3 | `ليبيا ("مهاجر" OR "مهاجرا" OR "مهاجرون" OR "مهاجرين" OR "المهاجرين" OR "لاجئ" OR "لاجئين" OR "اللجوء")` |
| `theme:migration:ar:2` | Migration & detention (AR) 2/3 | `ليبيا ("مركز احتجاز" OR "مراكز الاحتجاز" OR "الاتجار بالبشر" OR "تهريب البشر" OR "خفر السواحل" OR "غرق قارب" OR "ترحيل" OR "قوارب")` |
| `theme:migration:ar:3` | Migration & detention (AR) 3/3 | `ليبيا ("قارب" OR "الهجرة غير الشرعية" OR "الهجرة غير النظامية" OR "غير النظامية" OR "إنقاذ")` |
| `theme:migration:en` | Migration & detention (EN) 1/3 | `Libya (migrant OR migrants OR migration OR IOM OR refugee OR refugees OR asylum OR "detention centre")` |
| `theme:migration:en:2` | Migration & detention (EN) 2/3 | `Libya ("detention center" OR "people smuggling" OR "human smuggling" OR "migrant smuggling" OR "human trafficking" OR "coast guard" OR shipwreck OR deportation)` |
| `theme:migration:en:3` | Migration & detention (EN) 3/3 | `Libya (boat OR boats OR departures OR rescued OR "missing at sea")` |
| `theme:security:ar` | Security & armed groups (AR) 1/4 | `ليبيا ("ميليشيا" OR "ميليشيات" OR "مليشيات" OR "مجموعات مسلحة" OR "جماعات مسلحة" OR "اشتباكات" OR "اشتباك" OR "وقف إطلاق النار")` |
| `theme:security:ar:2` | Security & armed groups (AR) 2/4 | `ليبيا ("غارة" OR "طائرة مسيرة" OR "المسيرات" OR "بمسيرة" OR "مسيرات" OR "مسلحين" OR "اختطاف" OR "اغتيال")` |
| `theme:security:ar:3` | Security & armed groups (AR) 3/4 | `ليبيا ("مقتل" OR "قتلى" OR "قتيل" OR "السجون" OR "اقتحام سجن" OR "سجن معيتيقة" OR "فرار" OR "خطف")` |
| `theme:security:ar:4` | Security & armed groups (AR) 4/4 | `ليبيا ("انفجار" OR "عبوة ناسفة" OR "مسلح" OR "قوة عسكرية" OR "الاستخبارات العسكرية")` |
| `theme:security:en` | Security & armed groups (EN) 1/3 | `Libya (militia OR militias OR "armed group" OR "armed groups" OR clashes OR fighting OR ceasefire OR airstrike)` |
| `theme:security:en:2` | Security & armed groups (EN) 2/3 | `Libya ("drone strike" OR gunmen OR kidnapping OR abducted OR assassination OR killed OR killing OR "prison break")` |
| `theme:security:en:3` | Security & armed groups (EN) 3/3 | `Libya (jailbreak OR "armed clashes" OR assassinated OR explosion OR bomb)` |
| `theme:services:ar` | Public services (water & power) (AR) 1/2 | `ليبيا ("انقطاع الكهرباء" OR "الكهرباء" OR "طرح الأحمال" OR "الشركة العامة للكهرباء" OR "إمدادات المياه" OR "المياه" OR "النهر الصناعي" OR "الصرف الصحي")` |
| `theme:services:ar:2` | Public services (water & power) (AR) 2/2 | `ليبيا ("تحلية المياه" OR "نقص الوقود" OR "الديزل" OR "البنزين" OR "طوابير" OR "شح المياه" OR "انقطاع المياه")` |
| `theme:services:en` | Public services (water & power) (EN) 1/2 | `Libya ("power cut" OR "power cuts" OR blackout OR electricity OR GECOL OR "water supply" OR "Great Man-Made River" OR "Man-Made River")` |
| `theme:services:en:2` | Public services (water & power) (EN) 2/2 | `Libya (sewage OR desalination OR "load shedding" OR "water shortage" OR "fuel shortage" OR diesel OR gasoline OR queues)` |

## Gap-targeted (south, minorities, recovery)

| Key | Label | Query (paste exactly) |
|---|---|---|
| `extra:amazigh:ar` | Amazigh (AR) | `(الأمازيغ OR الأمازيغية) ليبيا` |
| `extra:amazigh:en` | Amazigh (EN) | `(Amazigh OR Berber) Libya` |
| `extra:derna_recovery:ar` | Derna recovery (AR) | `درنة (الإعمار OR السيول OR السد)` |
| `extra:derna_recovery:en` | Derna recovery (EN) | `Derna (reconstruction OR flood OR dam)` |
| `extra:kufra_migration:ar` | Kufra migration (AR) | `الكفرة (مهاجرين OR السودانيين OR لاجئين)` |
| `extra:kufra_migration:en` | Kufra migration (EN) | `Kufra (migrants OR Sudanese OR refugees)` |
| `extra:south_services:ar` | Fezzan public services (AR) | `(فزان OR "الجنوب الليبي") (كهرباء OR وقود OR مستشفى OR مياه)` |
| `extra:south_services:en` | Fezzan public services (EN) | `(Fezzan OR "southern Libya") (electricity OR fuel OR hospital OR water)` |
| `extra:tebu_tuareg:ar` | Tebu & Tuareg communities (AR) | `(التبو OR الطوارق) ليبيا` |
| `extra:tebu_tuareg:en` | Tebu & Tuareg communities (EN) | `(Tebu OR Toubou OR Tuareg) Libya` |
