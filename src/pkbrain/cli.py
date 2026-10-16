"""命令行入口。

    pkbrain init
    pkbrain talk                 # 今晚的会话
    pkbrain snapshot --from-file today.md
    pkbrain search 睡眠
    pkbrain serve                # 每晚定时提醒（可选）
"""

from __future__ import annotations

import json
import os
from datetime import date as Date
from pathlib import Path
from typing import Callable

import typer

from . import __version__, goals as goals_module, store
from .brain import pipeline, questions as questions_module, session
from .brain.llm import build_llm
from .brain.report import coverage
from .collectors import manual
from .config import Config, load_config, write_default_config
from .schema import PkbsSubset, load_schema
from .store.sqlite import Store

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="PKBrain —— 开源、本地优先的个人知识库大脑。",
)

DATA_DIR_OPTION = typer.Option(
    None, "--data-dir", help="数据目录，默认 ~/.pkbrain 或环境变量 PKBRAIN_HOME。", show_default=False
)


def _data_dir(value: Path | None) -> Path:
    if value is not None:
        return Path(value).expanduser()
    env = os.environ.get("PKBRAIN_HOME")
    return Path(env).expanduser() if env else Path.home() / ".pkbrain"


def _setup(data_dir: Path | None) -> tuple[Path, PkbsSubset, Config]:
    directory = _data_dir(data_dir)
    schema = load_schema()
    return directory, schema, load_config(directory, schema)


def _open(directory: Path, schema: PkbsSubset) -> Store:
    return Store(store.sqlite.db_path(directory, schema), schema)


# ---- 基础 ---------------------------------------------------------------


@app.command()
def version() -> None:
    """显示版本与当前 schema 目录。"""
    schema = load_schema()
    typer.echo(f"pkbrain {__version__}")
    typer.echo(f"schema {schema.version}（{schema.status}）来自 {schema.source_dir}")


@app.command()
def init(data_dir: Path = DATA_DIR_OPTION) -> None:
    """建数据目录、数据库、目标清单与配置文件。可重复执行，不覆盖已有文件。"""
    directory = _data_dir(data_dir)
    schema = load_schema()
    directory.mkdir(parents=True, exist_ok=True)
    (directory / schema.paths["records"]).mkdir(parents=True, exist_ok=True)
    (directory / schema.paths["sessions"]).mkdir(parents=True, exist_ok=True)
    with _open(directory, schema):
        pass
    goals_file = goals_module.write_default(directory, schema)
    config_file = write_default_config(directory, schema)

    typer.echo(f"数据目录 {directory}")
    typer.echo(f"数据库   {store.sqlite.db_path(directory, schema)}")
    typer.echo(f"目标     {goals_file}")
    typer.echo(f"配置     {config_file}")


