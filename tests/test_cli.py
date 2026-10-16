"""CLI 端到端：init → snapshot → search → show → stats。"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from pkbrain.cli import app
from pkbrain.schema import load_schema

runner = CliRunner()


@pytest.fixture
def example() -> str:
    return str(load_schema().source_dir.parent / "examples" / "today.md")


def test_init_creates_the_database(tmp_path):
    result = runner.invoke(app, ["init", "--data-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert (tmp_path / "pkbrain.db").is_file()
    assert (tmp_path / "records").is_dir()


def test_snapshot_then_search_then_show(tmp_path, example):
    assert runner.invoke(app, ["init", "--data-dir", str(tmp_path)]).exit_code == 0

    result = runner.invoke(
        app,
        [
            "snapshot",
            "--data-dir",
            str(tmp_path),
            "--from-file",
            example,
            "--date",
            "2026-10-16",
            "--tag",
            "晚间",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "记录" in result.output

    found = runner.invoke(app, ["search", "--data-dir", str(tmp_path), "睡眠"])
    assert found.exit_code == 0
    assert "2026-10-16" in found.output
    assert "共 1 条" in found.output

    missed = runner.invoke(app, ["search", "--data-dir", str(tmp_path), "不存在的词"])
    assert "没有匹配的记录。" in missed.output

    shown = runner.invoke(app, ["show", "--data-dir", str(tmp_path), "2026-10-16"])
    assert shown.exit_code == 0
    assert "## D1 身体" in shown.output
    assert "## 指标" in shown.output

    summary = runner.invoke(app, ["stats", "--data-dir", str(tmp_path)])
    assert "记录 1 条" in summary.output
    assert "sleep_hours 1" in summary.output


def test_search_json(tmp_path, example):
    runner.invoke(app, ["snapshot", "--data-dir", str(tmp_path), "--from-file", example])
    result = runner.invoke(app, ["search", "--data-dir", str(tmp_path), "--json", "睡眠"])
    payload = json.loads(result.output)
    assert len(payload) == 1
    assert payload[0]["dims"] == ["D1", "D2", "D3", "D4"]
    assert "睡眠" in payload[0]["excerpt"]


def test_snapshot_reports_empty_input(tmp_path):
    blank = tmp_path / "blank.md"
    blank.write_text("   \n", encoding="utf-8")
    result = runner.invoke(app, ["snapshot", "--data-dir", str(tmp_path), "--from-file", str(blank)])
    assert result.exit_code == 1
    assert "没写成" in result.output


def test_search_without_any_records_is_not_an_error(tmp_path):
    result = runner.invoke(app, ["search", "--data-dir", str(tmp_path), "睡眠"])
    assert result.exit_code == 0
    assert "没有匹配的记录。" in result.output


def test_show_missing_record_exits_nonzero(tmp_path):
    result = runner.invoke(app, ["show", "--data-dir", str(tmp_path), "2026-01-01"])
    assert result.exit_code == 1
    assert "没找到" in result.output


def test_unknown_channel_is_rejected(tmp_path, example):
    result = runner.invoke(
        app,
        ["snapshot", "--data-dir", str(tmp_path), "--from-file", example, "--channel", "telepathy"],
    )
    assert result.exit_code == 1


def test_stats_without_records_points_at_the_next_step(tmp_path):
    result = runner.invoke(app, ["stats", "--data-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "还没有记录" in result.output


# ---- M1：每晚的会话 -----------------------------------------------------


def test_init_creates_goals_and_config(tmp_path):
    result = runner.invoke(app, ["init", "--data-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert (tmp_path / "goals.md").is_file()
    assert (tmp_path / "config.toml").is_file()
    assert (tmp_path / "sessions").is_dir()


def test_plan_prints_tonight_questions_without_writing(tmp_path):
    result = runner.invoke(app, ["plan", "--data-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "reflection" in result.output
    assert not (tmp_path / "records").exists() or not list((tmp_path / "records").rglob("*.md"))


def test_talk_answers_from_a_file(tmp_path):
    answers = tmp_path / "answers.txt"
    answers.write_text("昨晚睡了 7 小时。\n把检索调通了。\n", encoding="utf-8")

    result = runner.invoke(
        app, ["talk", "--data-dir", str(tmp_path), "--answers-file", str(answers)]
    )
    assert result.exit_code == 0, result.output
    assert "sleep_hours=7" in result.output
    assert "转写" in result.output

    found = runner.invoke(app, ["search", "--data-dir", str(tmp_path), "7 小时"])
    assert "共 1 条" in found.output


def test_talk_skips_the_second_run_the_same_day(tmp_path):
    """pending 文件用掉就删。当天已经答过，第二轮就没什么可问的了。"""
    answers = tmp_path / "answers.txt"
    answers.write_text("今天还行。\n", encoding="utf-8")
    first = runner.invoke(app, ["talk", "--data-dir", str(tmp_path), "--answers-file", str(answers)])
    assert first.exit_code == 0

    second = runner.invoke(
        app, ["talk", "--data-dir", str(tmp_path), "--answers-file", str(answers)]
    )
    assert second.exit_code == 0
    assert "已经备好的" not in second.output
    assert "今晚没有问题。" in second.output

    summary = runner.invoke(app, ["stats", "--data-dir", str(tmp_path)])
    assert "记录 1 条" in summary.output


def test_talk_uses_the_pending_questions_from_serve(tmp_path):
    assert runner.invoke(app, ["serve", "--now", "--data-dir", str(tmp_path)]).exit_code == 0

    answers = tmp_path / "answers.txt"
    answers.write_text("今年想少加点班。\n", encoding="utf-8")
    result = runner.invoke(
        app, ["talk", "--data-dir", str(tmp_path), "--answers-file", str(answers)]
    )
    assert result.exit_code == 0
    assert "已经备好的" in result.output


def test_talk_without_any_answer_exits_nonzero(tmp_path):
    blank = tmp_path / "answers.txt"
    blank.write_text("\n\n", encoding="utf-8")
    result = runner.invoke(
        app, ["talk", "--data-dir", str(tmp_path), "--answers-file", str(blank)]
    )
    assert result.exit_code == 1
    assert "没写成" in result.output


def test_stats_reports_coverage(tmp_path, example):
    runner.invoke(app, ["snapshot", "--data-dir", str(tmp_path), "--from-file", example])
    result = runner.invoke(app, ["stats", "--data-dir", str(tmp_path)])
    assert "完整率 100.0%" in result.output
    assert "连续 1 天" in result.output
    assert "目标 90% 达标" in result.output


def test_goals_add_and_show(tmp_path):
    added = runner.invoke(
        app,
        ["goals", "add", "联系客户确认合同", "--due", "2026-10-20", "--dim", "D3", "--data-dir", str(tmp_path)],
    )
    assert added.exit_code == 0

    shown = runner.invoke(app, ["goals", "show", "--data-dir", str(tmp_path)])
    assert "联系客户确认合同" in shown.output
    assert "2026-10-20" in shown.output


def test_goals_add_rejects_a_bad_date(tmp_path):
    result = runner.invoke(
        app, ["goals", "add", "写周报", "--due", "下周三", "--data-dir", str(tmp_path)]
    )
    assert result.exit_code != 0


def test_config_show_never_prints_the_key(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-不该出现")
    result = runner.invoke(app, ["config", "show", "--data-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "sk-不该出现" not in result.output
    assert "已设置" in result.output


def test_config_init_and_show(tmp_path):
    assert runner.invoke(app, ["config", "init", "--data-dir", str(tmp_path)]).exit_code == 0
    result = runner.invoke(app, ["config", "show", "--data-dir", str(tmp_path)])
    assert "template" in result.output
    assert "22:00" in result.output
    assert "notify.backend    auto" in result.output
    assert "mcp.allow_write   True" in result.output


def test_mcp_print_config_points_at_the_data_dir(tmp_path):
    result = runner.invoke(app, ["mcp", "--print-config", "--data-dir", str(tmp_path)])
    assert result.exit_code == 0
    entry = json.loads(result.output)["mcpServers"]["pkbrain"]
    assert entry["command"] == "pkbrain"
    assert entry["args"] == ["mcp", "--data-dir", str(tmp_path)]


def test_mcp_rejects_an_unknown_transport(tmp_path):
    result = runner.invoke(app, ["mcp", "--transport", "carrier-pigeon", "--data-dir", str(tmp_path)])
    assert result.exit_code == 1
    assert "没起来" in result.output


def test_notify_reports_where_it_went(tmp_path, schema):
    (tmp_path / schema.paths["config"]).write_text(
        '[notify]\nbackend = "command"\ncommand = "true"\n', encoding="utf-8"
    )
    result = runner.invoke(app, ["notify", "测试一条", "--data-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "发出去了：command" in result.output


def test_notify_says_when_it_did_not_reach_the_system(tmp_path, schema):
    (tmp_path / schema.paths["config"]).write_text(
        '[notify]\nbackend = "none"\n', encoding="utf-8"
    )
    result = runner.invoke(app, ["notify", "测试一条", "--data-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "没走系统通知" in result.output
    assert "config.toml" in result.output
