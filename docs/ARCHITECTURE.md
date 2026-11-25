# 系统架构

P0 由 FastAPI 提供本机 HTTP API，Pydantic 负责数据校验，SQLAlchemy 2 管理会话和模型，SQLite 保存数据，Alembic 管理版本。uv 锁定依赖，pytest 使用独立数据库执行迁移和 API 集成测试。

| 层 | 职责 |
| --- | --- |
| HTTP | 请求解析、分页、响应模型、错误格式与 OpenAPI |
| 人工导入 | 解析 CSV/JSON、字段校验、规范化、去重、创建原始证据 |
| 持久化 | 事务、SQLite 外键、索引和约束 |
| 运行 | 环境配置、日志、健康和就绪检查、回环地址启动入口 |

P1 引入采集适配器和运行台账，再按需采用官方 HTTP 接口、RSS 或公开网页解析。P2 引入可替换的模型 Provider，拟支持 MiniMax M3 与本地 Qwen。调用按任务保留输入证据、结构化输出、运行状态、模型版本和预算成本。Demand、Market、Competitor、Strategy、Technology、Business 分别负责需求、替代方案、竞品、差异化、技术及商业可行性，先以独立任务运行。P6 使用 GitHub REST API。P8 使用 React 和 TypeScript，P9 按需引入 APScheduler 和飞书机器人。

数据库及凭证本地管理。P0 开启 SQLite 外键，写入以事务提交，日志记录批次结果和异常类别。库中时间统一保存为 UTC，API 显式输出时区。后续继续使用关系型数据模型，按确立的业务需求引入基础设施。
