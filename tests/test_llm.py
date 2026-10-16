"""模型层。OpenAI 兼容那部分打一个本地桩服务器，真发一次 HTTP。"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from pkbrain.brain.llm import OpenAICompatLLM, TemplateLLM, build_llm
from pkbrain.config import Config, LLMConfig


class StubHandler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802 - http.server 的接口
        length = int(self.headers.get("Content-Length", 0))
        self.server.received = json.loads(self.rfile.read(length))
        self.server.authorization = self.headers.get("Authorization")
        payload = {
            "choices": [{"message": {"content": "昨晚睡得怎么样？"}}],
            "usage": {"total_tokens": 42},
        }
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # 别往测试输出里灌日志
        return


@pytest.fixture
def server():
    httpd = HTTPServer(("127.0.0.1", 0), StubHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd
    httpd.shutdown()


def test_template_llm_returns_the_question_unchanged():
    reply = TemplateLLM().ask("昨天身体怎么样？")
    assert reply.text == "昨天身体怎么样？"
    assert reply.model == "template"
    assert reply.fallback is False


def test_template_llm_reflects_on_the_session():
    assert "3 个回答" in TemplateLLM().reflect(3, 5).text
    assert "没有可量化的指标" in TemplateLLM().reflect(3, 0).text


def test_build_llm_defaults_to_offline():
    assert isinstance(build_llm(Config()), TemplateLLM)


def test_build_llm_rejects_an_unknown_provider():
    with pytest.raises(ValueError, match="未知的 llm.provider"):
        build_llm(Config(llm=LLMConfig(provider="gpt-5-telepathy")))


def test_openai_llm_needs_a_base_url_and_model():
    with pytest.raises(ValueError, match="base_url"):
        OpenAICompatLLM(LLMConfig(provider="openai"))
    with pytest.raises(ValueError, match="model"):
        OpenAICompatLLM(LLMConfig(provider="openai", base_url="http://localhost:1/v1"))


def test_openai_llm_appends_the_chat_path():
    llm = OpenAICompatLLM(LLMConfig(provider="openai", model="m", base_url="http://x/v1/"))
    assert llm.endpoint == "http://x/v1/chat/completions"
    already = OpenAICompatLLM(
        LLMConfig(provider="openai", model="m", base_url="http://x/v1/chat/completions")
    )
    assert already.endpoint == "http://x/v1/chat/completions"


def test_openai_llm_calls_the_endpoint(server):
    base_url = f"http://127.0.0.1:{server.server_port}/v1"
    llm = OpenAICompatLLM(LLMConfig(provider="openai", model="qwen2.5", base_url=base_url))
    reply = llm.ask("昨天身体怎么样？", context="昨天记了：跑了 30 分钟。")

    assert reply.text == "昨晚睡得怎么样？"
    assert reply.tokens == 42
    assert reply.fallback is False

    sent = server.received
    assert sent["model"] == "qwen2.5"
    assert sent["messages"][0]["role"] == "system"
    assert "跑了 30 分钟" in sent["messages"][1]["content"]
    assert "昨天身体怎么样？" in sent["messages"][1]["content"]


def test_openai_llm_sends_the_key_from_the_environment(server, monkeypatch):
    monkeypatch.setenv("PKBRAIN_TEST_KEY", "sk-test-key")
    base_url = f"http://127.0.0.1:{server.server_port}/v1"
    llm = OpenAICompatLLM(
        LLMConfig(provider="openai", model="m", base_url=base_url, api_key_env="PKBRAIN_TEST_KEY")
    )
    llm.ask("在吗？")
    assert server.authorization == "Bearer sk-test-key"


def test_openai_llm_sends_no_authorization_without_a_key(server, monkeypatch):
    monkeypatch.delenv("PKBRAIN_TEST_KEY", raising=False)
    base_url = f"http://127.0.0.1:{server.server_port}/v1"
    llm = OpenAICompatLLM(
        LLMConfig(provider="openai", model="m", base_url=base_url, api_key_env="PKBRAIN_TEST_KEY")
    )
    llm.ask("在吗？")
    assert server.authorization is None


def test_openai_llm_falls_back_when_the_endpoint_is_down():
    llm = OpenAICompatLLM(
        LLMConfig(provider="openai", model="m", base_url="http://127.0.0.1:9/v1"),
        timeout=2,
    )
    ask = llm.ask("昨天身体怎么样？")
    assert ask.text == "昨天身体怎么样？"
    assert ask.fallback is True

    reflect = llm.reflect(2, 1)
    assert "2 个回答" in reflect.text
