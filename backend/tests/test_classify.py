from app.classify import PlaceRule, ThemeRule, classify_themes, tag_places
from app.textnorm import detect_lang, english_plural, normalise, term_variants


def test_normalise_arabic_variants():
    assert normalise("أجدابيا") == normalise("اجدابيا")
    assert normalise("مستشفى") == normalise("مستشفي")
    assert normalise("درنة") == normalise("درنه")
    assert normalise("الكَهْرَبَاء") == normalise("الكهرباء")
    assert normalise("Power-cuts!") == " power cuts "


def test_arabic_prefix_variants():
    v = term_variants("الكهرباء")
    assert "بالكهرباء" in v and "والكهرباء" in v and "كهرباء" in v


def rules():
    return [
        ThemeRule.build(1, "services", 1, ["power cut", "electricity"], ["انقطاع الكهرباء", "الكهرباء"], []),
        ThemeRule.build(2, "economy", 1, ["oil"], ["النفط"], ["olive oil", "زيت الزيتون"]),
        ThemeRule.build(3, "health", 1, ["hospital"], ["مستشفى"], []),
    ]


def test_theme_matching_en_ar():
    r = rules()
    assert set(classify_themes("Residents in Sabha protest over power cuts", r)) == {1}  # 'power cuts' is the plural of 'power cut'
    assert set(classify_themes("Electricity shortages hit Sabha hospital", r)) == {1, 3}
    assert set(classify_themes("احتجاجات في سبها بسبب انقطاع الكهرباء", r)) == {1}
    assert set(classify_themes("نقص الأدوية في المستشفى العام", r)) == {3}
    assert set(classify_themes("وزارة الصحة تزور بمستشفى درنه", r)) == {3}


def test_exclusions_veto():
    r = rules()
    assert classify_themes("Libyan olive oil exports rise", r) == {}
    assert set(classify_themes("NOC says oil output rises", r)) == {2}


def test_whole_word_only():
    r = [ThemeRule.build(1, "x", 1, ["oil"], [], [])]
    assert classify_themes("Turmoil in Tripoli", r) == {}


def test_places_spelling_variants():
    p = [PlaceRule.build(10, ["Ajdabiya", "أجدابيا"]), PlaceRule.build(11, ["Derna", "Darnah", "درنة"])]
    assert tag_places("Flooding in Darnah", p) == [11]
    assert tag_places("فيضانات في درنه واجدابيا", p) == [10, 11]
    assert tag_places("وصل الوفد إلى أجدابيا", p) == [10]


def test_place_homonyms_need_an_anchor_and_negatives_veto():
    libya = [v for t in ("ليبيا", "Libya", "Libyan", "الليبية") for v in term_variants(t)]
    khoms = PlaceRule.build(20, ["Khoms", "الخمس", "زليتن"], ambiguous=["الخمس"])
    tripoli = PlaceRule.build(21, ["Tripoli", "طرابلس"],
                              negatives={"Tripoli": ["Lebanon", "Lebanese"], "طرابلس": ["لبنان", "شمال لبنان"]})
    barqa = PlaceRule.build(22, ["Cyrenaica", "برقة"], ambiguous=["برقة"])
    p = [khoms, tripoli, barqa]
    # الخمس -> خمس "five": the bare word is never the city, with or without the country beside it
    assert "خمس" not in khoms.ambiguous and "الخمس" in khoms.ambiguous and "بالخمس" in khoms.ambiguous
    assert tag_places("خمس نصائح لتوفير الكهرباء", p, libya) == []
    assert tag_places("خمس سنوات على الحرب في ليبيا", p, libya) == []
    # the definite form is the city, but only beside the country or an unambiguous place
    assert tag_places("اشتباكات في الخمس", p, libya) == []
    assert tag_places("اشتباكات في الخمس", p, libya, anchored=True) == [20]   # a Libyan outlet's own local story
    assert tag_places("خمس نصائح لتوفير الكهرباء", p, libya, anchored=True) == []   # the bare word stays "five"
    assert tag_places("اشتباكات في الخمس غرب ليبيا", p, libya) == [20]
    assert tag_places("الطريق بين الخمس وزليتن مغلق", p, libya) == [20]
    assert tag_places("حريق بمصنع بالخمس والشركة الليبية تحقق", p, libya) == [20]   # a demonym anchors too
    # Tripoli, Lebanon: a negative vetoes the alias wherever it appears
    assert tag_places("Clashes in Tripoli", p, libya) == [21]
    assert tag_places("Clashes in Tripoli, Lebanon, leave two dead", p, libya) == []
    assert tag_places("Libya and Lebanon: clashes in Tripoli", p, libya) == []
    assert tag_places("اشتباكات في طرابلس شمال لبنان", p, libya) == []
    assert tag_places("اشتباكات في طرابلس الليبية", p, libya) == [21]
    # برقة is also "gently" (بِرِقّة)
    assert tag_places("تحدث برقة عن الوضع", p, libya) == []
    assert tag_places("قبائل برقة تطالب الحكومة الليبية", p, libya) == [22]
    assert tag_places("Cyrenaica tribes meet", p, libya) == [22]
    # without a country list an ambiguous alias still anchors on another region's plain alias
    assert tag_places("طرابلس وبرقة", p) == [21, 22]
    assert tag_places("برقة", p) == []


