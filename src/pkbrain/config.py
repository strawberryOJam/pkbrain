"""数据目录里的配置：`<data_dir>/config.toml`。

写这个文件是可选动作。文件不存在时用默认值：离线模板模型，不联网，不需要密钥。
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

TEMPLATE = """\
# PKBrain 配置。改完直接生效，不用重启任何东西。

[llm]
# template：离线模板，不联网、不要密钥，够把对话闭环跑通。
# openai：任何 OpenAI 兼容端点。Ollama 用 http://localhost:11434/v1 且不需要 key。
provider = "template"
model = ""
base_url = ""
# 密钥从环境变量读，不写进这个文件。
api_key_env = "OPENAI_API_KEY"
temperature = 0.3

[schedule]
# pkbrain serve 每晚开一场会话的时间，24 小时制。
time = "22:00"
# 到点发不发通知。
notify = true

[notify]
# 通知往哪送。auto：macOS 用 osascript，Linux 用 notify-send，都没有就打到终端。
# 可选 auto / macos / linux / command / stdout / none。
backend = "auto"

# backend = "command" 时跑这句。{title} 与 {message} 会被替换，
# 同时也以环境变量 PKBRAIN_TITLE / PKBRAIN_MESSAGE 传入。例如：
#   command = "curl -s -X POST https://ntfy.sh/我的主题 -d '{message}'"
command = ""

# 单次投递的超时秒数。hook 卡住不会拖住 serve。
timeout = 10.0

[mcp]
# 允许 MCP 客户端（Claude Desktop、Cursor、任意 agent）写入记录。
# 关掉就是只读大脑：检索、统计、看目标都能用，写不进来。
allow_write = true
"""


@dataclass(frozen=True)
class LLMConfig:
    provider: str = "template"
    model: str = ""
    base_url: str = ""
    api_key_env: str = "OPENAI_API_KEY"
    temperature: float = 0.3

    @property
    def api_key(self) -> str | None:
        return os.environ.get(self.api_key_env) or None


@dataclass(frozen=True)
class ScheduleConfig:
    time: str = "22:00"
    notify: bool = True

    @property
    def hour_minute(self) -> tuple[int, int]:
        hour, _, minute = self.time.partition(":")
        return int(hour), int(minute or 0)


@dataclass(frozen=True)
class NotifyConfig:
    """通知的去处。与 `notify.Settings` 同形，可直接交给 `notify.send`。"""

    backend: str = "auto"
    command: str = ""
    timeout: float = 10.0


@dataclass(frozen=True)
class McpConfig:
    allow_write: bool = True


@dataclass(frozen=True)
class Config:
    llm: LLMConfig = field(default_factory=LLMConfig)
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)
    notify: NotifyConfig = field(default_factory=NotifyConfig)
    mcp: McpConfig = field(default_factory=McpConfig)
    path: Path | None = None

    def with_llm(self, **changes: object) -> Config:
        return replace(self, llm=replace(self.llm, **changes))

    def to_toml(self) -> str:
        return TEMPLATE

    def as_dict(self) -> dict:
        data = asdict(self)
        data.pop("path", None)
        return data


def config_path(data_dir: Path, schema) -> Path:
    return Path(data_dir) / schema.paths["config"]


def load_config(data_dir: Path, schema) -> Config:
    path = config_path(data_dir, schema)
    if not path.is_file():
        return Config()
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    llm = LLMConfig(**{**asdict(LLMConfig()), **raw.get("llm", {})})
    schedule = ScheduleConfig(**{**asdict(ScheduleConfig()), **raw.get("schedule", {})})
    notify = NotifyConfig(**{**asdict(NotifyConfig()), **raw.get("notify", {})})
    mcp = McpConfig(**{**asdict(McpConfig()), **raw.get("mcp", {})})
    return Config(llm=llm, schedule=schedule, notify=notify, mcp=mcp, path=path)


def write_default_config(data_dir: Path, schema, *, force: bool = False) -> Path:
    path = config_path(data_dir, schema)
    if path.exists() and not force:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(TEMPLATE, encoding="utf-8")
    return path
