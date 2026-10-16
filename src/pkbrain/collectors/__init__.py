"""采集通道。

| 通道 | M0 状态 | 计划 |
|---|---|---|
| manual | 已实现（读文件） | — |
| chat | 未实现 | M1：定时对话写回 |
| audio | 未实现 | M2：自研录音 + faster-whisper |
| device | 未实现 | M2：健康设备导入 |
| weather | 未实现 | M2：Open-Meteo |

所有通道的产物都是一段文本，交给 `brain.pipeline` 走同一条流水线。
"""

from . import manual

__all__ = ["manual"]
