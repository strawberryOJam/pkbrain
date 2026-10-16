"""对外接口：MCP。

`server.mcp` 把大脑挂到 MCP 上，客户端是谁都行：Claude Desktop、Cursor、Codex、自己写的 agent。

```sh
pkbrain mcp                     # stdio，本地客户端用这个
pkbrain mcp --transport http    # streamable-http，别的机器或别的进程接
```

M0 是空壳，M1 之前只有本地 CLI。M2 落地 MCP 读写；REST 还没做。

这里不 `import mcp`：MCP 的 SDK 依赖不轻，只有真跑 `pkbrain mcp` 时才加载。
"""

__all__: list[str] = []
