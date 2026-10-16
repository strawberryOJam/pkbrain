from pkbrain.config import (
    Config,
    LLMConfig,
    McpConfig,
    NotifyConfig,
    ScheduleConfig,
    load_config,
    write_default_config,
)


def test_missing_config_file_uses_defaults(tmp_path, schema):
    config = load_config(tmp_path, schema)
    assert config.llm.provider == "template"
    assert config.schedule.time == "22:00"
    assert config.path is None


def test_write_then_load(tmp_path, schema):
    path = write_default_config(tmp_path, schema)
    assert path.is_file()

    (tmp_path / schema.paths["config"]).write_text(
        '[llm]\nprovider = "openai"\nmodel = "qwen2.5:7b"\n'
        'base_url = "http://localhost:11434/v1"\n\n[schedule]\ntime = "23:30"\nnotify = false\n',
        encoding="utf-8",
    )
    config = load_config(tmp_path, schema)
    assert config.llm.provider == "openai"
    assert config.llm.model == "qwen2.5:7b"
    assert config.llm.api_key_env == "OPENAI_API_KEY"  # 没写的字段回落到默认
    assert config.schedule.time == "23:30"
    assert config.schedule.notify is False
    assert config.path == tmp_path / schema.paths["config"]


def test_write_default_does_not_clobber(tmp_path, schema):
    path = write_default_config(tmp_path, schema)
    path.write_text("我自己改过的\n", encoding="utf-8")
    write_default_config(tmp_path, schema)
    assert path.read_text(encoding="utf-8") == "我自己改过的\n"

    write_default_config(tmp_path, schema, force=True)
    assert "provider" in path.read_text(encoding="utf-8")


def test_generated_config_round_trips(tmp_path, schema):
    write_default_config(tmp_path, schema)
    config = load_config(tmp_path, schema)
    assert config.llm == LLMConfig()
    assert config.schedule == ScheduleConfig()
    assert config.notify == NotifyConfig()
    assert config.mcp == McpConfig()


def test_notify_section_loads(tmp_path, schema):
    (tmp_path / schema.paths["config"]).write_text(
        '[notify]\nbackend = "command"\ncommand = "curl -d \'{message}\'"\ntimeout = 3\n',
        encoding="utf-8",
    )
    config = load_config(tmp_path, schema)
    assert config.notify.backend == "command"
    assert config.notify.command == "curl -d '{message}'"
    assert config.notify.timeout == 3


def test_mcp_section_loads(tmp_path, schema):
    (tmp_path / schema.paths["config"]).write_text("[mcp]\nallow_write = false\n", encoding="utf-8")
    config = load_config(tmp_path, schema)
    assert config.mcp.allow_write is False
    assert config.notify == NotifyConfig()  # 没写的段回落到默认


def test_a_config_without_the_new_sections_still_loads(tmp_path, schema):
    """0.2.0 之前写的 config.toml 没有 [notify] 与 [mcp]，不该因此报错。"""
    (tmp_path / schema.paths["config"]).write_text(
        '[llm]\nprovider = "openai"\n', encoding="utf-8"
    )
    config = load_config(tmp_path, schema)
    assert config.notify == NotifyConfig()
    assert config.mcp.allow_write is True


def test_hour_minute_parsing():
    assert ScheduleConfig(time="22:00").hour_minute == (22, 0)
    assert ScheduleConfig(time="06:05").hour_minute == (6, 5)
    assert ScheduleConfig(time="7").hour_minute == (7, 0)


def test_api_key_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("PKBRAIN_TEST_KEY", "sk-abc")
    assert LLMConfig(api_key_env="PKBRAIN_TEST_KEY").api_key == "sk-abc"
    monkeypatch.delenv("PKBRAIN_TEST_KEY")
    assert LLMConfig(api_key_env="PKBRAIN_TEST_KEY").api_key is None


def test_as_dict_hides_the_path(tmp_path, schema):
    config = load_config(tmp_path, schema)
    assert "path" not in config.as_dict()
    assert config.as_dict()["llm"]["provider"] == "template"
    assert isinstance(Config().llm, LLMConfig)
