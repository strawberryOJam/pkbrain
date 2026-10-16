"""MCP：把大脑接到任意 agent 上。

走 stdin/stdout 上的 JSON-RPC，客户端是谁都行——Claude Desktop、Cursor、Codex、自己写的 agent：

    pkbrain mcp                     # stdio，本地客户端用这个
    pkbrain mcp --transport http    # streamable-http，别的机器或别的进程接

工具分两半：检索与概览是只读的；`add_record` 写记录，可以在 `config.toml` 的
`[mcp] allow_write = false` 关掉，把大脑变成纯只读。

协议实现用官方 python-sdk（`modelcontextprotocol`），自己不去拼 JSON-RPC。
见 docs/ADR/0006-mcp-接入.md。
"""

from __future__ import annotations

import json
from datetime import date as Date
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from .. import __version__
from .. import goals as goals_module
from ..brain import pipeline
from ..brain.questions import QuestionEngine
from ..brain.report import coverage, describe
from ..config import Config
from ..schema import PkbsSubset
from ..store.sqlite import Hit, Store, db_path

INSTRUCTIONS = """\
这是用户本人的本地个人知识库（PKBrain），数据只存在这台机器上。

用 search_records 找具体记录，用 get_record 取原文，用 metric_series 看某指标随时间的变化，
用 brain_stats 看整体覆盖情况。回答「我上周的运动和情绪有什么关系」这类问题时，
给出结论后要指回具体日期或记录 id，让用户能自己核对。

隐私：记录带 P0（公开）/ P1（私密，默认）/ P2（敏感）三级。P2 是用户特意标成敏感的，
往外发之前先问一句。写记录用 add_record，写之前跟用户确认写什么。
"""

TOOLS: tuple[tuple[str, str], ...] = (
    ("brain_schema", "这份知识库的词汇表：记录类型、维度、指标、隐私分级、采集通道。先看它再写记录。"),
    ("brain_stats", "记录条数、覆盖天数、快照完整率与连续天数。"),
    ("search_records", "全文检索记录。不给检索词就按条件列出最近的记录。"),
    ("get_record", "取一条记录的 Markdown 原文：传日期（当天全部）或记录 id。"),
    ("metric_series", "某个指标随时间的取值序列，如睡眠时长、体重、心情。"),
    ("list_goals", "目标清单，带到期日与归属维度。"),
    ("todays_questions", "今天会问用户什么。只读：不改状态、不写记录。"),
    ("add_record", "把一段文本落成记录，写 Markdown 与索引。"),
)