def test_detect_lang():
    assert detect_lang("انقطاع الكهرباء في طرابلس") == "ar"
    assert detect_lang("Power cuts in Tripoli") == "en"
    assert detect_lang("") == "und" and detect_lang(None) == "und"


def test_detect_lang_french_and_italian():
    """A-R2.9: French and Italian headlines are no longer 'en', so they leave the English side of the
    Arabic-English balance. Function words decide; a name alone (Meloni, Roma) is not a language."""
    assert detect_lang("Libye : des migrants secourus au large de Tripoli") == "fr"
    assert detect_lang("La Libye et l'Italie signent un accord sur le pétrole") == "fr"
    assert detect_lang("Les forces de Haftar à Syrte") == "fr"
    assert detect_lang("Libia, naufragio al largo di Tripoli: 20 morti") == "it"
    assert detect_lang("La Libia e il petrolio: cosa cambia dopo l'accordo") == "it"
    assert detect_lang("Libia: scontri a Tripoli, è caos") == "it"
    assert detect_lang("Agenzia Nova: Libia, il governo di Tripoli annuncia nuove misure") == "it"
    # genuine English stays English: 'in', 'non-' and names are not Italian, a possessive 's is not French
    assert detect_lang("Libya's NOC says oil output rises after clashes in the west") == "en"
    assert detect_lang("GNU minister: the non-governmental groups will meet in Tripoli") == "en"
    assert detect_lang("Dbeibah meets Meloni in Rome") == "en"
    assert detect_lang("Migrants rescued off Libya, IOM says") == "en"
    # too little to go on reads as English, as before
    assert detect_lang("Scontri a Tripoli") == "en"


def test_english_plural_variants_match():
    """A-R2.9: a term matches its regular plural / third-person form; a phrase inflects its last word;
    Arabic terms, -ed forms and words already plural are left alone."""
    assert term_variants("clash") == ["clash", "clashes"]
    assert term_variants("refinery") == ["refineries", "refinery"]
    assert term_variants("power cut") == ["power cut", "power cuts"]
    assert term_variants("first woman") == ["first woman", "first women"]
    assert term_variants("killed") == ["killed"] and term_variants("migrants") == ["migrants"]
    assert term_variants("Resolution 1325") == ["resolution 1325"]
    assert english_plural("box") == "boxes" and english_plural("day") == "days" and english_plural("ab") is None
    assert term_variants("fuel") == ["fuel"] and term_variants("fuel shortage") == ["fuel shortage", "fuel shortages"]
    assert term_variants("مستشفى") == term_variants("مستشفي") and "مستشفىs" not in term_variants("مستشفى")
    r = [ThemeRule.build(1, "security", 1, ["clash", "militia", "kill"], [], []),
         ThemeRule.build(2, "economy", 1, ["refinery"], [], ["olive oil"])]
    assert set(classify_themes("Militias clash near the Zawiya refinery", r)) == {1, 2}
    assert set(classify_themes("Gunman kills two in clashes", r)) == {1}
    assert set(classify_themes("Refineries idle as militias fight", r)) == {1, 2}
    assert classify_themes("Olive oils from Libya win prizes", r) == {}    # the exclusion inflects too
    # the evidence names the term as written, and a plural is the same word for the two-words rule
    assert r[0].match(normalise("Militias clash in Tripoli")) == ("title", ["clash", "militia"])
    assert r[0].match(normalise("Report"), [normalise("Three militias and a militia leader were seen")]) is None


