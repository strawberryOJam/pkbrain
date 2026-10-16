"""把一条消息送出去：系统通知，或你自己配的一条 hook。

默认跨平台：macOS 走 `osascript`，Linux 走 `notify-send`，两样都没有就把消息打到终端。
想接别的地方——Bark、ntfy、企业微信、写进一个文件——配一条 shell 命令就够了：

    [notify]
    backend = "command"
    command = "curl -s -X POST https://ntfy.sh/我的主题 -d '{message}'"

`{title}` 与 `{message}` 会被替换；同时以环境变量 `PKBRAIN_TITLE` / `PKBRAIN_MESSAGE` 传入，
命令里本来就含花括号时用环境变量那份。

发不出去不算失败：调用方拿到的 `Delivery` 会说清用了哪种方式、为什么没成。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Callable

BACKENDS = ("auto", "macos", "linux", "command", "stdout", "none")
DEFAULT_TITLE = "PKBrain"


@dataclass(frozen=True)
class Settings:
    """通知的去处。`config.NotifyConfig` 与它同形，可直接传进来。"""

    backend: str = "auto"
    command: str = ""
    timeout: float = 10.0


@dataclass(frozen=True)
class Delivery:
    delivered: bool
    backend: str
    detail: str = ""

    def __bool__(self) -> bool:
        return self.delivered


def resolve(settings: Settings | None = None, *, platform: str | None = None,
            which: Callable[[str], str | None] = shutil.which) -> str:
    """定下这次用哪种方式。`auto` 按平台与手边有什么来挑。"""
    backend = (settings.backend if settings else "auto").strip().lower() or "auto"
    if backend != "auto":
        return backend
    platform = platform or sys.platform
    if platform == "darwin":
        return "macos"
    if which("notify-send"):
        return "linux"
    return "stdout"


def send(
    message: str,
    *,
    title: str = DEFAULT_TITLE,
    settings: Settings | None = None,
    platform: str | None = None,
    run: Callable = subprocess.run,
    which: Callable[[str], str | None] = shutil.which,
    out: Callable[[str], object] = print,
    env: dict[str, str] | None = None,
) -> Delivery:
    """发一条消息。永远不抛异常。"""
    settings = settings or Settings()
    backend = resolve(settings, platform=platform, which=which)

    if backend == "none":
        return Delivery(False, backend, "配置成不发通知")
    if backend == "macos":
        return _osascript(title, message, settings=settings, run=run, platform=platform)
    if backend == "linux":
        return _notify_send(title, message, settings=settings, run=run)
    if backend == "command":
        return _command(title, message, settings=settings, run=run, env=env)
    if backend == "stdout":
        out(f"[{title}] {message}")
        return Delivery(False, backend, "打到标准输出")
    return Delivery(False, backend, f"不认识的通知方式 {backend!r}，可选 {'/'.join(BACKENDS)}")


def _osascript(title: str, message: str, *, settings, run, platform=None) -> Delivery:
    platform = platform or sys.platform
    if platform != "darwin":
        return Delivery(False, "macos", f"osascript 只在 macOS 上有，当前 {platform}")
    script = f'display notification "{_escape(message)}" with title "{_escape(title)}"'
    try:
        run(["osascript", "-e", script], check=False, capture_output=True, timeout=settings.timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        return Delivery(False, "macos", f"osascript 没跑起来：{exc}")
    return Delivery(True, "macos", "osascript")


def _notify_send(title: str, message: str, *, settings, run) -> Delivery:
    argv = ["notify-send", title, message]
    try:
        run(argv, check=False, capture_output=True, timeout=settings.timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        return Delivery(False, "linux", f"notify-send 没跑起来：{exc}（没装就 apt install libnotify-bin）")
    return Delivery(True, "linux", "notify-send")


def _command(title: str, message: str, *, settings, run, env=None) -> Delivery:
    template = settings.command.strip()
    if not template:
        return Delivery(False, "command", "[notify] command 是空的，先在 config.toml 里写一条")
    argv = template.replace("{title}", title).replace("{message}", message)
    environment = {**os.environ, **(env or {})}
    environment["PKBRAIN_TITLE"] = title
    environment["PKBRAIN_MESSAGE"] = message
    try:
        completed = run(
            argv,
            shell=True,
            check=False,
            capture_output=True,
            timeout=settings.timeout,
            env=environment,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return Delivery(False, "command", f"hook 没跑起来：{exc}")
    code = getattr(completed, "returncode", 0)
    if code:
        return Delivery(False, "command", f"hook 退出码 {code}")
    return Delivery(True, "command", template)


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')
