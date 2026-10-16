from pkbrain.brain.extractor import RulesExtractor


def test_splits_sections_by_dimension_code_or_name(schema):
    text = "# 标题\n\n## D1 身体\n\n睡了 6 小时。\n\n## 情绪\n\n还行。\n"
    result = RulesExtractor(schema).extract(text)
    assert result.sections == {"D1": "睡了 6 小时。", "D2": "还行。"}
    assert result.dims == ["D1", "D2"]


def test_unknown_sections_and_loose_text_are_kept(schema):
    text = "# 标题\n\n开头一句。\n\n## 今日总结\n\n想去散步。\n"
    result = RulesExtractor(schema).extract(text)
    assert result.sections == {}
    assert "开头一句。" in result.free_text
    assert "「今日总结」" in result.free_text
    assert "想去散步。" in result.free_text


def test_free_record_heading_does_not_leave_a_duplicate_title(schema):
    result = RulesExtractor(schema).extract("## 自由记录\n\n下雨了，没去散步。")
    assert result.free_text == "下雨了，没去散步。"
    assert result.sections == {}


def test_extracts_metrics_with_units(schema):
    result = RulesExtractor(schema).extract("昨晚睡眠 6.5 小时，质量 3。体重 71.2 公斤，精力 3。")
    assert result.metrics == {"sleep_hours": 6.5, "sleep_quality": 3, "weight_kg": 71.2, "energy": 3}


def test_int_metrics_are_rounded(schema):
    result = RulesExtractor(schema).extract("跑了 30 分钟")
    assert result.metrics["exercise_min"] == 30
    assert isinstance(result.metrics["exercise_min"], int)


def test_out_of_range_metric_is_dropped_with_warning(schema):
    result = RulesExtractor(schema).extract("体重 12 公斤")
    assert "weight_kg" not in result.metrics
    assert any("低于下限" in w for w in result.warnings)


def test_repeated_metric_takes_the_first(schema):
    result = RulesExtractor(schema).extract("心情 2。晚点又觉得心情 5。")
    assert result.metrics["mood"] == 2
    assert any("取第一处" in w for w in result.warnings)


def test_empty_input_is_empty(schema):
    result = RulesExtractor(schema).extract("\n\n")
    assert result.is_empty()
