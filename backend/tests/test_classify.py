from app.classify import PlaceRule, ThemeRule, classify_themes, tag_places
from app.textnorm import detect_lang, normalise, term_variants


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
    assert set(classify_themes("Residents in Sabha protest over power cuts", r)) == set()  # 'power cuts' != 'power cut'
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


def test_detect_lang():
    assert detect_lang("انقطاع الكهرباء في طرابلس") == "ar"
    assert detect_lang("Power cuts in Tripoli") == "en"


def test_cooc_and_strict():
    w = ["النساء", "امرأة", "ابنتيه", "women"]
    v = ["تغتال", "يقتل", "killed"]
    r = ThemeRule.build(9, "gv", 1, ["femicide"], ["العنف ضد المرأة"], ["المبعوثة الأممية"], cooc=[w, v], strict=True)
    assert r.strict
    assert set(classify_themes("عندما تُغتال النساء في ليبيا", [r])) == {9}
    assert set(classify_themes("أب يقتل ابنتيه في بنغازي", [r])) == {9}
    assert set(classify_themes("Two women killed in Tripoli shelling", [r])) == {9}
    assert classify_themes("النساء في سوق العمل", [r]) == {}          # women word alone: no
    assert classify_themes("يقتل مسلح في طرابلس", [r]) == {}          # issue word alone: no
    assert set(classify_themes("حملة العنف ضد المرأة", [r])) == {9}   # phrase still works


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
    assert term_variants("women's representation") == ["women representation"]
