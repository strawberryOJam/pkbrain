# PKBS 最小子集（v0.2.0-min）

> **这不是 PKBS-1.0 的官方定义。**
> 它是为了让 M0 能开工而定下的临时子集，字段名与编码沿用 PKBS 的命名习惯。PKBS-1.0 正文到手后，按 [ADR-0002](ADR/0002-最小-PKBS-子集.md) 整体替换 `schema/`。
>
> 机器可读版本是 `schema/pkbs.yaml`、`schema/metrics.csv` 和 `schema/record.json`。本文件解释它们。

## 1. 记录类型

M0 只定义 2 种，够「手动输入 → 快照」这条闭环用。

| 编码 | 名称 | 时间粒度 | 说明 |
|---|---|---|---|
| R1 | 每日快照 | 一天一条 | 一天的自我记录汇总 |
| R2 | 即时记录 | 一条一事 | 想到就记的念头、事件 |

R3–R7 留空，等 PKBS-1.0 定义。

## 2. 维度

7 维 + 基线 + 2 贯穿维是 PKBS 的框架。M0 先落地 4 个维度。

| 编码 | 名称 | 类型 | M0 是否落地 |
|---|---|---|---|
| D0 | 基线 | 基线 | 是（记录自身的元信息） |
| D1 | 身体 | 维度 | 是 |
| D2 | 情绪 | 维度 | 是 |
| D3 | 事业 | 维度 | 是 |
| D4 | 关系 | 维度 | 是 |
| D5–D7 | 待定 | 维度 | 否 |
| X1 | 时间 | 贯穿 | 否（用 frontmatter 的 `ts` / `date` 近似） |
| X2 | 目标 | 贯穿 | 否 |

输入文件里写 `## D1 身体` 或 `## 身体` 都能识别，匹配规则见 `pkbs.yaml` 的 `dimensions`。

## 3. 隐私分级

| 编码 | 名称 | 规则 |
|---|---|---|
| P0 | 公开 | 可同步、可分享 |
| P1 | 私密 | 仅本地明文，默认值 |
| P2 | 敏感 | 仅本地，v0.2 起静态加密 |

M0 只打标，不加密。P3/P4 留给 PKBS-1.0。

## 4. 采集通道

`channel` 取值：`manual`、`chat`、`audio`、`device`、`weather`。M0 只有 `manual` 会真的写入。

## 5. 统一 frontmatter

每条记录一份，字段顺序固定：

```yaml
id: 20261016-R1-a1b2c3
type: R1
ts: 2026-10-16T21:30:00+08:00
date: 2026-10-16
dims: [D1, D2]
source: examples/today.md
confidence: 0.7
privacy: P1
version: 0.2.0-min
entities: []
tags: [晚间]
channel: manual
agent_id:
model:
prompt_used:
tokens:
```

载荷不写进 frontmatter，落在正文里，用 `## <维度>` 分节。抽不出指标的正文进 `## 自由记录`，一个字都不丢。

| 字段 | 说明 |
|---|---|
| `id` | `<YYYYMMDD>-<类型>-<6 位短 id>`，全局唯一 |
| `ts` | 记录生成时间，带时区 |
| `date` | 归属日期，检索按它过滤 |
| `dims` | 本记录覆盖的维度编码，升序 |
| `confidence` | 0–1，抽取可信度，规则见下 |
| `version` | 记录所依据的 schema 版本 |
| `entities` | 涉及的实体，M0 留空 |
| `channel` | 采集通道 |
| `agent_id` / `model` / `prompt_used` / `tokens` | 生成该记录的 Agent 会话、模型、模板版本与消耗。M0 手动路径全为空 |

## 6. 指标字典

`schema/metrics.csv` 是指标的唯一事实来源，同时被两处使用：

- `brain/extractor.py` 按 `pattern` 列从正文抽数；
- `store/markdown.py` 按 `unit` 列渲染指标表。

列：

| 列 | 说明 |
|---|---|
| `name` | 指标名，snake_case，记录内唯一 |
| `dim` | 所属维度 |
| `unit` | 单位 |
| `type` | `int` 或 `float` |
| `min` / `max` | 合理区间，越界的值丢弃并记一条 warning |
| `pattern` | 抽取正则，必须有且只有一个 `(?P<value>...)` 命名组 |
| `description` | 中文说明 |

## 7. confidence 规则（M0）

规则抽取器没有模型自评，用固定公式：

```
confidence = min(0.5 + 0.1 × 抽到的指标数, 0.95)
```

正文分节但一个指标都没抽到时为 0.5，全靠自由记录时为 0.4。M2 接 LLM 抽取后改为模型自评。

## 8. 提问话术（v0.2.0-min 新增）

提问引擎的话术也放在 `pkbs.yaml` 的 `questions` 段，改数据就改了每晚被问什么：

| 键 | 用途 |
|---|---|
| `probes` | 每个维度的探问句，昨日缺口（优先级 1）用它补问 |
| `open_markers` | 悬而未决项的触发词，句子里命中就追问进展 |
| `reflections` | 精神层反思轮换池（优先级 3），答案进自由记录 |
| `revisit_days` | 回顾旧记忆（优先级 4）的回看天数 |
| `session.max_questions` | 一场会话最多几条 |
| `session.min_answers` | 少于几条就拒绝落记录 |

优先级与插队规则见 [ADR-0005](ADR/0005-提问引擎的优先级.md)。

## 9. 数据目录布局

| 文件 | 内容 |
|---|---|
| `records/年/月/日期-类型-短id.md` | 记录正本 |
| `sessions/日期-短id.md` | 会话转写（问题、回答、依据） |
| `sessions/日期-pending.json` | `serve` 备好但还没答的问题 |
| `goals.md` | 目标清单（贯穿维 X2） |
| `state.json` | 提问引擎的轮换状态 |
| `config.toml` | 模型与定时设置 |
| `pkbrain.db` | 索引，可由正本重建（重建命令待补） |

