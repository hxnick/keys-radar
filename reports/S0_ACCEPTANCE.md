# Keys Radar S0 初始化验收报告

2026 年 11 月 25 日。**S0 本地工程初始化完成，真实运行及人工验收待完成。**

## 1. 实际路径与保留范围

本轮在 `/Users/vision/Projects/keys-radar` 执行。建议的嵌套路径不存在。读取并保留已有业务规划、架构、数据模型、合规、竞品、评分和报告规范。使用上次 P0 归档逐文件核对，既有文件仅修改 `.gitignore`、`AGENTS.md`、`README.md` 和 `docs/ROADMAP.md`，P0 业务源码、迁移和原业务测试保持原样。

## 2. Symphony 安装及版本

| 检查 | 实测 |
| --- | --- |
| 主机 | macOS 27.2.1，arm64 |
| Git / GitHub CLI | Git 2.54.0。当前 PATH 和已查安装位置未发现 `gh` |
| Python / uv | Python 3.11.18，uv 0.11.16，现有本地虚拟环境可用 |
| Symphony / Elixir | 当前 PATH 和已查本机安装、项目及 vendor 目录未发现 Symphony。未找到 `elixir`、`erl`、`mix`、`mise` |
| 参考版本 | 官方稳定版 v0.0.3（`1c0fb6c`），提供 macOS arm64 发行构建 |
| 仓库与网络 | 项目无 Git 仓库。执行环境不能解析 `github.com` 和 `raw.githubusercontent.com`。官方资料通过独立网页检索阅读 |

