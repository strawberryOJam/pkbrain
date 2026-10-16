"""MCP：工具面、读写、以及一次真实的 stdio 往返。

工具调用都走 `MCPServer.call_tool`，与客户端收到的是同一条路径；最后一个用例真的把
`pkbrain mcp` 拉起来，用官方客户端的 stdio 传输走一遍握手。
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import date

import pytest

from pkbrain.brain.questions import load_state
from pkbrain.config import Config, McpConfig
from pkbrain.server import mcp as mcp_module

TODAY = date(2026, 10, 16)

SLEEP = """\
# 2026-10-15 晚间快照

## D1 身体
昨晚睡了 6.5 小时，质量一般。没运动。

## D2 情绪
客户的事悬着，有点焦虑。
"""


@pytest.fixture
def server(tmp_path, schema):
    return mcp_module.build_server(tmp_path, schema, Config())


def call(server, tool: str, **arguments) -> str:
    result = asyncio.run(server.call_tool(tool, arguments))
    return result.content[0].text


# ---- 工具面 ---------------------------------------------------------------


def test_the_tool_surface_is_what_the_docs_claim(server):
    listed = asyncio.run(server.list_tools())
    assert [tool.name for tool in listed] == [name for name, _ in mcp_module.TOOLS]
    assert all(tool.description for tool in listed)


def test_schema_tool_lists_the_vocabulary(server):
    text = call(server, "brain_schema")
    assert "D1 身体" in text
    assert "sleep_hours（h，D1）" in text
    assert "夜间睡眠时长" in text
    assert "P2 敏感" in text
    assert "manual, chat, audio, device, weather" in text
    assert "已有记录 0 条" in text


def test_stats_says_there_is_nothing_yet(server):
    assert "还没有记录" in call(server, "brain_stats")


def test_stats_reports_records(tmp_path, schema, add, server):
    add(SLEEP, TODAY)
    text = call(server, "brain_stats")
    assert "记录 1 条" in text
    assert "完整率 100.0%" in text


# ---- 检索 -----------------------------------------------------------------


def test_search_finds_a_record(tmp_path, schema, add, server):
    add(SLEEP, TODAY)
    text = call(server, "search_records", query="小时")
    assert "共 1 条" in text
    assert TODAY.isoformat() in text
    assert "睡了 6.5 小时" in text


def test_search_without_a_query_lists_recent_records(tmp_path, schema, add, server):
    add(SLEEP, TODAY)
    text = call(server, "search_records", limit=5)
    assert "共 1 条" in text


def test_search_can_filter_by_dimension(tmp_path, schema, add, server):
    add(SLEEP, TODAY)
    assert "共 1 条" in call(server, "search_records", dim="D1")
    assert "没有匹配的记录" in call(server, "search_records", dim="D4")


def test_search_with_nothing_matching_points_at_the_way_out(server):
    text = call(server, "search_records", query="量子力学")
    assert "没有匹配的记录" in text


def test_a_bad_date_is_explained_rather_than_raised(server):
    text = call(server, "search_records", since="10/01")
    assert "参数不对" in text
    assert "YYYY-MM-DD" in text

    assert "参数不对" in call(server, "metric_series", name="mood", until="昨天")
    assert "参数不对" in call(server, "add_record", text=SLEEP, day="前天")


def test_get_record_by_date_and_by_id(tmp_path, schema, add, server):
    record, _ = add(SLEEP, TODAY)

    by_date = call(server, "get_record", key=TODAY.isoformat())
    by_id = call(server, "get_record", key=record.id)

    assert by_date == by_id
    assert by_date.startswith("---")
    assert "睡了 6.5 小时" in by_date


def test_get_record_missing_is_a_message_not_a_crash(server):
    text = call(server, "get_record", key="2026-01-01")
    assert "没找到" in text
    assert "search_records" in text


def test_metric_series(tmp_path, schema, add, server):
    add(SLEEP, TODAY)
    text = call(server, "metric_series", name="sleep_hours")
    assert "sleep_hours（h，D1）" in text
    assert "2026-10-16 6.5" in text


def test_metric_series_lists_the_known_names(server):
    text = call(server, "metric_series", name="体温")
    assert "没有指标" in text
    assert "sleep_hours" in text
    assert "mood" in text


def test_list_goals(tmp_path, schema, server):
    path = tmp_path / schema.paths["goals"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("- [ ] 联系客户确认合同 (2026-10-20) #D3\n", encoding="utf-8")

    text = call(server, "list_goals")
    assert "联系客户确认合同" in text
    assert "2026-10-20" in text
    assert "#D3" in text


def test_list_goals_when_there_are_none(server):
    assert "还没有目标" in call(server, "list_goals")


def test_todays_questions_is_read_only(tmp_path, schema, server):
    text = call(server, "todays_questions")
    assert "[" in text
    assert load_state(tmp_path, schema).last_reflection_date is None
    assert not list((tmp_path / schema.paths["records"]).glob("**/*.md"))


# ---- 写入 -----------------------------------------------------------------


def test_add_record_writes_and_is_then_findable(tmp_path, schema, server):
    text = call(server, "add_record", text=SLEEP, day=TODAY.isoformat())
    assert "写入" in text
    assert "维度 D1, D2" in text
    assert "sleep_hours=6.5" in text

    found = call(server, "search_records", query="焦虑")
    assert "共 1 条" in found
    assert "记录 1 条" in call(server, "brain_stats")


def test_add_record_marks_the_channel_and_source(tmp_path, schema, server):
    call(server, "add_record", text=SLEEP, day=TODAY.isoformat(), tags=["claude"])
    hit = call(server, "search_records", query="小时")
    assert "#claude" in hit

    markdown = call(server, "get_record", key=TODAY.isoformat())
    assert "channel: chat" in markdown
    assert "source: mcp" in markdown
    assert "tags: [claude]" in markdown


def test_add_record_defaults_to_today(tmp_path, schema, server):
    text = call(server, "add_record", text=SLEEP)
    assert f"日期 {date.today().isoformat()}" in text


def test_add_record_can_be_turned_off(tmp_path, schema):
    read_only = mcp_module.build_server(tmp_path, schema, Config(mcp=McpConfig(allow_write=False)))
    text = call(read_only, "add_record", text=SLEEP)
    assert "写入被关掉了" in text
    assert "记录 0 条" in call(read_only, "brain_schema")


def test_add_record_says_why_nothing_was_extracted(server):
    text = call(server, "add_record", text="   ")
    assert "没写成" in text


def test_add_record_reports_a_bad_privacy_instead_of_writing(server):
    text = call(server, "add_record", text=SLEEP, privacy="P9")
    assert "没写成" in text
    assert "记录 0 条" in call(server, "brain_schema")


# ---- 客户端配置 -----------------------------------------------------------


def test_client_config_points_at_the_data_dir(tmp_path):
    data = json.loads(mcp_module.client_config(tmp_path))
    entry = data["mcpServers"]["pkbrain"]
    assert entry["command"] == "pkbrain"
    assert entry["args"] == ["mcp", "--data-dir", str(tmp_path)]


# ---- 真跑一遍 -------------------------------------------------------------


def test_stdio_round_trip_with_the_official_client(tmp_path, schema):
    from mcp.client.session import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "pkbrain", "mcp", "--data-dir", str(tmp_path)],
        env=dict(os.environ),
    )

    async def round_trip():
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write, read_timeout_seconds=30.0) as session:
                await session.initialize()
                listed = await session.list_tools()
                stats = await session.call_tool("brain_stats", {})
                return [tool.name for tool in listed.tools], stats.content[0].text

    names, stats_text = asyncio.run(round_trip())

    assert names == [name for name, _ in mcp_module.TOOLS]
    assert "还没有记录" in stats_text
