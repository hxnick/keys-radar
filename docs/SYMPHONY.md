# Keys Radar Symphony 操作说明

## 版本和环境

本项目按 OpenAI Symphony Elixir 稳定版 **v0.0.3**（`1c0fb6c`）的 GitHub Issues 适配器配置。官方仓库当前文档也列出 Linear、Jira Cloud、Asana 和 GitLab。GitHub Issues 从 v0.0.2 纳入发行。本机环境尚待取得并校验官方 macOS arm64 自包含发行文件。本项目的启动器只需 Python 3.11 标准库。

- [官方仓库](https://github.com/openai/symphony)
- [调度规范](https://github.com/openai/symphony/blob/main/SPEC.md)
- [Elixir 配置和运行文档](https://github.com/openai/symphony/blob/main/elixir/README.md)
- [v0.0.3 发行和校验文件](https://github.com/openai/symphony/releases/tag/v0.0.3)
- [Codex App Server 协议](https://developers.openai.com/codex/app-server/)

优先复用已核验兼容的本机发行文件。需要安装时，在用户批准后从发行页获取 macOS arm64 文件及校验文件，按发行页校验哈希，保存到 Keys Radar 专用的 `.symphony-state/runtime/` 目录并赋予执行权限。自包含版附带 Elixir 和 Erlang，主机还需可运行的 Codex 和 Git。可选的源码构建使用官方文档的 `mise install`、`mise exec -- mix setup` 和 `mise exec -- mix build`，检出已确认的发行标签。S0 可以在没有 `gh` 的情况下验证本地逻辑。正式运行用 GitHub API 读取，操作员可在 GitHub 网页维护任务标签和审核。

## GitHub Issues 状态映射

GitHub Issues 提供 `open` 和 `closed` 两种原生状态。开放 Issue 只能有一个下表中的流程标签。独立调度标签 `radar:run` 由操作员加减。

| 逻辑状态 | GitHub 映射 | 操作 |
| --- | --- | --- |
| Backlog | open + `radar:backlog` | 待规划，移除 `radar:run` |
| Todo | open + `radar:todo` | 授权后加入 `radar:run` 并从本机启动 |
| In Progress | open + `radar:in-progress` | 观察日志输出和工作区初次运行标记后调整。保留 `radar:run` 允许运行中的进程继续 |
| Blocked | open + `radar:blocked` | 先移除 `radar:run` 停止调度，再记录权限、环境或测试阻塞 |
| Human Review | open + `radar:human-review` | 移除 `radar:run`。测试证据通过复核后，操作员转入此状态 |
| Rework | open + `radar:rework` | 填写明确返工要求，用户再次授权才能加 `radar:run` 并用保留工作区续跑 |
| Done | closed | 人工验收及代码整合后，先移除调度标签，再关 Issue |

Symphony 选取 `open` 且带 `radar:run` 的记录。本地启动器另外检查仓库、Issue 编号、非 PR、唯一流程标签、前置任务人工验收记录和 Git 基线。Todo 与 Rework 可启动。运行中允许 In Progress，启动器定期复查标签和状态。未授权 Issue 即使带有运行标签，工作区钩子也会在 Codex 启动前拒绝。当前只允许 P0-01 至 P0-05，P1–P9 均需后续明确的范围与配置变更。

当前适配器会暴露主机代理的 `github_api`。正式运行仅使用限定仓库且只有 Issues 读取权限的细粒度 token。由操作员本人在网页上处理写入。用户自行在终端注入 `KEYS_RADAR_GITHUB_TOKEN`，仓库文件里只有变量引用。流水线运行以现有经授权的 Codex 研发账户为前提。测试联调关闭业务模型调用。

## 运行、暂停和审核

1. 确认 S0 验收报告，批准并准备本地 Git 仓库及干净基线、指定 GitHub 仓库、Issue 读取凭证，以及正式研发会话。记录使用的 Symphony 二进制来源和校验值。
2. 先本地离线验证，再由操作员批准 S0 和一个明确的 P0 Issue。以下 `RADAR_APPROVED_REPO`、`RADAR_APPROVED_ISSUE` 和 `RADAR_SYMPHONY_BIN` 由操作员赋真实值，分别为获准的 `owner/repo`、Issue 编号及二进制绝对路径。

```sh
cd /Users/vision/Projects/keys-radar
python3.11 scripts/symphony_s0.py verify
mkdir -m 700 -p .symphony-state
python3.11 scripts/symphony_s0.py accept-s0 \
  --repo "$RADAR_APPROVED_REPO" --evidence .symphony-state/S0-handover.md
python3.11 scripts/symphony_s0.py run \
  --repo "$RADAR_APPROVED_REPO" --issue "$RADAR_APPROVED_ISSUE" \
  --task P0-01 --symphony "$RADAR_SYMPHONY_BIN"
```

`.symphony-state/S0-handover.md` 由验收人记录真实联调和批准依据。P0-01 对应 Issue 由操作员在用户批准后建立并设置 Todo 和运行标签。启动器执行已经校验的发行文件，实际参数为 `<Symphony 可执行文件> --logs-root <本次运行目录>/logs <本次运行目录>/WORKFLOW.md`。直接运行仓库模板绕过了本机授权配置，模板的钩子会因缺少启动器生成的运行上下文而拒绝。

3. **暂停或止损。** 在前台按 Ctrl+C，或先移除 Issue 的 `radar:run`，随后改设 Blocked。监督进程接收 SIGTERM 同样走暂停流程。单次授权只允许一个 Worker 尝试、最多三个 Codex turn、总前台时限 30 分钟。有 SQLite、网络、凭证、工作区或钩子错误时查阅本次 `launcher.log`、`logs/` 和 `stop.json`。Symphony 的读超时 10 秒、turn 消息静默超时 180 秒和 stall 超时 120 秒独立于总时限。
4. **审核与整合。** 运行停止后，执行 `python3.11 scripts/symphony_s0.py review "$RADAR_RUN_ID"` 验证交付物格式与退出码。操作员查看差异并按验收标准独立复核测试。通过后移除调度标签，将 Issue 转为 Human Review。记录本人复核依据，并令 `RADAR_REVIEW_EVIDENCE` 指向该文件，例如项目忽略目录中的 `.symphony-state/P0-01-handover.md`。有实际差异时，用户先明确授权 Git 整合并提交基线。已有实现直接验证通过时，可沿用干净基线。使用 `python3.11 scripts/symphony_s0.py accept "$RADAR_RUN_ID" --evidence "$RADAR_REVIEW_EVIDENCE"` 记录人工验收，最后人工关闭 Issue。机器校验格式和声明退出码，独立复核由验收人完成。
5. **返工。** 保留旧运行编号。在 Issue 标记 Rework 并取得再授权后，重复启动命令并附加 `--resume "$RADAR_RUN_ID"`。仓库、Issue、任务和基线必须一致。旧运行内的原始代码、数据和证据仍可查阅。基线发生变化时，人工确定新基线和旧成果的迁移方式，再启动新尝试。

## 隔离和成果保存

项目专用 `.symphony-state/` 权限为 0700，已排除出版本控制。调度器每次启动使用全新的运行目录，每个批准 Issue 有独立的 `workspaces/GH-<编号>` 和 `radar/gh-<编号>` 分支。钩子使用本地干净 Git 基线克隆，移除 origin，工作区仅包含本分支和交付文件。原项目工作树及其他项目不参与执行。

应用日志、启动器日志、运行绑定、前置验收凭据和本次变更保存在运行目录。人工暂停保留原工作区。工作流显式配置 `terminal_states: []`，让关闭 Issue 退出活动状态，同时避免交给调度器删工作区。若发生上游清理回调，保留钩子会先尝试将整个工作区原子移到本次运行的 `retained/`，未跟踪文件和 Git 历史一起保留。常规流程先完成复核和留档，再关闭 Issue。官方实现会记录并忽略清理钩子失败，真实接入验收须复测所选二进制对空终态列表的处理和关闭后的实际保留情况。配置、令牌及运营数据应保留在授权位置。

同一项目的前台启动器用主机文件锁限制并发。P0-02 至 P0-05 启动前，逐项检查所有前置任务的人工验收凭据，并用 Git 祖先检查验证已验收的基线包含于当前 HEAD。S0 及任务验收命令仅在操作员终端运行。项目工作流的约束以主机侧启动器、GitHub 只读凭证和 Codex 工作区沙箱共同执行。
