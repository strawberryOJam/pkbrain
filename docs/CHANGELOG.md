# CHANGELOG

按 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 组织，版本号跟随里程碑。

## [未发布]

### 新增

- `pkbrain mcp`：把大脑接到 MCP 上，客户端任意（Claude Desktop、Cursor、Codex、自己写的 agent）。
  stdio 与 streamable-http 两种传输，八个工具：`brain_schema`、`brain_stats`、`search_records`、
  `get_record`、`metric_series`、`list_goals`、`todays_questions`、`add_record`。
  只有最后一个是写入，`[mcp] allow_write = false` 可关。见 [ADR-0006](ADR/0006-mcp-接入与通知的去处.md)。
- `pkbrain mcp --print-config`：打印一份可直接贴进客户端的 JSON 配置。
- 通知的去处变成配置：`[notify] backend = auto | macos | linux | command | stdout | none`，
  `command` 是任意 shell 命令（hook），`{title}` / `{message}` 与
  `PKBRAIN_TITLE` / `PKBRAIN_MESSAGE` 都能用。不再只有 macOS。
- `pkbrain notify "文本"`：按配置发一条通知，自查 hook 通不通。
- `LICENSE`：Apache-2.0 全文。决策点 D2 拍板。
- `docs/DECISIONS.md`：D1–D8 的拍板结果、按建议先走的项，以及公开前清单。
- `pkbrain demo seed`：生成连续 N 天的演示快照，每天覆盖全部维度，指标落在 schema 区间内。
  固定随机种子；记录带 `tags: [演示数据]` 与 `source: seed_demo`；目标目录已有记录时默认拒绝写入。

### 变更

- `brain/scheduler.py` 的通知改为委托 `pkbrain.notify`：去处由配置决定，发不出去不再算失败。
- `pkbrain stats` 与 MCP 的 `brain_stats` 共用一个渲染函数（`brain.report.describe`），口径只有一处。
- `pyproject.toml` 标注 SPDX `license = "Apache-2.0"` 并把 `LICENSE` 打进包
  （wheel 里是 `License-Expression: Apache-2.0` 与 `License-File: LICENSE`）。
- ADR-0003 从「提议」改为「已采纳」。
- README 的许可一节改为指向 `LICENSE`。
- 测试从 143 项加到 190 项，其中一项真把 `pkbrain mcp` 拉起来，用官方 MCP 客户端的 stdio
  传输走一遍握手与工具调用。

## [0.2.0] - 2026-10-16

M1：每晚按记忆提问，回答即成当日快照。

### 新增

- `pkbrain talk`：今晚的会话。提问引擎按记忆挑问题，逐题问，回答组装成当天的 R1 快照。
- `pkbrain plan`：只打印今晚会问什么，不动状态、不写记录。
- `pkbrain serve`：APScheduler 进程内定时，每晚到点把问题备好并提醒（macOS 通知）。
- `pkbrain goals show|add`：目标清单 `goals.md`，供提问引擎追问进度。
- `pkbrain config init|show`：`config.toml`，含模型与定时设置。密钥只从环境变量读，不落盘。
- 提问引擎（`brain/questions.py`）：四级优先级——悬而未决项、维度缺口、目标、精神层反思、回顾旧记忆，
  带轮换状态 `state.json`。策略见 ADR-0005。
- 模型层（`brain/llm.py`）：`template`（默认，离线）与 `openai`（Ollama / DeepSeek / OpenAI 兼容），
  失败一律回退模板话术。见 ADR-0004。
- 会话转写：`sessions/日期-短id.md`，留问题、回答与依据。
- `pkbrain stats` 加快照完整率与连续天数，即 M1 的验收指标。
- `pkbrain talk --date`：补录过去的某一天。
- 测试从 44 项加到 132 项，含一个本地桩服务器验证 OpenAI 兼容客户端的真实请求。

### 变更

- schema 升到 `0.2.0-min`：新增 `questions` 段（探问句、触发词、反思池、会话配额）与数据目录路径。
- `schema/pkbs.yaml` 的触发词收紧，去掉「要」「想」「等」，减少把情绪描述误当待办。
- `goals.md` 模板里的例子改成注释，避免新用户被问到自己没写过的目标。

### 已知限制

- **M1 的验收还没完成**：要连续 14 天对话且完整率 ≥ 90%。功能齐了，天数是跑出来的。
- 抽取仍是规则，模型只参与措辞。「回顾旧记忆」走日期窗口与全文索引，还没有语义召回。
- 没有 `reindex` 命令，SQLite 仍不能由 Markdown 重建（见 ADR-0001）。
- 通知只在 macOS 走 `osascript`，其他平台打到标准输出。

### 决策

- ADR-0004：模型可插拔，默认离线模板。
- ADR-0005：优先级 1 最多两问，反思到期时插在目标之前。

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
