# PKBrain

开源、本地优先、Build in Public 的**个人知识库大脑**。

把每天的生活与内心按「人的维度」记下来，沉淀成一份会思考的数字自我，让任何 AI 都能基于它与你对话。

> 现状：**M1 开发中**。每晚的会话已经能用——`pkbrain talk` 按记忆挑问题，你回答，落成当天的快照；
> `pkbrain stats` 报完整率。M1 的验收是连续 14 天、完整率 ≥ 90%，天数是跑出来的，不是写出来的。
> M2 的第一件也落了地：`pkbrain mcp` 把大脑接给任意 AI。
> 其余能力按 [ROADMAP](docs/ROADMAP.md) 推进。
>
> PKBrain 是工作名（决策点 D1），正式命名与商标检查在公开前完成。

## 与 PKBS 的关系

PKBrain 是《个人知识库标准与规范（PKBS-1.0）》的软件实现。

- **PKBS** 回答「记录什么」——记录类型、维度、隐私分级、统一 frontmatter。
- **PKBrain** 回答「怎么自动记录、怎么让知识库变聪明」——四层采集、每日流水线、个性化回环。

PKBS-1.0 正文尚未并入本仓库。现在落的是[最小子集](docs/PKBS-MIN.md)（[ADR-0002](docs/ADR/0002-最小-PKBS-子集.md)），等正文到手后按 ADR 替换。

## 架构

```
collectors → brain → store → server
   采集        提问与抽取   落盘    对外
```

| 模块 | 职责 | 状态 |
|---|---|---|
| `collectors/` | 四层采集：手动、对话、录音、设备、天气 | 手动 ✅ 对话 ✅ 录音/设备/天气 M2 |
| `brain/` | 提问引擎、抽取、快照组装、定时 | ✅（语义抽取 M2） |
| `store/` | Markdown 与 SQLite 双写、检索 | ✅ |
| `memory/` | 只增记忆、实体链接 | 空壳，M2 |
| `server/` | MCP 对外 | ✅ 读写八工具（stdio / http），REST 待做 |
| `ui/` | 回顾面板 | 未开始，M3 |

## 快速开始

```sh
uv sync

# 1. 初始化数据目录（默认 ~/.pkbrain），建库、目标清单和配置
uv run pkbrain init

# 2. 看看今晚会问什么
uv run pkbrain plan

# 3. 答题。回答里有数字就会被抽成指标
uv run pkbrain talk

# 4. 查完整率和记录
uv run pkbrain stats
uv run pkbrain search 睡眠
```

数据落在 `~/.pkbrain/`：

```
~/.pkbrain/
  records/2026/10/2026-10-16-R1-<短 id>.md   # 人可读的正本：frontmatter + 正文
  sessions/2026-10-16-<短 id>.md             # 会话转写：问了什么、答了什么、依据哪条记录
  goals.md                                   # 目标清单
  config.toml                                # 模型与定时设置
  pkbrain.db                                 # 程序可查的索引
```

换目录用 `--data-dir` 或环境变量 `PKBRAIN_HOME`。

## 每晚怎么用

```sh
# 不想人守着：挂一个常驻进程，每晚 22:00 把问题备好并弹通知
uv run pkbrain serve

# 或者交给系统的 cron / launchd，一句就够
0 22 * * *  cd ~/pkbrain && uv run pkbrain serve --now
```

`serve` 备好问题后，`pkbrain talk` 会直接用那一批，不问第二遍。当天已经不缺什么了就什么都不问。

提问引擎按四级优先级挑问题（见 [ADR-0005](docs/ADR/0005-提问引擎的优先级.md)）：

1. 昨天写着「明天要…」的事，追问进展；
2. 昨天的快照缺哪个维度，就补问哪个；
3. 目标清单里最急的一条；
4. 精神层反思，每周至少一次；闲下来时回看 30/90/365 天前的记录。

改问法不用改代码，改 `schema/pkbs.yaml` 的 `questions` 段即可。

## 通知发到哪里

`serve` 备好问题后会提醒你。去处写在 `config.toml` 里，不绑平台：

```toml
[notify]
# auto：macOS 用 osascript，有 notify-send 就用它，两样都没有就打到终端。
backend = "auto"

# 想送到别处就换成一条命令，{title} 与 {message} 会被替换：
# backend = "command"
# command = "curl -s -X POST https://ntfy.sh/我的主题 -d '{message}'"
```

```sh
uv run pkbrain notify "测试一条"   # 自查：告诉你这次走了哪条路
uv run pkbrain config show        # 看生效的 backend
```

命令同时拿到环境变量 `PKBRAIN_TITLE` 与 `PKBRAIN_MESSAGE`，命令里本来就含花括号时用它们。
发不出去不会中断 `serve`。

## 接上任意 AI（MCP）

`pkbrain mcp` 在 stdin/stdout 上跑一个 MCP server。Claude Desktop、Cursor、Codex，或自己写的
agent，接上就能查你的历史：

```sh
uv run pkbrain mcp --print-config
```