本轮选择官方发行文件路径，避免安装全局 Elixir/Erlang。官方下载和实际载入依赖本机可访问 GitHub 及用户确认。 [官方发行](https://github.com/openai/symphony/releases/tag/v0.0.3) · [Elixir 使用说明](https://github.com/openai/symphony/blob/main/elixir/README.md)

## 3. Codex App Server

Codex CLI 0.139.0，`codex app-server --help` 可用。实际生成的 ThreadStart 和 TurnStart JSON Schema 包含本工作流用到的值。使用 stdio 发送 initialize 请求时，默认 SQLite 状态目录因只读而初始化失败。用进程级 `sqlite_home`、`log_dir` 指向临时目录重试，仍收到 `Operation not permitted`，未收到成功握手响应。过程中没有启动 Codex 模型 turn。 [App Server 协议](https://developers.openai.com/codex/app-server/) · [Codex 配置参考](https://developers.openai.com/codex/config-reference)

## 4. 任务管理平台

建议采用 GitHub Issues。官方 v0.0.2 加入 GitHub Issues 适配器，v0.0.3 包含该适配器。当前官方 Elixir 文档同时列出 Linear、Jira Cloud、Asana 与 GitLab。GitHub 原生 `open` 和 `closed` 配合项目流程标签及独立 `radar:run`。 [发行记录](https://github.com/openai/symphony/releases) · [GitHub 适配器文档](https://github.com/openai/symphony/blob/main/elixir/README.md#github-issues-adapter)

## 5. 文件清单

| 类型 | 文件 |
| --- | --- |
| 项目入口和规划 | 更新 `AGENTS.md`、`README.md`、`docs/ROADMAP.md`、`.gitignore` |
| 工作流和启动器 | 新增 `WORKFLOW.md`、`scripts/symphony_s0.py` |
| 操作及验收 | 新增 `docs/SYMPHONY.md`、`docs/ACCEPTANCE_CRITERIA.md`、`reports/README.md`、`reports/S0_ACCEPTANCE.md` |
| 任务 | 新增 `tasks/P0-01.md` 至 `tasks/P0-05.md` |
| S0 验证 | 新增 `tests/test_symphony_s0.py` |

## 6. 配置说明

WORKFLOW.md 使用 JSON 语法表示 YAML front matter。关键配置为 `tracker.kind: github`、`tracker.provider.repo`、令牌环境变量引用、`required_labels`、`active_states`、`terminal_states`、`workspace.root`、四个生命周期钩子和 Codex stdio。启动器生成本次绝对工作区与经授权仓库的配置副本。单并发、单次批准单个 Worker 尝试，最多 3 个 turn，30 分钟总时限。仓库模板没有有效运行上下文，正式任务只能经启动器准入。 [Symphony 规范](https://github.com/openai/symphony/blob/main/SPEC.md)

## 7. 隔离与留存

每次使用项目专用的私有运行目录，从受审的本地 Git 基线建立独立克隆和 `radar/gh-<Issue>` 分支，去掉 origin。日志、执行记录、报告、原工作区或保留目录一起留存。暂停、失败和超时保留代码。关闭 Issue 退出活动态，`terminal_states: []` 用于避免自动删除。清理钩子另尝试将工作区原子移到同卷的保留位置。返工以新的人工授权复制原工作区，并保留此前版本和测试记录。

## 8. 任务依赖及阶段门禁

S0 人工验收 → P0-01 → P0-02 → P0-03 → P0-04 → P0-05。启动前必须匹配已批准仓库及 Issue，核验标记、状态、前置验收凭据及已验收基线的 Git 祖先关系。锁和一次性运行标记分别限制并发和连续重试。关闭 Issue 或加标签本身不会生成验收凭据。本轮没有 P1–P9 的可执行任务。

## 9. 任务清单

| 编号 | 范围 |
| --- | --- |
| [P0-01](../tasks/P0-01.md) | 项目初始化及研发规范 |
| [P0-02](../tasks/P0-02.md) | 数据库模型及 Alembic 迁移 |
| [P0-03](../tasks/P0-03.md) | 人工需求导入及去重 |
| [P0-04](../tasks/P0-04.md) | 基础 API 及查询统计 |
| [P0-05](../tasks/P0-05.md) | 集成测试及 P0 阶段验收，含真实回环 TCP 缺项 |

既有 P0 实现作为后续任务的基线，按任务范围复核并补齐获准的缺口。

## 10. 本地与真实验证

| 验证项 | 结果 |
| --- | --- |
| 工作流格式 | 本地 Python 配置核验、Ruby YAML 解析和四个 Bash 钩子语法检查通过。官方可执行文件的配置加载待验证 |
| S0 自动化 | 16 项通过。覆盖模拟 Issue 状态、阶段依赖、人工记录、隔离克隆、一轮限制、前台结束、超时、保留未跟踪内容与返工 |
| 全量回归 | 56 项通过，包含既有 40 项 P0 测试 |
| 真实平台 | 未接入。未创建外部仓库、Issue、标签、PR 或账号 |
| 进程 | 本轮只运行有限时的本地测试及 App Server 探测。没有启动长期 Symphony 服务和正式研发任务 |
| Git 操作 | Git 初始化与提交仅发生在临时模拟测试仓库。实际项目没有初始化、提交、推送或合并 |

## 11. 用户需确认的权限与配置

1. 选择是否复用已有兼容的 Symphony 发行文件，或批准下载、校验并在 Keys Radar 专用目录运行 v0.0.3。
2. 指定获准的 GitHub 仓库，单独批准任务和标签管理。由用户在本机注入限该仓库的 Issues 只读令牌，外部状态写入由获授权的操作员承担。
3. 明确授权 Keys Radar 当前目录的 Git 初始化及本地基线提交。将来如涉及远程同步、推送、PR 或整合，分别确认相应操作。
4. 在允许 Codex 写入经授权运行状态目录的环境复测 stdio，确认正式 Codex 研发会话的账户及用量权限。

## 12. 未解决问题和风险

- 本机没有可用 Symphony 二进制。实际 v0.0.3 配置载入、钩子调用和关闭后留存仍待真实接入验证。
- Codex CLI 可运行，App Server 尚未通过 stdio 握手。当前执行环境的本地状态写入也受限制。
- 当前项目缺少本地 Git 基线与授权仓库、凭证及 Issue，正式调度门禁保持关闭。

## 13. 正式启动命令

在批准并准备完实际 Git 基线、二进制和授权参数后运行。

```sh
cd /Users/vision/Projects/keys-radar
python3.11 scripts/symphony_s0.py verify
python3.11 scripts/symphony_s0.py run \
  --repo "$RADAR_APPROVED_REPO" --issue "$RADAR_APPROVED_ISSUE" \
  --task P0-01 --symphony "$RADAR_SYMPHONY_BIN"
```

启动器执行 `<Symphony 二进制> --logs-root <本次运行目录>/logs <本次运行目录>/WORKFLOW.md`。启动前还需完成下节 S0 人工验收记录。

## 14. 启动、暂停和审核

在获授权 Issue 上设置 Todo 与运行标签后前台启动。Ctrl+C、SIGTERM 或撤销运行标签均可用于停止。升级为 Human Review 前，执行 `review <运行编号>` 并由验收人独立复核测试与差异。完成批准的整合后，执行 `accept <运行编号> --evidence <人工复核文件>`，最后人工关闭 Issue。返工使用 Rework 与新一次授权，可按运行编号恢复。完整状态映射和命令见 [Symphony 操作说明](../docs/SYMPHONY.md)。

## 15. S0 验收后开启 P0-01

真实环境复测和人工确认后，由项目负责人在本机执行 `accept-s0 --repo <已批准仓库> --evidence <人工验收文件>`。逐项准备 P0-01 的独立 Issue、Todo 标签、运行标签和上述正式启动参数。本轮停在 S0，等待人工验收。
