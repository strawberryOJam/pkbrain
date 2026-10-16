from datetime import date, timedelta

from pkbrain.brain.questions import QuestionEngine, State, load_state, save_state


def engine(schema, store, today=date(2026, 10, 16), state=None):
    return QuestionEngine(schema, store, data_dir=store.path.parent, today=today, state=state)


def kinds(questions):
    return [q.kind for q in questions]


# ---- 优先级 3：精神层反思（第一次跑时唯一能问的）----------------------


def test_first_night_only_asks_a_reflection(schema, store):
    picked = engine(schema, store).plan()
    assert kinds(picked) == ["reflection"]
    assert picked[0].text in schema.reflections()
    assert picked[0].dim is None


def test_reflection_is_not_asked_twice_within_a_week(schema, store, add):
    add("## D1 身体\n\n跑了 30 分钟。", date(2026, 10, 15))
    state = State(last_reflection_date="2026-10-13")
    picked = engine(schema, store, state=state).plan()
    assert "reflection" not in kinds(picked)


def test_reflection_comes_back_after_a_week(schema, store, add):
    add("## D1 身体\n\n跑了 30 分钟。", date(2026, 10, 15))
    state = State(last_reflection_date="2026-10-09")
    picked = engine(schema, store, state=state).plan()
    assert "reflection" in kinds(picked)


def test_commit_advances_the_rotation(schema, store):
    state = State(reflection_index=0)
    question_engine = engine(schema, store, state=state)
    picked = question_engine.plan()
    question_engine.commit(picked)

    assert state.reflection_index == 1
    assert state.last_reflection_date == "2026-10-16"
    reloaded = load_state(store.path.parent, schema)
    assert reloaded.last_reflection_date == "2026-10-16"


def test_state_round_trips_on_disk(schema, store):
    save_state(store.path.parent, schema, State(reflection_index=2, last_reflection_date="2026-10-01"))
    loaded = load_state(store.path.parent, schema)
    assert loaded.reflection_index == 2
    assert loaded.last_reflection_date == "2026-10-01"


def test_broken_state_file_falls_back_to_defaults(schema, store):
    path = store.path.parent / schema.paths["state"]
    path.write_text("{ 不是 json", encoding="utf-8")
    assert load_state(store.path.parent, schema) == State()


# ---- 优先级 1：悬而未决项与缺口 ----------------------------------------


def test_follows_up_on_yesterdays_loose_ends(schema, store, add):
    add("## D4 关系\n\n明天要把合同的事往前推一步。", date(2026, 10, 15))
    picked = engine(schema, store).plan()
    followup = next(q for q in picked if q.kind == "followup")
    assert "合同的事" in followup.text
    assert "后来" in followup.text


def test_follows_up_on_a_record_from_up_to_a_week_ago(schema, store, add):
    add("## D1 身体\n\n下周要去做体检。", date(2026, 10, 13))
    picked = engine(schema, store).plan()
    assert "followup" in kinds(picked)


def test_ignores_records_older_than_a_week(schema, store, add):
    add("## D1 身体\n\n下周要去做体检。", date(2026, 10, 1))
    picked = engine(schema, store).plan()
    assert "followup" not in kinds(picked)
    assert "gap" not in kinds(picked)


def test_asks_about_the_missing_dimension(schema, store, add):
    add("## D1 身体\n\n跑了 30 分钟，感觉还行。", date(2026, 10, 15))
    picked = engine(schema, store).plan()
    gap = next(q for q in picked if q.kind == "gap")
    assert gap.dim == "D2"
    assert gap.text == schema.probe("D2")


def test_no_gap_question_when_yesterday_covers_every_dimension(schema, store, add):
    text = "## D1 身体\n\n跑了 30 分钟。\n\n## D2 情绪\n\n还行。\n\n## D3 事业\n\n推进了。\n\n## D4 关系\n\n见了朋友。"
    add(text, date(2026, 10, 15))
    picked = engine(schema, store).plan()
    assert "gap" not in kinds(picked)


def test_priority_one_takes_at_most_two_slots(schema, store, add):
    add("## D1 身体\n\n明天要去见客户，还得准备材料。", date(2026, 10, 15))
    picked = engine(schema, store).plan(limit=4)
    assert kinds(picked).count("followup") == 1
    assert kinds(picked).count("gap") == 1


# ---- 优先级 2：目标 -----------------------------------------------------


def test_asks_about_a_goal_due_soon(schema, store):
    goals = store.path.parent / schema.paths["goals"]
    goals.write_text("- [ ] 联系客户确认合同 (2026-10-20) #D3\n", encoding="utf-8")

    picked = engine(schema, store).plan()
    goal = next(q for q in picked if q.kind == "goal")
    assert "联系客户确认合同" in goal.text
    assert "还有 4 天" in goal.text
    assert goal.dim == "D3"


def test_skips_a_goal_that_is_far_away(schema, store):
    goals = store.path.parent / schema.paths["goals"]
    goals.write_text("- [ ] 学会游泳 (2026-12-31) #D1\n", encoding="utf-8")
    picked = engine(schema, store).plan()
    assert "goal" not in kinds(picked)


def test_asks_about_an_undated_goal(schema, store):
    goals = store.path.parent / schema.paths["goals"]
    goals.write_text("- [ ] 每周跑三次\n", encoding="utf-8")
    picked = engine(schema, store).plan()
    assert any(q.kind == "goal" for q in picked)


def test_done_goals_are_ignored(schema, store):
    goals = store.path.parent / schema.paths["goals"]
    goals.write_text("- [x] 换掉椅子 (2026-10-16) #D1\n", encoding="utf-8")
    picked = engine(schema, store).plan()
    assert "goal" not in kinds(picked)


# ---- 优先级 4：回顾旧记忆 ----------------------------------------------


def test_revisits_an_old_record(schema, store, add):
    add("## D2 情绪\n\n那天很累。", date(2026, 9, 16))  # 三十天前
    add("## D1 身体\n\n跑了 30 分钟。", date(2026, 10, 15))
    picked = engine(schema, store).plan(limit=4)
    revisit = next(q for q in picked if q.kind == "revisit")
    assert "30 天前的今天" in revisit.text
    assert "很累" in revisit.text


def test_no_revisit_on_an_empty_history(schema, store):
    assert "revisit" not in kinds(engine(schema, store).plan(limit=4))


# ---- 配额 ---------------------------------------------------------------


def test_budget_is_respected(schema, store, add):
    add("## D1 身体\n\n明天要去见客户。", date(2026, 10, 15))
    add("## D2 情绪\n\n那天很累。", date(2026, 9, 16))
    goals = store.path.parent / schema.paths["goals"]
    goals.write_text("- [ ] 每周跑三次\n", encoding="utf-8")

    assert len(engine(schema, store).plan(limit=2)) == 2
    assert len(engine(schema, store).plan()) <= schema.session_limit("max_questions", 3)


def test_falls_back_to_the_most_recent_record_within_a_week(schema, store, add):
    """昨天没记，就往前找最近一条，一周以内还算数。"""
    add("## D1 身体\n\n明天要出差。", date(2026, 10, 14))
    picked = engine(schema, store, today=date(2026, 10, 17)).plan()
    assert "followup" in kinds(picked)


def test_engine_uses_todays_random_seed(schema, store, add):
    for offset in (30, 60, 90):
        add("## D1 身体\n\n跑了 30 分钟。", date(2026, 10, 16) - timedelta(days=offset))
    first = engine(schema, store).plan(limit=4)
    second = engine(schema, store).plan(limit=4)
    assert [q.text for q in first] == [q.text for q in second]
