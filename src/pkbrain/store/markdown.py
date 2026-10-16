"""Markdown 正本的读写：frontmatter + 正文。"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from ..models import Record
from ..schema import PkbsSubset

_BARE_RE = re.compile(r"^[A-Za-z0-9_./+\-\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+$")


def record_path(data_dir: Path, record: Record) -> Path:
    short = record.id.rsplit("-", 1)[-1]
    return (
        Path(data_dir) / "records" / f"{record.date:%Y}" / f"{record.date:%m}" / f"{record.date}-{record.type}-{short}.md"
    )


# ---- frontmatter -------------------------------------------------------


def _scalar(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if _BARE_RE.match(text) and text == text.strip():
        return text
    return json.dumps(text, ensure_ascii=False)


def _sequence(values: list[object]) -> str:
    return "[" + ", ".join(_scalar(v) for v in values) + "]"


def frontmatter(record: Record) -> str:
    lines = ["---"]
    for name, value in record.frontmatter().items():
        if isinstance(value, list):
            rendered = _sequence(value)
        elif hasattr(value, "isoformat"):  # date / datetime
            rendered = _scalar(value.isoformat())
        else:
            rendered = _scalar(value)
        lines.append(f"{name}: {rendered}".rstrip())
    lines.append("---")
    return "\n".join(lines)


def read_frontmatter(text: str) -> tuple[dict, str]:
    """拆出 frontmatter 与正文。没有 frontmatter 时返回 ({}, 原文)。"""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    return yaml.safe_load(parts[1]) or {}, parts[2].lstrip("\n")


def load_frontmatter(path: Path) -> Record:
    """按 frontmatter 重建记录。载荷（sections/metrics）在正文里，不回读。"""
    fm, _ = read_frontmatter(Path(path).read_text(encoding="utf-8"))
    if not fm:
        raise ValueError(f"{path} 没有 frontmatter")
    return Record(**fm)


# ---- 渲染 --------------------------------------------------------------


def render(record: Record, schema: PkbsSubset) -> str:
    type_name = schema.record_types.get(record.type, {}).get("name", record.type)
    blocks = [frontmatter(record), "", f"# {record.date} {type_name}", ""]

    for code in record.dims:
        dim = schema.dimensions.get(code)
        label = f"{code} {dim.name}" if dim else code
        blocks += [f"## {label}", "", record.sections.get(code, "").strip(), ""]

    if record.free_text.strip():
        blocks += ["## 自由记录", "", record.free_text.strip(), ""]

    if record.metrics:
        blocks += ["## 指标", "", "| 指标 | 值 | 单位 |", "| --- | --- | --- |"]
        for name, value in sorted(record.metrics.items()):
            metric = schema.metrics.get(name)
            unit = metric.unit if metric else ""
            blocks.append(f"| {name} | {value:g} | {unit} |")
        blocks.append("")

    return "\n".join(blocks).rstrip() + "\n"


def write(path: Path, content: str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path
