from pkbrain.text import segment, to_match_query


def test_segment_puts_spaces_around_cjk():
    assert segment("睡眠").strip() == "睡 眠"


def test_segment_keeps_latin_and_digits_together():
    assert segment("跑了30分钟").split() == ["跑", "了", "30", "分", "钟"]


def test_segment_leaves_punctuation_alone():
    assert segment("下雨了。").strip() == "下 雨 了 。"


def test_match_query_uses_one_phrase_per_term():
    assert to_match_query("睡眠") == '"睡 眠"'
    assert to_match_query(" 客户   合同 ") == '"客 户" AND "合 同"'


def test_match_query_keeps_latin_words_whole():
    assert to_match_query("D1 睡眠") == '"D1" AND "睡 眠"'


def test_match_query_drops_quotes():
    assert to_match_query('睡眠"') == '"睡 眠"'


def test_match_query_of_blank_is_empty():
    assert to_match_query("   ") == ""
