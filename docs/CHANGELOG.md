# CHANGELOG

按 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 组织，版本号跟随里程碑。

## [0.1.0] - 2026-10-16

M0：骨架与手动闭环。

### 新增

- CLI：`pkbrain init` / `snapshot` / `search` / `show` / `stats` / `schema show` / `schema export`。
- 流水线：输入文本 → 规则抽取（维度分节 + 指标正则）→ R1 记录 → Markdown 与 SQLite 双写。
- 存储：`records/<年>/<月>/<日期>-<类型>-<短 id>.md` 正本；`pkbrain.db` 元信息表、指标表、FTS5 全文索引。
- 中文全文检索：入库前按字符切分 CJK，查询时还原成短语，绕开 unicode61 不切中文的问题。
- `schema/`：`pkbs.yaml`（维度与通道）、`metrics.csv`（8 个指标与抽取正则）、`record.json`（由数据模型生成）。
- 文档：README、VISION、ROADMAP、PKBS 最小子集、3 份 ADR。
- 测试 43 项：抽取、模型、切分、schema 自洽、存储与检索、CLI 端到端。

### 已知限制

- 抽取器是规则的，不认识正则之外的写法。LLM 抽取器在 M2。
- 没有 `reindex` 命令，SQLite 暂时不能由 Markdown 重建（见 ADR-0001 的代价一节）。
- `entities` 恒为空，记忆层是空壳。
- P2 只打标，不加密。
- 采集只有 `manual` 通道。

### 决策

- ADR-0001：Markdown 正本 + SQLite 索引。
- ADR-0002：先用最小 PKBS 子集，等 PKBS-1.0 正文替换。
- ADR-0003：提议 Apache-2.0，待确认。
