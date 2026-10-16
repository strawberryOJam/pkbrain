# PKBrain

开源、本地优先、Build in Public 的**个人知识库大脑**。

把每天的生活与内心按「人的维度」记下来，沉淀成一份会思考的数字自我，让任何 AI 都能基于它与你对话。

> 现状：**M0 开发中**。现在能用 CLI 手动生成一条 R1 每日快照，并在本地检索到它。
> 其余能力按 [ROADMAP](docs/ROADMAP.md) 推进。

## 与 PKBS 的关系

PKBrain 是《个人知识库标准与规范（PKBS-1.0）》的软件实现。

- **PKBS** 回答「记录什么」——记录类型、维度、隐私分级、统一 frontmatter。
- **PKBrain** 回答「怎么自动记录、怎么让知识库变聪明」——四层采集、每日流水线、个性化回环。

PKBS-1.0 正文尚未并入本仓库。M0 先落一版[最小子集](docs/PKBS-MIN.md)（[ADR-0002](docs/ADR/0002-最小-PKBS-子集.md)），等正文到手后按 ADR 替换。

## 架构

```
collectors → brain → store → server
   采集        抽取     落盘     对外
```

| 模块 | 职责 | M0 状态 |
|---|---|---|
| `collectors/` | 四层采集：手动、对话、录音、设备、天气 | 只有 `manual` |
| `brain/` | 抽取、快照组装、调度（后续） | `extractor` + `pipeline` |
| `store/` | Markdown 与 SQLite 双写、检索 | 已完成 |
| `memory/` | 只增记忆、实体链接 | 空壳，M2 |
| `server/` | MCP 与 REST 对外 | 空壳，M2 |
| `ui/` | 回顾面板 | 未开始，M3 |

## 快速开始

```sh
uv sync

# 1. 初始化数据目录（默认 ~/.pkbrain）
uv run pkbrain init

# 2. 把一份输入落成 R1 每日快照
uv run pkbrain snapshot --from-file examples/today.md

# 3. 检索
uv run pkbrain search 睡眠
```

数据落在 `~/.pkbrain/`：

```
~/.pkbrain/
  records/2026/10/2026-10-16-R1-<短 id>.md   # 人可读的正文与 frontmatter
  pkbrain.db                                  # 程序可查的 SQLite + FTS5
```

换目录用 `--data-dir` 或环境变量 `PKBRAIN_HOME`。

## 输入格式

`snapshot` 接受 Markdown。用 `## <维度>` 分节，维度按 `schema/pkbs.yaml` 的编码或中文名匹配。

```markdown
# 2026-10-16 晚间快照

## D1 身体
睡了 6.5 小时，质量一般。没运动。

## 情绪
今天有点焦虑，客户的事悬着。
```

落在维度标题下的正文原样保留。指标（睡眠时长、体重、心情等）按 `schema/metrics.csv` 的正则抽取成结构化字段。抽不到的正文不会丢。

## 常用命令

```sh
pkbrain snapshot --from-file today.md --date 2026-10-16 --privacy P1 --tag 晚间
pkbrain search "睡眠" --dim D1 --since 2026-10-01 --limit 10
pkbrain show 2026-10-16
pkbrain stats
pkbrain schema export        # 由 pydantic 模型重新生成 schema/record.json
```

## 开发

```sh
uv run pytest
uv run pkbrain --help
```

## 不做什么

- 不托管你的数据：没有服务端，没有账号，没有同步。
- 不做通用笔记应用：不管知识管理，只管「记录人」。
- 不绑定模型：抽取与提问所用模型可插拔，本地 Ollama 与云端 API 都走同一条接口。

## 许可

Apache-2.0（[ADR-0003](docs/ADR/0003-开源协议.md)，待社区确认）。
