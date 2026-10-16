"""记忆层：只增记忆、实体链接、时间感知检索。

M0 是空壳。M2 落地，届时对外提供：

```python
class Memory:
    def add(self, record: Record) -> None: ...
    def link(self, record: Record) -> list[str]: ...      # 实体链接
    def recall(self, query: str, at: datetime) -> list: ...  # 时间感知检索
```

M0 的检索由 `store.sqlite` 的全文索引代劳。数量级到几千条、需要语义召回时再引入向量库
（pgvector 或 Qdrant）与 Mem0 对比，见 docs/ADR。
"""

__all__: list[str] = []
