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
| `theme:economy:ar` | Oil & economy (AR) | `ليبيا ("النفط" OR "نفط" OR "حقل نفطي" OR "المؤسسة الوطنية للنفط" OR "مصرف ليبيا المركزي" OR "المصرف المركزي" OR "الدينار" OR "الميزانية")` |
| `theme:economy:en` | Oil & economy (EN) | `Libya (oil OR crude OR oilfield OR "oil field" OR NOC OR "National Oil Corporation" OR "central bank" OR CBL)` |
| `theme:governance:ar` | Governance & elections (AR) | `ليبيا ("الانتخابات" OR "انتخابات" OR "المفوضية الوطنية العليا للانتخابات" OR "مجلس النواب" OR "المجلس الأعلى للدولة" OR "حكومة الوحدة الوطنية" OR "المجلس الرئاسي" OR "المجلس البلدي")` |
| `theme:governance:en` | Governance & elections (EN) | `Libya (election OR elections OR HNEC OR "House of Representatives" OR "High Council of State" OR "Government of National Unity" OR GNU OR "Presidential Council")` |
| `theme:health:ar` | Health (AR) | `ليبيا ("مستشفى" OR "المستشفيات" OR "وزارة الصحة" OR "الأدوية" OR "المستلزمات الطبية" OR "تفشي" OR "الكوليرا" OR "التطعيم")` |
| `theme:health:en` | Health (EN) | `Libya (hospital OR hospitals OR "health ministry" OR medicines OR "medical supplies" OR outbreak OR cholera OR vaccination)` |
| `theme:migration:ar` | Migration & detention (AR) | `ليبيا ("مهاجر" OR "مهاجرين" OR "المهاجرين" OR "لاجئ" OR "لاجئين" OR "اللجوء" OR "مركز احتجاز" OR "مراكز الاحتجاز")` |
| `theme:migration:en` | Migration & detention (EN) | `Libya (migrant OR migrants OR refugee OR refugees OR asylum OR "detention centre" OR "detention center" OR trafficking)` |
| `theme:security:ar` | Security & armed groups (AR) | `ليبيا ("ميليشيا" OR "ميليشيات" OR "مليشيات" OR "مجموعات مسلحة" OR "جماعات مسلحة" OR "اشتباكات" OR "اشتباك" OR "وقف إطلاق النار")` |
| `theme:security:en` | Security & armed groups (EN) | `Libya (militia OR militias OR "armed group" OR "armed groups" OR clashes OR fighting OR ceasefire OR airstrike)` |
| `theme:services:ar` | Public services (water & power) (AR) | `ليبيا ("انقطاع الكهرباء" OR "الكهرباء" OR "طرح الأحمال" OR "الشركة العامة للكهرباء" OR "إمدادات المياه" OR "المياه" OR "النهر الصناعي" OR "الصرف الصحي")` |
| `theme:services:en` | Public services (water & power) (EN) | `Libya ("power cut" OR "power cuts" OR blackout OR electricity OR GECOL OR "water supply" OR "Great Man-Made River" OR "Man-Made River")` |

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
