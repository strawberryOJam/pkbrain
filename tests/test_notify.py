"""通知：挑哪种去处、hook 怎么跑、失败了怎么办。"""

from __future__ import annotations

from types import SimpleNamespace

from pkbrain.notify import Settings, resolve, send

# ---- 挑去处 -------------------------------------------------------------


def test_auto_picks_osascript_on_macos():
    assert resolve(Settings(), platform="darwin") == "macos"


def test_auto_picks_notify_send_when_it_is_installed():
    which = lambda name: "/usr/bin/notify-send"
    assert resolve(Settings(), platform="linux", which=which) == "linux"


def test_auto_falls_back_to_stdout():
    assert resolve(Settings(), platform="linux", which=lambda name: None) == "stdout"
    assert resolve(Settings(), platform="win32", which=lambda name: None) == "stdout"


def test_an_explicit_backend_wins_over_the_platform():
    assert resolve(Settings(backend="command"), platform="darwin") == "command"
    assert resolve(Settings(backend="NONE"), platform="darwin") == "none"


def test_no_settings_means_auto():
    assert resolve(None, platform="darwin") == "macos"
    assert resolve(Settings(backend="  "), platform="darwin") == "macos"


# ---- macOS ---------------------------------------------------------------


def test_macos_shells_out_to_osascript():
    calls = []

    delivery = send("准备好了", title="PKBrain", platform="darwin",
                    run=lambda args, **kwargs: calls.append(args))
    assert delivery.delivered
    assert delivery.backend == "macos"
    assert calls[0][0] == "osascript"
    assert 'display notification "准备好了" with title "PKBrain"' in calls[0][2]


def test_macos_escapes_quotes():
    calls = []
    send('他说"好"', platform="darwin", run=lambda args, **kwargs: calls.append(args))
    assert '\\"好\\"' in calls[0][2]


def test_macos_on_another_platform_says_why():
    delivery = send("好了", settings=Settings(backend="macos"), platform="linux")
    assert not delivery.delivered
    assert "osascript" in delivery.detail


def test_macos_swallows_failures():
    def boom(*args, **kwargs):
        raise OSError("没有 osascript")

    delivery = send("好了", platform="darwin", run=boom)
    assert not delivery.delivered
    assert "osascript" in delivery.detail


# ---- Linux ---------------------------------------------------------------


def test_linux_uses_notify_send():
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        return SimpleNamespace(returncode=0)

    delivery = send(
        "今晚的问题", title="PKBrain", settings=Settings(backend="linux"), run=fake_run
    )
    assert delivery.delivered
    assert calls == [["notify-send", "PKBrain", "今晚的问题"]]


def test_linux_swallows_a_missing_binary():
    def boom(*args, **kwargs):
        raise FileNotFoundError("notify-send")

    delivery = send("好了", settings=Settings(backend="linux"), run=boom)
    assert not delivery.delivered
    assert "libnotify" in delivery.detail


# ---- hook -----------------------------------------------------------------


def test_command_substitutes_the_placeholders_and_exports_env():
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured["env"] = kwargs["env"]
        captured["shell"] = kwargs["shell"]
        return SimpleNamespace(returncode=0)

    settings = Settings(backend="command", command="say {title}: {message}")
    delivery = send("睡了 6 小时", title="今晚", settings=settings, run=fake_run)

    assert delivery.delivered
    assert captured["argv"] == "say 今晚: 睡了 6 小时"
    assert captured["shell"] is True
    assert captured["env"]["PKBRAIN_TITLE"] == "今晚"
    assert captured["env"]["PKBRAIN_MESSAGE"] == "睡了 6 小时"


def test_command_keeps_literal_braces_alone():
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured["env"] = kwargs["env"]
        return SimpleNamespace(returncode=0)

    settings = Settings(backend="command", command="curl -d '{\"text\": \"$PKBRAIN_MESSAGE\"}'")
    send("hi", settings=settings, run=fake_run)
    assert captured["argv"] == "curl -d '{\"text\": \"$PKBRAIN_MESSAGE\"}'"
    assert captured["env"]["PKBRAIN_MESSAGE"] == "hi"


def test_command_without_a_command_says_so():
    delivery = send("好了", settings=Settings(backend="command", command="  "))
    assert not delivery.delivered
    assert "command 是空的" in delivery.detail


def test_command_reports_a_nonzero_exit():
    settings = Settings(backend="command", command="false")
    delivery = send("好了", settings=settings, run=lambda argv, **kw: SimpleNamespace(returncode=3))
    assert not delivery.delivered
    assert "退出码 3" in delivery.detail


def test_command_swallows_failures():
    def boom(*args, **kwargs):
        raise OSError("没有这个命令")

    delivery = send("好了", settings=Settings(backend="command", command="x"), run=boom)
    assert not delivery.delivered
    assert "hook" in delivery.detail


# ---- 不打搅 ---------------------------------------------------------------


def test_stdout_prints_and_says_it_is_not_a_system_notification():
    printed = []
    delivery = send("准备好了", title="PKBrain", settings=Settings(backend="stdout"), out=printed.append)
    assert printed == ["[PKBrain] 准备好了"]
    assert not delivery.delivered
    assert delivery.backend == "stdout"


def test_none_does_nothing_at_all():
    printed = []
    delivery = send("好了", settings=Settings(backend="none"), out=printed.append)
    assert printed == []
    assert not delivery.delivered


def test_an_unknown_backend_is_reported_not_crashed():
    delivery = send("好了", settings=Settings(backend="telepathy"))
    assert not delivery.delivered
    assert "telepathy" in delivery.detail
    assert "command" in delivery.detail
