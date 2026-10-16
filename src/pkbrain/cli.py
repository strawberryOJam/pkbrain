"""命令行入口。

    pkbrain init
    pkbrain snapshot --from-file today.md
    pkbrain search 睡眠
"""

from __future__ import annotations

import json
import os
from datetime import date as Date
from pathlib import Path

import typer

from . import __version__, store
from .brain import pipeline
from .collectors import manual
from .schema import load_schema

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="PKBrain —— 开源、本地优先的个人知识库大脑（M0）。",
)

DATA_DIR_OPTION = typer.Option(
    None, "--data-dir", help="数据目录，默认 ~/.pkbrain 或环境变量 PKBRAIN_HOME。", show_default=False
)


def _data_dir(value: Path | None) -> Path:
    if value is not None:
        return Path(value).expanduser()
    env = os.environ.get("PKBRAIN_HOME")
    return Path(env).expanduser() if env else Path.home() / ".pkbrain"


@app.command()
def version() -> None:
    """显示版本与当前 schema 目录。"""
    schema = load_schema()
    typer.echo(f"pkbrain {__version__}")
    typer.echo(f"schema {schema.version}（{schema.status}）来自 {schema.source_dir}")


@app.command()
def init(data_dir: Path = DATA_DIR_OPTION) -> None:
    """建数据目录与数据库。可重复执行。"""
    directory = _data_dir(data_dir)
    schema = load_schema()
    (directory / schema.paths["records"]).mkdir(parents=True, exist_ok=True)
    database = store.sqlite.db_path(directory, schema)
    with store.sqlite.Store(database, schema):
        pass
    typer.echo(f"数据目录 {directory}")
    typer.echo(f"数据库   {database}")


@app.command()
def snapshot(
    from_file: Path = typer.Option(
        ..., "--from-file", "-f", exists=True, dir_okay=False, readable=True, help="输入文件，Markdown 或纯文本。"
    ),
    day: str = typer.Option(None, "--date", "-d", help="归属日期 YYYY-MM-DD，默认今天。"),
    kind: str = typer.Option("R1", "--type", "-t", help="记录类型 R1 或 R2。"),
    channel: str = typer.Option("manual", "--channel", help="采集通道。"),
    privacy: str = typer.Option(None, "--privacy", "-p", help="隐私分级 P0/P1/P2，默认取 schema 的默认值。"),
    tag: list[str] = typer.Option(None, "--tag", help="标签，可重复。"),
    as_json: bool = typer.Option(False, "--json", help="同时输出记录 JSON。"),
    data_dir: Path = DATA_DIR_OPTION,
) -> None:
    """把一份输入落成一条记录，写 Markdown 与 SQLite。"""
    directory = _data_dir(data_dir)
    schema = load_schema()
    target = Date.fromisoformat(day) if day else Date.today()

    text = manual.collect(from_file)
    try:
        record, extraction = pipeline.build_record(
            text,
            day=target,
            schema=schema,
            channel=channel,
            privacy=privacy,
            source=str(from_file),
            tags=list(tag or []),
            record_type=kind,
        )
    except ValueError as exc:
        typer.echo(f"没写成：{exc}", err=True)
        raise typer.Exit(code=1) from exc

    path = pipeline.write_snapshot(record, schema=schema, data_dir=directory)
    for warning in extraction.warnings:
        typer.echo(f"警告：{warning}", err=True)

    dims = ", ".join(record.dims) or "无"
    metrics = ", ".join(f"{k}={v:g}" for k, v in sorted(record.metrics.items())) or "无"
    typer.echo(f"记录   {record.id}")
    typer.echo(f"维度   {dims}")
    typer.echo(f"指标   {metrics}")
    typer.echo(f"置信度 {record.confidence}")
    typer.echo(f"写入   {path}")
    if as_json:
        typer.echo(record.model_dump_json(indent=2))


