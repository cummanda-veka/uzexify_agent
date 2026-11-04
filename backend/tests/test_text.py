import pytest

from uzexify.text import detect_lang, fold, name_key, product_key, to_latin


def test_company_keys():
    assert name_key('"ҲАРАЙЎМ КИМЁ" МЧЖ') == name_key("Harayo‘m Kimyo MCHJ") == "harayom kimyo"
    assert name_key("YEDO‘DO‘ PLAST MAS’ULIYATI CHEKLANGAN JAMIYATI") == "yedodo plast"
    assert name_key("OKA OK") == "oka"


def test_product_key_and_transliteration():
    assert product_key("ПОРТЛАНДЦЕМЕНТ") == "portlandsement"
    assert to_latin("ёғқўҳцщъыьюя") == "yogqohsshiyuya"


@pytest.mark.parametrize("apostrophe", ["ʻ", "ʼ", "‘", "’", "`", "´", "'"])
def test_apostrophes(apostrophe):
    assert name_key(f"YEDO{apostrophe}DO{apostrophe} PLAST MCHJ") == "yedodo plast"


def test_fold_and_language():
    assert fold("  «ТЕСТ», Ａ!  ") == "тест a"
    assert detect_lang("Сколько сделок?") == "ru"
    assert detect_lang("Буғдой") == "uz"
    assert detect_lang("bug‘doy") == "uz"
    assert detect_lang("aя") == "uz"
