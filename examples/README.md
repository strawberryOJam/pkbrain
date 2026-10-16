# 示例

- `today.md`：一份输入。用 `## <维度>` 分节，正文里带数字的句子会被指标字典的正则抽出来。
- `records/`：跑一次 `snapshot` 之后的产出，原样放进来当样例。看它的 frontmatter 与指标表。

复现这条产出：

```sh
uv run pkbrain snapshot --from-file examples/today.md --date 2026-10-16 --tag 晚间
```

短 id 是随机生成的，所以每次跑出来的文件名不同。
