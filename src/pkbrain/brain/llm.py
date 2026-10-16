"""模型层：可插拔，默认离线。

两个实现：

- `TemplateLLM`：不联网、不要密钥。用 schema 里的话术原文，够把闭环跑通。
- `OpenAICompatLLM`：任何 OpenAI 兼容端点。Ollama 用 `http://localhost:11434/v1`，不需要 key；
  DeepSeek、OpenAI、豆包填各自的 base_url 与 `api_key_env`。

调用失败一律回退到模板话术。晚上的会话不该因为网络抖动开不起来。
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol

from ..config import Config, LLMConfig

TIMEOUT_SECONDS = 30
PROMPT_VERSION = "m1-v1"


@dataclass(frozen=True)
class Reply:
    text: str
    model: str
    tokens: int | None = None
    fallback: bool = False


class LLM(Protocol):
    name: str

    def ask(self, question: str, *, context: str = "") -> Reply: ...

    def reflect(self, answered: int, metrics: int) -> Reply: ...


class TemplateLLM:
    """离线实现。句子都来自 schema 与固定模板，所以不会编。"""

    name = "template"

    def ask(self, question: str, *, context: str = "") -> Reply:
        return Reply(text=question, model=self.name)

    def reflect(self, answered: int, metrics: int) -> Reply:
        if metrics:
            text = f"记下了：{answered} 个回答，抽出 {metrics} 个指标。"
        else:
            text = f"记下了：{answered} 个回答。今天没有可量化的指标，正文都留着。"
        return Reply(text=text, model=self.name)


class OpenAICompatLLM:
    """OpenAI 兼容的 /chat/completions。用标准库发请求，不引额外依赖。"""

    name = "openai"

    def __init__(self, config: LLMConfig, *, timeout: int = TIMEOUT_SECONDS) -> None:
        if not config.base_url:
            raise ValueError("provider = openai 时必须填 base_url")
        if not config.model:
            raise ValueError("provider = openai 时必须填 model")
        self.config = config
        self.timeout = timeout
        self.model_name = f"{config.model}@{config.base_url}"

    @property
    def endpoint(self) -> str:
        base = self.config.base_url.rstrip("/")
        return base if base.endswith("/chat/completions") else f"{base}/chat/completions"

    def _chat(self, system: str, user: str) -> Reply:
        body = json.dumps(
            {
                "model": self.config.model,
                "temperature": self.config.temperature,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            }
        ).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        request = urllib.request.Request(self.endpoint, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        text = payload["choices"][0]["message"]["content"].strip()
        tokens = (payload.get("usage") or {}).get("total_tokens")
        return Reply(text=text, model=self.model_name, tokens=tokens)

    def ask(self, question: str, *, context: str = "") -> Reply:
        system = (
            "你在帮一个人做每日自我记录。把给你的问题改写成一句自然、具体、好回答的中文问句。"
            "只输出这一句，不要解释，不要加引号，不要编号。"
        )
        user = f"参考背景：\n{context}\n\n问题：{question}" if context else f"问题：{question}"
        try:
            return self._chat(system, user)
        except (urllib.error.URLError, OSError, KeyError, IndexError, ValueError, json.JSONDecodeError):
            return Reply(text=question, model=self.model_name, fallback=True)

    def reflect(self, answered: int, metrics: int) -> Reply:
        system = "你在帮一个人做每日自我记录。用一句不超过 40 字的中文回应他，不要寒暄，不要提问。"
        user = f"他回答了 {answered} 个问题，记下 {metrics} 个可量化指标。"
        try:
            return self._chat(system, user)
        except (urllib.error.URLError, OSError, KeyError, IndexError, ValueError, json.JSONDecodeError):
            return TemplateLLM().reflect(answered, metrics)


def build_llm(config: Config) -> LLM:
    provider = (config.llm.provider or "template").lower()
    if provider == "template":
        return TemplateLLM()
    if provider in {"openai", "ollama", "deepseek"}:
        return OpenAICompatLLM(config.llm)
    raise ValueError(f"未知的 llm.provider：{provider}，可选 template / openai")
