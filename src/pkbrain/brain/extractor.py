"""抽取：把一段原始文本变成结构化的维度与指标。

M0 用规则抽取器：不需要模型，结果可预期。M2 再接入 LLM 抽取器，接口不变。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol

from ..schema import PkbsSubset

HEADING_RE = re.compile(r"^(#{1,6})\s*(.*?)\s*$")


@dataclass
class Extraction:
    """一次抽取的结果。"""

    sections: dict[str, str] = field(default_factory=dict)  # 维度编码 -> 正文
    free_text: str = ""  # 未归入维度的正文，原样保留
    metrics: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def dims(self) -> list[str]:
        return sorted(self.sections)

    def is_empty(self) -> bool:
        return not self.sections and not self.metrics and not self.free_text.strip()


class Extractor(Protocol):
    def extract(self, text: str) -> Extraction: ...


class RulesExtractor:
    """按 schema/metrics.csv 的正则抽指标，按 pkbs.yaml 的维度切分节。"""

    def __init__(self, schema: PkbsSubset) -> None:
        self.schema = schema

    def extract(self, text: str) -> Extraction:
        result = Extraction()
        self._split_sections(text, result)
        self._extract_metrics(text, result)
        return result

    # ---- 分节 ---------------------------------------------------------

    def _split_sections(self, text: str, result: Extraction) -> None:
        current: str | None = None
        buffers: dict[str | None, list[str]] = {}
        for line in text.splitlines():
            match = HEADING_RE.match(line)
            if match:
                level, heading = len(match.group(1)), match.group(2)
                if level == 1:  # 文档标题，不进正文
                    current = None
                    continue
                dim = self.schema.dimension_of(heading)
                if dim is not None:
                    current = dim.code
                    buffers.setdefault(current, [])
                    continue
                if heading.strip() in self.schema.free_headings:
                    current = None  # 自由记录，渲染时统一套一个标题
                    continue
                current = f"free:{heading}"
                buffers.setdefault(current, [])
                continue
            key = current
            buffers.setdefault(key, []).append(line)

        for key, lines in buffers.items():
            body = "\n".join(lines).strip()
            if not body:
                continue
            if key is None:
                result.free_text = body
            elif key.startswith("free:"):
                heading = key[5:]
                block = f"「{heading}」\n{body}"
                result.free_text = f"{result.free_text}\n\n{block}".strip()
            else:
                result.sections[key] = body

    # ---- 指标 ---------------------------------------------------------

    def _extract_metrics(self, text: str, result: Extraction) -> None:
        for name, metric in self.schema.metrics.items():
            matches = list(metric.regex().finditer(text))
            if not matches:
                continue
            if len(matches) > 1:
                result.warnings.append(f"{name} 在正文出现 {len(matches)} 次，取第一处")
            value = metric.coerce(matches[0].group("value"))
            if metric.min is not None and value < metric.min:
                result.warnings.append(f"{name}={value} 低于下限 {metric.min}，已丢弃")
                continue
            if metric.max is not None and value > metric.max:
                result.warnings.append(f"{name}={value} 高于上限 {metric.max}，已丢弃")
                continue
            result.metrics[name] = value
