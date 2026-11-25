# S0-SMOKE-01 Symphony 与 Codex 研发闭环测试

本任务先读取工作区的 AGENTS.md 和 .radar-task.json，核对当前任务编号和 Issue 编号。只在工作区执行。

1. 创建 `smoke_test/hello.py`，实现函数 `hello()`，返回固定字符串 `Keys Radar Ready`。
2. 创建 `smoke_test/test_hello.py`，用 pytest 验证返回值。测试直接导入该函数。
3. 使用 .radar-task.json 指定的 pytest 可执行文件，运行 `<pytest> -q smoke_test/test_hello.py`，记录原始输出到 `reports/S0-SMOKE-01-pytest.txt`，保留退出码。
4. 保存 `reports/S0-SMOKE-01-delivery.md`，记录文件、命令、实际通过与失败数及阻塞。保存 `reports/S0-SMOKE-01-result.json`，包含 `task`、数字 `issue`、`result`（passed、failed 或 blocked）及 `tests` 数组，数组元素包括 `command` 和数字 `exit_code`。
5. 测试通过后停在等待人工审核。GitHub 状态和标签由已获授权的操作员处理。

业务功能、Git 提交、推送、合并、部署、Github 写入及 P0 任务均超出本次范围。
