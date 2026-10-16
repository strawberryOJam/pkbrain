"""对外接口：MCP 与 REST。

M0 是空壳。M2 落地，届时：

- REST：`/records`、`/search`、`/metrics`，只读先行；
- MCP：用 modelcontextprotocol 的 python-sdk 暴露 `search_records`、`get_snapshot` 两个只读工具，
  让 Claude、ChatGPT、豆包接得上。

M0 的 In/Out 清单把 MCP 推到 M2，先把手动闭环跑通。
"""

__all__: list[str] = []
