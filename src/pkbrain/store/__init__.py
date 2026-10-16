"""落盘与检索。

两处写入，各有各的用途：

- Markdown：人可读，可导出，可进 Git。是记录的正本。
- SQLite：程序可查，带全文与指标索引。随时可由 Markdown 重建。
"""

from . import markdown, record_json, sqlite

__all__ = ["markdown", "record_json", "sqlite"]
