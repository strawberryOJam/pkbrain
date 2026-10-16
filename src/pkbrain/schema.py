"""读取 schema/ 下的机器可读定义。

schema/ 是唯一事实来源，仓库里一份，打包时再随包带一份（见 pyproject 的 force-include）。
"""

from __future__ import annotations

import csv
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Dimension:
    code: str
    name: str
    kind: str  # baseline | dimension | cross


@dataclass(frozen=True)
class MetricDef:
    name: str
    dim: str
    unit: str
    type: str  # int | float
    min: float | None
    max: float | None
    pattern: str
    description: str

    def regex(self) -> re.Pattern[str]:
        return _compile(self.pattern)

    def coerce(self, raw: str) -> float:
        return int(round(float(raw))) if self.type == "int" else float(raw)


@dataclass(frozen=True)
class PkbsSubset:
    version: str
    standard: str
    status: str
    dimensions: dict[str, Dimension]
    metrics: dict[str, MetricDef]
    record_types: dict[str, dict]
    privacy: dict[str, dict]
    channels: list[str]
    free_headings: list[str]
    default_privacy: str
    confidence: dict[str, float]
    paths: dict[str, str]
    source_dir: Path

    # ---- 查询 ---------------------------------------------------------

    def dimension_of(self, heading: str) -> Dimension | None:
        """把标题文本匹配成维度：接受 `D1`、`D1 身体`、`身体`。"""
        text = heading.strip()
        token = text.split()[0].rstrip("：:") if text.split() else ""
        candidates = [token.upper(), text.upper()]
        for code, dim in self.dimensions.items():
            if code in candidates or dim.name in candidates:
                return dim
        return None

    def metrics_of(self, dim: str) -> list[MetricDef]:
        return [m for m in self.metrics.values() if m.dim == dim]

    def dim_codes(self) -> list[str]:
        return list(self.dimensions)


@lru_cache(maxsize=8)
def _compile(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern)


@lru_cache(maxsize=4)
def schema_dir() -> Path:
    """定位 schema 目录：环境变量 → 仓库检出 → 已安装的包 → 当前目录。"""
    env = os.environ.get("PKBRAIN_SCHEMA")
    if env:
        p = Path(env).expanduser()
        p = p if p.is_dir() else p.parent
        if (p / "pkbs.yaml").is_file():
            return p
        raise FileNotFoundError(f"PKBRAIN_SCHEMA 指向的目录里没有 pkbs.yaml：{p}")

    candidates: list[Path] = [parent / "schema" for parent in Path(__file__).resolve().parents]
    try:  # 已安装的 wheel
        from importlib import resources

        candidates.append(Path(str(resources.files("pkbrain") / "schema")))
    except Exception:  # pragma: no cover - 仅在异常打包下发生
        pass
    candidates.append(Path.cwd() / "schema")

    for cand in candidates:
        if (cand / "pkbs.yaml").is_file():
            return cand
    raise FileNotFoundError("找不到 schema/pkbs.yaml，请设置 PKBRAIN_SCHEMA")


def load_metrics(path: Path) -> dict[str, MetricDef]:
    metrics: dict[str, MetricDef] = {}
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            name = row["name"].strip()
            if name in metrics:
                raise ValueError(f"metrics.csv 里指标名重复：{name}")
            pattern = row["pattern"]
            if pattern.count("(?P<value>") != 1:
                raise ValueError(f"指标 {name} 的 pattern 必须有且只有一个 (?P<value>...) 命名组")
            _compile(pattern)
            metrics[name] = MetricDef(
                name=name,
                dim=row["dim"].strip(),
                unit=row["unit"].strip(),
                type=row["type"].strip(),
                min=_opt_float(row.get("min")),
                max=_opt_float(row.get("max")),
                pattern=pattern,
                description=(row.get("description") or "").strip(),
            )
    return metrics


def _opt_float(raw: str | None) -> float | None:
    if raw is None or not str(raw).strip():
        return None
    return float(raw)


@lru_cache(maxsize=4)
def load_schema(path: Path | None = None) -> PkbsSubset:
    """读入 pkbs.yaml 与 metrics.csv。"""
    directory = Path(path).expanduser().resolve() if path else schema_dir()
    data = yaml.safe_load((directory / "pkbs.yaml").read_text(encoding="utf-8"))
    metrics = load_metrics(directory / "metrics.csv")

    dimensions = {
        code: Dimension(code=code, name=spec["name"], kind=spec.get("kind", "dimension"))
        for code, spec in data["dimensions"].items()
    }
    for metric in metrics.values():
        if metric.dim not in dimensions:
            raise ValueError(f"指标 {metric.name} 指向未知维度 {metric.dim}")

    return PkbsSubset(
        version=data["version"],
        standard=data["standard"],
        status=data["status"],
        dimensions=dimensions,
        metrics=metrics,
        record_types=data["record_types"],
        privacy=data["privacy"],
        channels=list(data["channels"]),
        free_headings=list(data.get("free_headings", [])),
        default_privacy=data["default_privacy"],
        confidence={k: float(v) for k, v in data["confidence"].items()},
        paths=dict(data["paths"]),
        source_dir=directory,
    )