def test_cooc_and_strict():
    w = ["النساء", "امرأة", "ابنتيه", "women"]
    v = ["تغتال", "يقتل", "killed", "مقتل"]
    r = ThemeRule.build(9, "gv", 1, ["femicide"], ["العنف ضد المرأة"], ["كرة القدم النسائية"], cooc=[w, v], strict=True,
                        cooc_veto_context=["shelling", "قصف", "UN envoy"])
    assert r.strict
    assert set(classify_themes("عندما تُغتال النساء في ليبيا", [r])) == {9}
    assert set(classify_themes("أب يقتل ابنتيه في بنغازي", [r])) == {9}
    # conflict casualties are not violence against women: a pair-veto word next to the pair stops it
    assert classify_themes("Two women killed in Tripoli shelling", [r]) == {}
    assert classify_themes("مقتل ثلاث نساء في قصف على طرابلس", [r]) == {}
    assert set(classify_themes("Two women killed by a relative in Tripoli", [r])) == {9}   # the pair itself still counts
    assert set(classify_themes("مقتل ثلاث نساء على يد مسلح في طرابلس", [r])) == {9}
    # the veto reaches only COOC_WINDOW tokens: a far-away context word does not stop a pair
    assert set(classify_themes("Two women killed by their husbands at home, police say, hours after shelling elsewhere", [r])) == {9}
    assert classify_themes("UN envoy meets women killed", [r]) == {}   # a phrase context taints the words beside it
    assert classify_themes("النساء في سوق العمل", [r]) == {}          # women word alone: no
    assert classify_themes("يقتل مسلح في طرابلس", [r]) == {}          # issue word alone: no
    assert set(classify_themes("حملة العنف ضد المرأة", [r])) == {9}   # phrase still works
    assert set(classify_themes("حملة العنف ضد المرأة بعد قصف", [r])) == {9}   # the veto never touches the phrases


def test_ta_marbuta_does_not_match_possessive():
    r = ThemeRule.build(1, "x", 1, [], ["النائبة"], [])
    assert set(classify_themes("تصريح النائبة حول القانون", [r])) == {1}
    assert set(classify_themes("وقالت والنائبة إن", [r])) == {1}
    assert classify_themes("لقاء عقيلة بالكبير ونائبه", [r]) == {}   # "and his deputy"


def test_english_possessive_is_stripped():
    assert normalise("Libya's NOC") == " libya noc "
    assert normalise("NOC’s output") == " noc output "
    assert normalise("migrants' rights") == " migrants rights "
    assert normalise("Women's Representation") == normalise("women's representation") == " women representation "
    assert normalise("O'Sullivan don't") == " osullivan dont "
    assert normalise("مجلس النواب الليبي") == " مجلس النواب الليبي "   # Arabic untouched
    r = [ThemeRule.build(1, "economy", 1, ["NOC"], [], [])]
    assert set(classify_themes("Libya's NOC reports output", r)) == {1}
    assert set(classify_themes("NOC's chairman visits Brega", r)) == {1}
    assert term_variants("women's representation") == ["women representation", "women representations"]