把打印出来的 JSON 贴进客户端配置。Claude Desktop 是
`~/Library/Application Support/Claude/claude_desktop_config.json`：

```json
{
  "mcpServers": {
    "pkbrain": {
      "command": "pkbrain",
      "args": ["mcp", "--data-dir", "/Users/you/.pkbrain"]
    }
  }
}
```

用 uv、不想全局装的话，`command` 换成 `uv`、`args` 改成 `["run", "pkbrain", "mcp", ...]`。

| 工具 | 做什么 |
|---|---|
| `brain_schema` | 这份知识库的词汇表：记录类型、维度、指标、隐私分级。写之前先看它 |
| `brain_stats` | 条数、覆盖天数、完整率、连续天数 |
| `search_records` | 全文检索，可按维度 / 日期 / 隐私过滤 |
| `get_record` | 按日期或记录 id 取 Markdown 原文 |
| `metric_series` | 某个指标随时间的取值 |
| `list_goals` | 目标清单 |
| `todays_questions` | 今天会问什么。只读，不动轮换状态 |
| `add_record` | 把一段文本落成记录 |

接上以后就能问「我上周的睡眠和情绪有什么关系」「我上次说要联系客户，后来怎么样了」，
回答里会带日期与记录 id，能自己核对。

- 只想要只读大脑：`config.toml` 里写 `[mcp] allow_write = false`。
- 让别的机器或别的进程接：`uv run pkbrain mcp --transport http --port 8765`，
  端点是 `http://127.0.0.1:8765/mcp`。默认只监听本地，没有认证，别对着公网开。

多说一句隐私：记录带 P0/P1/P2 三级，MCP 会原样交给客户端。P2 是你特意标成敏感的那些，
往外发之前先问自己一句。见 [ADR-0006](docs/ADR/0006-mcp-接入与通知的去处.md)。

## 用哪个模型

默认 `template`：不联网、不要密钥，问句用 schema 里的话术原文。开箱即用。

想让它问得更贴合昨天的事，换成本地 Ollama：

```sh
ollama serve
ollama pull qwen2.5:7b
uv run pkbrain config init
# 把 config.toml 里改成：
#   provider = "openai"
#   model = "qwen2.5:7b"
#   base_url = "http://localhost:11434/v1"
uv run pkbrain config show
```

云端同理，填各自的 `base_url`，密钥放进 `api_key_env` 指的环境变量。模型只负责把问句写自然，
调用失败会静默退回模板话术——晚上的会话不会因为网络抖断开。

## 输入格式

`snapshot` 与 `talk` 都接受 Markdown。用 `## <维度>` 分节，维度按 `schema/pkbs.yaml` 的编码或中文名匹配。

```markdown
# 2026-10-16 晚间快照

## D1 身体
睡了 6.5 小时，质量一般。没运动。

## 情绪
今天有点焦虑，客户的事悬着。
```

落在维度标题下的正文原样保留。指标（睡眠时长、体重、心情等）按 `schema/metrics.csv` 的正则抽成结构化字段，
抽不到的正文进 `## 自由记录`，一个字不丢。

## 常用命令

```sh
pkbrain snapshot --from-file today.md --date 2026-10-16 --privacy P1 --tag 晚间
pkbrain talk --date 2026-10-16          # 补录过去某一天
pkbrain search "睡眠" --dim D1 --since 2026-10-01 --limit 10
pkbrain show 2026-10-16
pkbrain goals add "联系客户确认合同" --due 2026-10-20 --dim D3
pkbrain goals show
pkbrain config show
pkbrain stats --target 0.9
pkbrain mcp --print-config              # 贴进 MCP 客户端的配置
pkbrain notify "测试一条"                # 看通知走哪条路
pkbrain schema export                    # 由 pydantic 模型重新生成 schema/record.json
```

## 开发

```sh
uv run pytest
uv run pkbrain --help
```

### 想看有历史数据的样子

```sh
uv run pkbrain demo seed --data-dir /tmp/pkbrain-demo --days 40
uv run pkbrain stats --data-dir /tmp/pkbrain-demo
uv run pkbrain plan  --data-dir /tmp/pkbrain-demo
```

生成连续 N 天的快照，每天四个维度全填、指标落在 schema 区间内。固定随机种子，同一种子出同一批数据。

演示记录带 `tags: [演示数据]` 与 `source: seed_demo`，和真人记录一眼分得开；目标目录里已有记录时默认拒绝写入。
它让「没数据时看不到样子」这件事有解，但不代替 M1 的 14 天验收——那条说的是你自己连续用了 14 天。

## 不做什么

- 不托管你的数据：没有服务端，没有账号，没有同步。
- 不做通用笔记应用：不管知识管理，只管「记录人」。
- 不绑定模型：抽取与提问所用模型可插拔，本地 Ollama 与云端 API 都走同一条接口。

## 许可

Apache-2.0，全文见 [LICENSE](LICENSE)。版权 2026 echoyan。

决策点 D1–D8 的拍板结果与公开前清单见 [docs/DECISIONS.md](docs/DECISIONS.md)。
