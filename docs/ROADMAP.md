# ROADMAP

里程碑的验收标准是**能不能观察到**，不是「写完了没有」。

## M0 — 骨架与手动闭环（✅ 已完成）

| 项 | 状态 |
|---|---|
| 仓库骨架、`pyproject.toml`、uv 可装可跑 | ✅ |
| `schema/`：`pkbs.yaml`、`metrics.csv`、`record.json` | ✅ |
| CLI：`init` / `snapshot` / `search` / `show` / `stats` / `schema` | ✅ |
| Markdown 正本 + SQLite 全文索引双写 | ✅ |
| `docs/`：VISION、ROADMAP、ADR、CHANGELOG | ✅ |
| 单元与端到端测试 | ✅ 43 项 |

**验收标准：** 用 CLI 手动生成一条 R1 快照并能检索到它。

```sh
uv run pkbrain snapshot --from-file examples/today.md
uv run pkbrain search 睡眠
```

## M1 — 定时对话（实现完成，验收进行中）

| 项 | 状态 |
|---|---|
| `brain/questions.py`：四级优先级的提问引擎 + 轮换状态 | ✅ |
| `brain/session.py`：问答组装走同一条流水线，转写留档 | ✅ |
| `brain/llm.py`：`template`（默认离线）与 `openai`（Ollama / 云端） | ✅ |
| `brain/scheduler.py`：APScheduler 每晚备好问题 + 提醒（去处见 M2） | ✅ |
| `collectors/chat.py`：对话通道 | ✅ |
| `brain/report.py` + `pkbrain stats`：完整率与连续天数 | ✅ |
| `pkbrain talk` / `plan` / `serve` / `goals` / `config` | ✅ |

**验收标准：** 连续 14 天对话，快照完整率 ≥ 90%，中间没有一天需要手工补。

功能齐了，天数还得跑。用 `pkbrain stats` 看：完整率与连续天数就是这两条判据。

## M2 — 采集与对外（目标：3 个月）

| 项 | 状态 |
|---|---|
| `server/mcp.py`：八个工具，stdio 与 streamable-http 两种传输 | ✅ |
| `notify.py`：通知的去处进配置，跨平台 + 可配 hook | ✅ |
| `pkbrain mcp` / `pkbrain notify` / `pkbrain mcp --print-config` | ✅ |
| 录音：自研录音 + faster-whisper，可选接入 screenpipe | ❌ |
| 向量检索：pgvector 或 Qdrant，与自研记忆层二选一（见 ADR 待写） | ❌ |
| 设备与天气：健康设备导入、Open-Meteo | ❌ |
| REST：`/records`、`/search`、`/metrics` | ❌ 等面板需要时再做 |

**验收标准：** 向外部 AI 问「我上周的运动和情绪有什么关系」，回答能指回具体记录。

MCP 那一半现在就能验：`pkbrain mcp --print-config` 把配置贴进客户端，问一句
「我上周的睡眠和情绪有什么关系」，看它能不能报出日期与记录 id。
另一半要等向量检索——纯全文索引答不了「关系」这类跨维度的问法。

## M3 — 回顾与自托管（目标：6 个月）

- `ui/`：Tauri + React 回顾面板，日历热力与维度趋势。
- 实体图谱、加密同步、插件机制。

**验收标准：** 外部用户按 README 自托管跑通全流程。

## 暂不做

| 项 | 原因 |
|---|---|
| 移动端 App | 采集可以在桌面完成，M1 验证前不做 |
| 多人协作 | 这是个人知识库，不是团队产品 |
| 自建模型训练 | 抽取用现成模型够，训练是另一个项目 |
