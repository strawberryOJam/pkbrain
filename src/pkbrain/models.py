"""记录的数据模型。

这是结构的唯一事实来源：`schema/record.json` 由它生成，`store/` 与 `cli/` 都按它读写。
字段名沿用 PKBS 的统一 frontmatter 命名。
"""

from __future__ import annotations

import re
from datetime import date as Date
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

RecordType = str  # "R1" | "R2"，M0 只允许这两个
Privacy = str  # "P0" | "P1" | "P2"
Channel = str  # manual | chat | audio | device | weather

RECORD_ID_RE = re.compile(r"^\d{8}-R[1-7]-[0-9a-f]{6}$")
DIM_RE = re.compile(r"^[DX][0-9]$")
DIM_ORDER = {f"D{i}": i for i in range(10)} | {f"X{i}": 10 + i for i in range(10)}


class Record(BaseModel):
    """一条记录。

    `sections` 与 `metrics` 是载荷，落在正文里，不写进 frontmatter。
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    type: str = "R1"
    ts: datetime
    date: Date
    dims: list[str] = Field(default_factory=list)
    source: str = "manual"
    confidence: float = Field(default=0.4, ge=0.0, le=1.0)
    privacy: str = "P1"
    version: str = "0.1.0"
    entities: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    channel: str = "manual"
    agent_id: str | None = None
    model: str | None = None
    prompt_used: str | None = None
    tokens: int | None = None

    sections: dict[str, str] = Field(default_factory=dict)
    free_text: str = ""
    metrics: dict[str, float] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def _check_id(cls, v: str) -> str:
        if not RECORD_ID_RE.match(v):
            raise ValueError(f"id 必须是 <YYYYMMDD>-<R类型>-<6 位小写短 id>，收到 {v!r}")
        return v

    @field_validator("type")
    @classmethod
    def _check_type(cls, v: str) -> str:
        if v not in {"R1", "R2"}:
            raise ValueError(f"M0 只支持 R1 与 R2，收到 {v!r}")
        return v

    @field_validator("privacy")
    @classmethod
    def _check_privacy(cls, v: str) -> str:
        if v not in {"P0", "P1", "P2"}:
            raise ValueError(f"M0 只支持 P0/P1/P2，收到 {v!r}")
        return v

    @field_validator("channel")
    @classmethod
    def _check_channel(cls, v: str) -> str:
        if v not in {"manual", "chat", "audio", "device", "weather"}:
            raise ValueError(f"未知采集通道 {v!r}")
        return v

    @field_validator("dims")
    @classmethod
    def _check_dims(cls, v: list[str]) -> list[str]:
        for d in v:
            if not DIM_RE.match(d):
                raise ValueError(f"维度编码形如 D1 / X2，收到 {d!r}")
        return sorted(set(v), key=lambda d: DIM_ORDER.get(d, 99))

    # ---- 序列化 -------------------------------------------------------

    @classmethod
    def frontmatter_fields(cls) -> list[str]:
        """frontmatter 的字段顺序，即模型里除载荷外的字段顺序。"""
        return [n for n in cls.model_fields if n not in {"sections", "free_text", "metrics"}]

    def frontmatter(self) -> dict[str, object]:
        return {name: getattr(self, name) for name in self.frontmatter_fields()}

    def plain_text(self) -> str:
        """供全文检索的纯文本：维度正文 + 自由记录 + 指标名值。不含 frontmatter。"""
        parts = [self.sections[d] for d in sorted(self.sections, key=lambda d: DIM_ORDER.get(d, 99))]
        if self.free_text.strip():
            parts.append(self.free_text)
        if self.metrics:
            parts.append(" ".join(f"{k} {v}" for k, v in sorted(self.metrics.items())))
        return "\n".join(p for p in parts if p.strip())