@app.command()
def search(
    query: str = typer.Argument(None, help="检索词。留空则按过滤条件列出最近记录。"),
    dim: str = typer.Option(None, "--dim", help="只看某个维度，如 D1。"),
    since: str = typer.Option(None, "--since", help="起始日期 YYYY-MM-DD。"),
    until: str = typer.Option(None, "--until", help="结束日期 YYYY-MM-DD。"),
    privacy: str = typer.Option(None, "--privacy", help="只看某个隐私分级。"),
    limit: int = typer.Option(10, "--limit", "-n", help="最多返回几条。"),
    as_json: bool = typer.Option(False, "--json", help="输出 JSON。"),
    data_dir: Path = DATA_DIR_OPTION,
) -> None:
    """在本地全文索引里检索。"""
    directory = _data_dir(data_dir)
    schema = load_schema()
    with store.sqlite.Store(store.sqlite.db_path(directory, schema), schema) as database:
        hits = database.search(
            query, dim=dim, since=since, until=until, privacy=privacy, limit=limit
        )

    if as_json:
        typer.echo(
            json.dumps(
                [
                    {**hit.__dict__, "excerpt": hit.excerpt(query.split() if query else [])}
                    for hit in hits
                ],
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    if not hits:
        typer.echo("没有匹配的记录。")
        return

    terms = query.split() if query else []
    for hit in hits:
        dims = ",".join(hit.dims) or "-"
        typer.echo(f"{hit.date}  {hit.id}  [{dims}]  {hit.privacy}  置信度 {hit.confidence}")
        typer.echo(f"    {hit.excerpt(terms)}")
    typer.echo(f"共 {len(hits)} 条。")


@app.command()
def show(
    key: str = typer.Argument(..., help="日期 YYYY-MM-DD 或记录 id。"),
    data_dir: Path = DATA_DIR_OPTION,
) -> None:
    """打印一条记录的 Markdown 原文。"""
    directory = _data_dir(data_dir)
    schema = load_schema()
    with store.sqlite.Store(store.sqlite.db_path(directory, schema), schema) as database:
        hits = database.by_date(key) if len(key) == 10 and key[4] == "-" else []
        if not hits:
            single = database.by_id(key)
            hits = [single] if single else []

    if not hits:
        typer.echo(f"没找到 {key}", err=True)
        raise typer.Exit(code=1)
    for hit in hits:
        typer.echo(Path(hit.path).read_text(encoding="utf-8"))
        typer.echo("-" * 40)


@app.command()
def stats(data_dir: Path = DATA_DIR_OPTION) -> None:
    """看数据目录的概况。"""
    directory = _data_dir(data_dir)
    schema = load_schema()
    with store.sqlite.Store(store.sqlite.db_path(directory, schema), schema) as database:
        info = database.stats()

    if not info["records"]:
        typer.echo("还没有记录。先跑 pkbrain snapshot --from-file <文件>。")
        return
    typer.echo(f"记录 {info['records']} 条，覆盖 {info['days']} 天（{info['first']} → {info['last']}）")
    channels = "，".join(f"{k} {v}" for k, v in info["channels"].items())
    typer.echo(f"通道 {channels}")
    if info["metrics"]:
        metrics = "，".join(f"{k} {v}" for k, v in info["metrics"].items())
        typer.echo(f"指标 {metrics}")
    else:
        typer.echo("指标 无")


schema_app = typer.Typer(no_args_is_help=True, help="查看与导出 schema。")
app.add_typer(schema_app, name="schema")


@schema_app.command("show")
def schema_show() -> None:
    """打印维度与指标字典。"""
    schema = load_schema()
    typer.echo(f"schema {schema.version}（{schema.status}），标准 {schema.standard}")
    for code, dim in schema.dimensions.items():
        metrics = "，".join(f"{m.name}({m.unit})" for m in schema.metrics_of(code))
        typer.echo(f"  {code:<3} {dim.name:<6} {dim.kind:<10} {metrics}")
    typer.echo(f"隐私 {', '.join(schema.privacy)}，通道 {', '.join(schema.channels)}")


@schema_app.command("export")
def schema_export(
    out: Path = typer.Option(
        None, "--out", help="输出路径，默认写回 schema/record.json。", show_default=False
    )
) -> None:
    """由数据模型重新生成 record.json。"""
    target = Path(out) if out else load_schema().source_dir / "record.json"
    store.markdown.write(target, store.record_json.dumps())
    typer.echo(f"写入 {target}")


if __name__ == "__main__":  # pragma: no cover
    app()
