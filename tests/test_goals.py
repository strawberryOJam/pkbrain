from datetime import date

from pkbrain import goals as goals_module

TODAY = date(2026, 10, 16)


def test_parse_marks_text_due_and_dim():
    items = goals_module.parse(
        "# 目标\n\n- [ ] 联系客户确认合同 (2026-10-20) #D3\n- [x] 换掉椅子 (2026-10-01)\n- [ ] 每周跑三次 #D1\n"
    )
    assert [g.text for g in items] == ["联系客户确认合同", "换掉椅子", "每周跑三次"]
    assert items[0].due == date(2026, 10, 20)
    assert items[0].dim == "D3"
    assert items[0].line == 3
    assert items[1].done is True
    assert items[1].dim is None
    assert items[2].due is None
    assert items[2].dim == "D1"


def test_parse_ignores_ordinary_lines():
    assert goals_module.parse("# 标题\n普通段落\n\n- 没有复选框\n") == []


def test_load_returns_nothing_without_a_file(tmp_path, schema):
    assert goals_module.load(tmp_path, schema) == []


def test_load_reads_the_data_dir(tmp_path, schema):
    path = goals_module.write_default(tmp_path, schema)
    assert path == tmp_path / schema.paths["goals"]
    # 模板里的例子是注释掉的，不该被当成真目标
    assert goals_module.load(tmp_path, schema) == []

    path.write_text("- [ ] 把 PKBrain 用到第 14 天 (2026-10-30) #D3\n", encoding="utf-8")
    assert [g.text for g in goals_module.load(tmp_path, schema)] == ["把 PKBrain 用到第 14 天"]


def test_most_urgent_picks_the_nearest_due_date():
    items = goals_module.parse(
        "- [ ] 远的 (2026-10-25)\n- [ ] 近的 (2026-10-18)\n- [ ] 已过的 (2026-10-10)\n"
    )
    assert goals_module.most_urgent(items, TODAY).text == "已过的"


def test_most_urgent_ignores_distant_goals():
    items = goals_module.parse("- [ ] 学会游泳 (2026-12-31)\n")
    assert goals_module.most_urgent(items, TODAY, within_days=7) is None


def test_most_urgent_falls_back_to_an_undated_goal():
    items = goals_module.parse("- [ ] 学会游泳 (2026-12-31)\n- [ ] 每周跑三次\n")
    assert goals_module.most_urgent(items, TODAY, within_days=7).text == "每周跑三次"


def test_most_urgent_skips_finished_goals():
    assert goals_module.most_urgent(goals_module.parse("- [x] 做完了 (2026-10-16)\n"), TODAY) is None


def test_most_urgent_on_an_empty_list():
    assert goals_module.most_urgent([], TODAY) is None