class Brain:
    """一份数据目录上的工具实现。每次调用自己开一次数据库连接，用完就关。"""

    def __init__(self, data_dir: Path, schema: PkbsSubset, config: Config | None = None) -> None:
        self.data_dir = Path(data_dir)
        self.schema = schema
        self.config = config or Config()

    # ---- 取数 ---------------------------------------------------------

    def _open(self) -> Store:
        return Store(db_path(self.data_dir, self.schema), self.schema)

    @staticmethod
    def _day(raw: str | None, label: str) -> str | None:
        if raw is None or not str(raw).strip():
            return None
        try:
            return Date.fromisoformat(str(raw).strip()).isoformat()
        except ValueError as exc:
            raise ValueError(f"{label} 要写成 YYYY-MM-DD，收到 {raw!r}") from exc

    def _span(self, since: str | None, until: str | None) -> tuple[str | None, str | None, str]:
        """校准日期区间。写错了就回一句人话，别让客户端只看到「Error executing tool」。"""
        try:
            return self._day(since, "since"), self._day(until, "until"), ""
        except ValueError as exc:
            return None, None, f"参数不对：{exc}"

    # ---- 只读工具 -----------------------------------------------------

    def brain_schema(self) -> str:
        schema = self.schema
        lines = [
            f"数据目录 {self.data_dir}",
            f"PKBS 子集 {schema.version}（{schema.status}），标准 {schema.standard}",
            "记录类型：",
        ]
        for code, spec in schema.record_types.items():
            dims = ",".join(spec.get("dims") or []) or "不限定"
            lines.append(f"  {code} {spec['name']}（{spec.get('scope', '-')}）维度 {dims}")
        lines.append("维度：")
        for code, dim in schema.dimensions.items():
            lines.append(f"  {code} {dim.name}（{dim.kind}）")
        lines.append("指标：")
        for metric in schema.metrics.values():
            span = ""
            if metric.min is not None or metric.max is not None:
                low = "-" if metric.min is None else f"{metric.min:g}"
                high = "-" if metric.max is None else f"{metric.max:g}"
                span = f"，范围 {low}–{high}"
            note = f"　{metric.description}" if metric.description else ""
            lines.append(f"  {metric.name}（{metric.unit}，{metric.dim}）{span}{note}")
        levels = "，".join(f"{code} {spec['name']}" for code, spec in schema.privacy.items())
        lines.append(f"隐私：{levels}，默认 {schema.default_privacy}")
        lines.append(f"采集通道：{', '.join(schema.channels)}")
        lines.append(f"自由记录标题：{', '.join(schema.free_headings)}")
        with self._open() as database:
            lines.append(f"已有记录 {database.stats()['records']} 条")
        return "\n".join(lines)

    def brain_stats(self) -> str:
        with self._open() as database:
            info = database.stats()
            share = coverage(database.dates(), today=Date.today())
        return describe(info, share)

    def search_records(
        self,
        query: str | None = None,
        dim: str | None = None,
        since: str | None = None,
        until: str | None = None,
        privacy: str | None = None,
        limit: int = 10,
    ) -> str:
        since, until, problem = self._span(since, until)
        if problem:
            return problem
        terms = query.split() if query else []
        with self._open() as database:
            hits = database.search(
                query, dim=dim, since=since, until=until, privacy=privacy, limit=limit
            )
        if not hits:
            return "没有匹配的记录。试试换个词，或不给检索词、只留日期范围。"
        return "\n".join(_line(hit, terms) for hit in hits) + f"\n共 {len(hits)} 条。"

    def get_record(self, key: str) -> str:
        key = str(key).strip()
        with self._open() as database:
            hits = database.by_date(key) if _is_day(key) else []
            if not hits:
                single = database.by_id(key)
                hits = [single] if single else []
        if not hits:
            return f"没找到 {key}。传日期 YYYY-MM-DD（当天全部记录）或记录 id，先用 search_records 找 id。"
        parts = [Path(hit.path).read_text(encoding="utf-8").rstrip() for hit in hits]
        return "\n\n---\n\n".join(parts)

    def metric_series(self, name: str, since: str | None = None, until: str | None = None) -> str:
        since, until, problem = self._span(since, until)
        if problem:
            return problem
        metric = self.schema.metrics.get(name)
        if metric is None:
            known = "、".join(self.schema.metrics)
            return f"没有指标 {name!r}。现有：{known}。"
        with self._open() as database:
            rows = database.metric_series(name, since=since, until=until)
        if not rows:
            return f"还没有 {name} 的取值。"
        points = [f"{_pretty_day(row['record_id'])} {row['value']:g}" for row in rows]
        return f"{name}（{metric.unit}，{metric.dim}）共 {len(points)} 个取值：\n" + "；\n".join(points)

    def list_goals(self) -> str:
        goals = goals_module.load(self.data_dir, self.schema)
        path = self.data_dir / self.schema.paths["goals"]
        if not goals:
            return f"还没有目标。写在 {path} 里，一行一条：- [ ] 联系客户确认合同 (2026-10-20) #D3"
        lines = [f"{path}"]
        for goal in goals:
            mark = "x" if goal.done else " "
            due = f"（{goal.due}）" if goal.due else ""
            dim = f" #{goal.dim}" if goal.dim else ""
            lines.append(f"[{mark}] {goal.text}{due}{dim}")
        return "\n".join(lines)

    def todays_questions(self, limit: int | None = None) -> str:
        with self._open() as database:
            engine = QuestionEngine(
                self.schema, database, data_dir=self.data_dir, today=Date.today()
            )
            picked = engine.plan(limit)
        if not picked:
            return "今天没有问题：该记的都记了。"
        lines = []
        for index, question in enumerate(picked, start=1):
            dim = f" → {question.dim}" if question.dim else ""
            lines.append(f"{index}. [{question.kind}{dim}] {question.text}")
            if question.sources:
                lines.append(f"   依据 {'、'.join(question.sources)}")
        return "\n".join(lines) + "\n（只读：回答请交给用户，落盘用 add_record 或 pkbrain talk。）"

    # ---- 写入工具 -----------------------------------------------------

    def add_record(
        self,
        text: str,
        day: str | None = None,
        record_type: str = "R1",
        privacy: str | None = None,
        tags: list[str] | None = None,
    ) -> str:
        if not self.config.mcp.allow_write:
            return "写入被关掉了：config.toml 里 [mcp] allow_write = false。检索与统计仍可用。"
        try:
            target = Date.fromisoformat(self._day(day, "day") or Date.today().isoformat())
        except ValueError as exc:
            return f"参数不对：{exc}"
        try:
            record, extraction = pipeline.build_record(
                text,
                day=target,
                schema=self.schema,
                channel="chat",
                privacy=privacy,
                source="mcp",
                tags=list(tags or []),
                record_type=record_type,
            )
        except ValueError as exc:
            return f"没写成：{exc}"

        with self._open() as database:
            path = pipeline.write_snapshot(
                record, schema=self.schema, data_dir=self.data_dir, database=database
            )

        dims = ", ".join(record.dims) or "无"
        metrics = ", ".join(f"{k}={v:g}" for k, v in sorted(record.metrics.items())) or "无"
        lines = [
            f"写入 {record.id}",
            f"日期 {record.date}  类型 {record.type}  通道 {record.channel}  隐私 {record.privacy}",
            f"维度 {dims}",
            f"指标 {metrics}",
            f"文件 {path}",
        ]
        for warning in extraction.warnings:
            lines.append(f"警告 {warning}")
        return "\n".join(lines)


