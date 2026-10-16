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
