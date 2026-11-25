# 研发验收记录

- [S0 验收报告](S0_ACCEPTANCE.md)
- [既有 P0 验收报告](../docs/P0_ACCEPTANCE.md)

每个正式任务在其隔离工作区的 `reports/` 生成 `<任务编号>-delivery.md` 和 `<任务编号>-result.json`。报告列出实际代码与文件、目标测试命令、实测结果和日志位置、缺陷、阻塞及待审批项。每个任务至少保存一项适用测试。

```json
{
  "task": "P0-01",
  "issue": 123,
  "result": "passed",
  "tests": [{"command": "uv run --locked pytest -q", "exit_code": 0}]
}
```

上例为格式示例。真实失败或阻塞的 `result` 填 `failed` 或 `blocked`，保留实际非零退出码和证据。验收人核对差异、按任务复核测试，并记录人工意见。运行日志和工作区由本地启动器保存，日常验收报告适合提交到项目文档。