def _is_day(key: str) -> bool:
    return len(key) == 10 and key[4] == "-"


def _pretty_day(record_id: str) -> str:
    head = record_id[:8]
    return f"{head[:4]}-{head[4:6]}-{head[6:8]}"


def _line(hit: Hit, terms: list[str]) -> str:
    dims = ",".join(hit.dims) or "-"
    tags = f"  #{' #'.join(hit.tags)}" if hit.tags else ""
    return (
        f"{hit.date}  {hit.id}  [{dims}]  {hit.privacy}  置信度 {hit.confidence}{tags}\n"
        f"    {hit.excerpt(terms)}"
    )


def build_server(
    data_dir: Path, schema: PkbsSubset, config: Config | None = None, *, version: str = __version__
) -> MCPServer:
    """把上面这些工具挂到一台 MCP server 上。"""
    brain = Brain(data_dir, schema, config)
    server = MCPServer(
        name="pkbrain",
        title="PKBrain",
        version=version,
        instructions=INSTRUCTIONS,
    )
    for name, description in TOOLS:
        server.add_tool(getattr(brain, name), name=name, description=description)
    return server


def run(
    data_dir: Path,
    schema: PkbsSubset,
    config: Config | None = None,
    *,
    transport: str = "stdio",
    host: str = "127.0.0.1",
    port: int = 8765,
) -> None:
    """跑起来，直到客户端断开。stdio 下 stdout 归协议，别往里写别的东西。"""
    server = build_server(data_dir, schema, config)
    if transport == "stdio":
        server.run("stdio")
        return
    if transport in {"http", "streamable-http"}:
        server.run("streamable-http", host=host, port=port)
        return
    raise ValueError(f"不认识的 transport：{transport}（可用 stdio 或 http）")


def client_config(data_dir: Path, *, command: str = "pkbrain") -> str:
    """一份可以直接贴进 MCP 客户端配置的 JSON。"""
    return json.dumps(
        {
            "mcpServers": {
                "pkbrain": {
                    "command": command,
                    "args": ["mcp", "--data-dir", str(Path(data_dir).expanduser())],
                }
            }
        },
        ensure_ascii=False,
        indent=2,
    )