# ---- 记录 ---------------------------------------------------------------


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
    directory, schema, _ = _setup(data_dir)
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
    _report_record(record, extraction, path)
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
    directory, schema, _ = _setup(data_dir)
    with _open(directory, schema) as database:
        hits = database.search(query, dim=dim, since=since, until=until, privacy=privacy, limit=limit)

    if as_json:
        typer.echo(
            json.dumps(
                [{**hit.__dict__, "excerpt": hit.excerpt(query.split() if query else [])} for hit in hits],
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
    directory, schema, _ = _setup(data_dir)
    with _open(directory, schema) as database:
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
def stats(
    target: float = typer.Option(0.9, "--target", help="完整率的达标线，M1 的验收标准是 0.9。"),
    data_dir: Path = DATA_DIR_OPTION,
) -> None:
    """看数据目录的概况，含 M1 的快照完整率。"""
    directory, schema, _ = _setup(data_dir)
    with _open(directory, schema) as database:
        info = database.stats()
        share = coverage(database.dates(), today=Date.today())

    if not info["records"]:
        typer.echo("还没有记录。先跑 pkbrain talk，或 pkbrain snapshot --from-file <文件>。")
        return

    typer.echo(f"记录 {info['records']} 条，覆盖 {info['days']} 天（{info['first']} → {info['last']}）")
    typer.echo(
        f"完整率 {share.rate:.1%}（{share.days_recorded}/{share.days_span} 天），"
        f"连续 {share.streak} 天，目标 {target:.0%} {'达标' if share.meets(target) else '未达标'}"
    )
    channels = "，".join(f"{k} {v}" for k, v in info["channels"].items())
    typer.echo(f"通道 {channels}")
    if info["metrics"]:
        metrics = "，".join(f"{k} {v}" for k, v in info["metrics"].items())
        typer.echo(f"指标 {metrics}")
    else:
        typer.echo("指标 无")


# ---- 每晚的会话 ---------------------------------------------------------


@app.command()
def plan(
    limit: int = typer.Option(None, "--limit", "-n", help="最多几条，默认取 schema 的 session 上限。"),
    as_json: bool = typer.Option(False, "--json", help="输出 JSON。"),
    data_dir: Path = DATA_DIR_OPTION,
) -> None:
    """只打印今晚会问什么，不动状态、不写记录。"""
    directory, schema, _ = _setup(data_dir)
    with _open(directory, schema) as database:
        engine = questions_module.QuestionEngine(
            schema, database, data_dir=directory, today=Date.today()
        )
        picked = engine.plan(limit)

    if as_json:
        typer.echo(json.dumps([vars(q) for q in picked], ensure_ascii=False, indent=2))
        return
    if not picked:
        typer.echo("今晚没有问题。")
        return
    for index, question in enumerate(picked, start=1):
        dim = f" → {question.dim}" if question.dim else ""
        typer.echo(f"{index}. [{question.kind}{dim}] {question.text}")
        if question.sources:
            typer.echo(f"     依据 {'、'.join(question.sources)}")


@app.command()
def talk(
    limit: int = typer.Option(None, "--limit", "-n", help="最多问几条。"),
    day: str = typer.Option(None, "--date", "-d", help="归属日期 YYYY-MM-DD，默认今天（补录用）。"),
    from_file: Path = typer.Option(
        None, "--answers-file", help="从文件逐行取答案，用于脚本化或测试。", show_default=False
    ),
    polish: bool = typer.Option(True, "--polish/--no-polish", help="让模型把问句改写得自然些。"),
    privacy: str = typer.Option(None, "--privacy", "-p", help="本次记录的隐私分级。"),
    data_dir: Path = DATA_DIR_OPTION,
) -> None:
    """今晚的会话：按记忆挑问题，你回答，落成当天的快照。"""
    directory, schema, config = _setup(data_dir)
    today = Date.fromisoformat(day) if day else Date.today()
    llm = build_llm(config)

    from .brain.scheduler import load_pending, pending_file

    pending_path = pending_file(directory, schema, today)
    with _open(directory, schema) as database:
        pending = load_pending(pending_path)
        if pending:
            typer.echo(f"用 {today} 已经备好的 {len(pending)} 个问题。")
            picked = pending
        else:
            engine = questions_module.QuestionEngine(
                schema, database, data_dir=directory, today=today
            )
            picked = engine.plan(limit)
            engine.commit(picked)

        if not picked:
            typer.echo("今晚没有问题。")
            return

        try:
            result = session.run_session(
                picked,
                schema=schema,
                data_dir=directory,
                store=database,
                day=today,
                llm=llm,
                ask=_asker(from_file),
                privacy=privacy,
                polish=polish,
            )
        except ValueError as exc:
            typer.echo(f"没写成：{exc}", err=True)
            raise typer.Exit(code=1) from exc

    if pending_path.is_file():
        pending_path.unlink()

    typer.echo()
    typer.echo(result.reply.text)
    _report_record(result.record, result.extraction, result.snapshot_path)
    typer.echo(f"转写   {result.transcript_path}")


@app.command()
def serve(
    now: bool = typer.Option(False, "--now", help="立刻推进一次，不进调度循环。"),
    data_dir: Path = DATA_DIR_OPTION,
) -> None:
    """每晚到点把问题备好并提醒你。Ctrl-C 退出。"""
    directory, schema, config = _setup(data_dir)
    from .brain import scheduler as scheduler_module

    if now:
        picked = scheduler_module.open_nightly(config, schema, directory)
        if not picked:
            typer.echo("今晚没有问题。")
            return
        for question in picked:
            typer.echo(f"[{question.kind}] {question.text}")
        return

    scheduler = scheduler_module.build_scheduler(config, schema, directory)
    typer.echo(f"每晚 {config.schedule.time} 开一场会话。Ctrl-C 退出。")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        typer.echo("停了。")


# ---- 目标 ---------------------------------------------------------------

goals_app = typer.Typer(no_args_is_help=True, help="目标清单（贯穿维 X2），提问引擎按它追问进度。")
app.add_typer(goals_app, name="goals")


@goals_app.command("show")
def goals_show(data_dir: Path = DATA_DIR_OPTION) -> None:
    """列出目标。"""
    directory, schema, _ = _setup(data_dir)
    path = directory / schema.paths["goals"]
    items = goals_module.load(directory, schema)
    if not items:
        typer.echo(f"还没有目标。写 {path}，或用 pkbrain goals add。")
        return
    typer.echo(f"{path}\n")
    for goal in items:
        mark = "x" if goal.done else " "
        due = f"（{goal.due}）" if goal.due else ""
        dim = f" #{goal.dim}" if goal.dim else ""
        typer.echo(f"[{mark}] {goal.text}{due}{dim}  第 {goal.line} 行")


@goals_app.command("add")
def goals_add(
    text: str = typer.Argument(..., help="目标内容。"),
    due: str = typer.Option(None, "--due", help="到期日 YYYY-MM-DD。"),
    dim: str = typer.Option(None, "--dim", help="归属维度，如 D3。"),
    data_dir: Path = DATA_DIR_OPTION,
) -> None:
    """追加一条目标。"""
    directory, schema, _ = _setup(data_dir)
    path = goals_module.write_default(directory, schema)
    line = f"- [ ] {text}"
    if due:
        Date.fromisoformat(due)  # 格式不对就报错
        line += f" ({due})"
    if dim:
        line += f" #{dim}"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    typer.echo(f"写入 {path}")


# ---- 配置 ---------------------------------------------------------------

config_app = typer.Typer(no_args_is_help=True, help="模型与定时设置。")
app.add_typer(config_app, name="config")


@config_app.command("init")
def config_init(
    force: bool = typer.Option(False, "--force", help="覆盖已有文件。"),
    data_dir: Path = DATA_DIR_OPTION,
) -> None:
    """写一份带注释的配置文件。"""
    directory, schema, _ = _setup(data_dir)
    path = write_default_config(directory, schema, force=force)
    typer.echo(f"写入 {path}")


@config_app.command("show")
def config_show(data_dir: Path = DATA_DIR_OPTION) -> None:
    """打印生效的配置。密钥只显示环境变量名，不显示值。"""
    directory, schema, config = _setup(data_dir)
    source = config.path or "（还没有配置文件，用的是默认值，跑 pkbrain config init 生成）"
    typer.echo(f"来自 {source}")
    typer.echo(f"llm.provider      {config.llm.provider}")
    typer.echo(f"llm.model         {config.llm.model or '（未设）'}")
    typer.echo(f"llm.base_url      {config.llm.base_url or '（未设）'}")
    typer.echo(f"llm.temperature   {config.llm.temperature}")
    typer.echo(f"llm.密钥          环境变量 {config.llm.api_key_env}：{'已设置' if config.llm.api_key else '未设置'}")
    typer.echo(f"schedule.time     {config.schedule.time}")
    typer.echo(f"schedule.notify   {config.schedule.notify}")


# ---- schema -------------------------------------------------------------

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


# ---- 内部 ---------------------------------------------------------------


def _report_record(record, extraction, path) -> None:
    dims = ", ".join(record.dims) or "无"
    metrics = ", ".join(f"{k}={v:g}" for k, v in sorted(record.metrics.items())) or "无"
    for warning in extraction.warnings:
        typer.echo(f"警告：{warning}", err=True)
    typer.echo(f"记录   {record.id}")
    typer.echo(f"维度   {dims}")
    typer.echo(f"指标   {metrics}")
    typer.echo(f"置信度 {record.confidence}")
    typer.echo(f"写入   {path}")


def _asker(from_file: Path | None) -> Callable[[str], str]:
    """交互读答案，或从文件逐行读。"""
    if from_file is None:

        def interactive(text: str) -> str:
            typer.echo()
            typer.echo(typer.style(f"? {text}", fg=typer.colors.CYAN))
            return typer.prompt(">", default="", show_default=False)

        return interactive

    lines = Path(from_file).read_text(encoding="utf-8").splitlines()
    queue = iter([line.rstrip() for line in lines])

    def scripted(text: str) -> str:
        typer.echo()
        typer.echo(typer.style(f"? {text}", fg=typer.colors.CYAN))
        answer = next(queue, "")
        typer.echo(f"> {answer}")
        return answer

    return scripted


if __name__ == "__main__":  # pragma: no cover
    app()
