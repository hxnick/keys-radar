---
{
  "tracker": {
    "kind": "github",
    "provider": {
      "repo": "owner/keys-radar",
      "token": "$KEYS_RADAR_GITHUB_TOKEN"
    },
    "required_labels": ["radar:run"],
    "active_states": ["open"],
    "terminal_states": []
  },
  "polling": {"interval_ms": 10000},
  "workspace": {"root": "$KEYS_RADAR_WORKSPACE_ROOT"},
  "hooks": {
    "after_create": "exec \"${KEYS_RADAR_PYTHON:?}\" \"${KEYS_RADAR_HOOK_SCRIPT:?}\" hook prepare",
    "before_run": "exec \"${KEYS_RADAR_PYTHON:?}\" \"${KEYS_RADAR_HOOK_SCRIPT:?}\" hook before-run",
    "after_run": "exec \"${KEYS_RADAR_PYTHON:?}\" \"${KEYS_RADAR_HOOK_SCRIPT:?}\" hook after-run",
    "before_remove": "exec \"${KEYS_RADAR_PYTHON:?}\" \"${KEYS_RADAR_HOOK_SCRIPT:?}\" hook preserve",
    "timeout_ms": 60000
  },
  "agent": {
    "max_concurrent_agents": 1,
    "max_turns": 3,
    "max_retry_backoff_ms": 15000
  },
  "codex": {
    "command": "codex app-server --listen stdio://",
    "approval_policy": "never",
    "thread_sandbox": "workspace-write",
    "turn_timeout_ms": 180000,
    "read_timeout_ms": 10000,
    "stall_timeout_ms": 120000
  }
}
---

本次 GitHub Issue 为 {{ issue.identifier }}。先读取工作区里的 `.radar-task.json`、`AGENTS.md`、`docs/PROJECT_BRIEF.md`、`docs/ARCHITECTURE.md`、`docs/ROADMAP.md`、`docs/ACCEPTANCE_CRITERIA.md` 以及 `.radar-task.json` 指定的本地任务文件。控制文件缺失、编号有冲突、范围有歧义或外部权限不足时，记录阻塞后结束。

以验收条件为准，先确认当前代码及测试状态。优先复用已交付的 P0 内容，只处理当前任务范围内的缺口。使用独立临时数据库和显式模拟数据。按任务要求执行测试并保存实际输出。

交付 `reports/<任务编号>-delivery.md` 和 `reports/<任务编号>-result.json`。结构化结果列出工作区绑定的任务、Issue 和每个测试的命令及真实退出码。报告列出实际变更、测试证据、未验收项和阻塞原因。无代码差异时，报告核对过程及有效验收证据。

状态、评审和代码整合由操作员处理。所有更改留在当前本地工作区。禁止写入 GitHub、提交、推送、合并、部署、启动其他任务或调用业务模型。
