# Keys Radar P0 开发验收报告

验收日期为 2026 年 11 月 25 日。

## 1. 项目状态

P0 代码、数据库与文档已交付。依赖安装、迁移、40 项自动化测试和 13 次 Uvicorn HTTP 请求验证通过。TCP 回环监听被当前执行环境拒绝，因此 P0 的本机 TCP 启动验收仍待完成。P1 等待人工确认。

## 2. 实际项目路径

`/Users/vision/Projects/keys-radar`。该目录启动前为空，附件建议的嵌套路径不存在。检查时项目没有 Git 仓库。项目运行于 macOS ARM64、Python 3.11.18 和 SQLite 3.54.1。

## 3. 实际新增文件

| 用途 | 文件 |
| --- | --- |
| 项目说明及规则 | `AGENTS.md`、`README.md`、`tasks/P0.md` |
| 依赖与环境 | `pyproject.toml`、`uv.lock`、`.python-version`、`.gitignore`、`.env.example` |
| 后端入口与配置 | `radar/__init__.py`、`radar/__main__.py`、`radar/main.py`、`radar/config.py` |
| 数据与导入 API | `radar/constants.py`、`radar/db.py`、`radar/models.py`、`radar/schemas.py`、`radar/errors.py`、`radar/imports.py`、`radar/api.py` |
| 数据迁移 | `alembic.ini`、`migrations/env.py`、`migrations/script.py.mako`、`migrations/versions/0001_p0_schema.py` |
| 测试 | `tests/conftest.py`、`tests/test_migrations.py`、`tests/test_api.py` |
| 规划 | `docs/PROJECT_BRIEF.md`、`docs/ARCHITECTURE.md`、`docs/ROADMAP.md`、`docs/DATA_SCHEMA.md`、`docs/SOURCE_COMPLIANCE.md`、`docs/COMPETITIVE_ANALYSIS.md`、`docs/SCORING_RULES.md`、`docs/OPPORTUNITY_REPORT_SCHEMA.md` |
| 验收 | `docs/P0_ACCEPTANCE.md` |

本机默认库 `data/keys_radar.sqlite3` 已迁移至 `0001 (head)`。库内预置 17 个来源目录项，原始需求和证据均为 0 条。联调与测试用库独立存放。源代码包仅包含项目文件，运行依赖和业务数据库由本地启动步骤生成。

## 4. 数据库结构

| 业务表 | 主要字段及关系 |
| --- | --- |
| `data_sources` | 来源编码和名称，编码唯一 |
| `raw_posts` | 平台记录 ID、标题、原文、链接、发布时间和导入时间、录入方式、内容哈希、类型、模拟标识和核实状态。外键关联来源 |
| `evidence_records` | 原文摘录、来源、链接、获取时间、可信度及模拟标识。复合外键确保原始需求、来源及模拟标识匹配 |
| `demand_signals` | 场景、痛点、证据评级、创建时间。外键指向原始需求 |
| `business_opportunities` | 产品名称、定位、目标用户、痛点、使用场景、验证状态、模拟标识及时间 |
| `opportunity_evidence` | 机会与证据多对多，复合外键约束模拟状态一致 |
| `analysis_runs` | 任务类型、状态、输入输出引用、模型版本、起止时间与异常摘要 |

SQLite 外键已启用。时间统一为 UTC。相同来源及模拟标识下，规范链接、平台记录 ID、内容哈希任一匹配即判重复。重复提交返回已有 ID，保留原始记录。Alembic 另有版本表。

## 5. API 实测

| 接口 | 功能 | HTTP 协议验证 |
| --- | --- | --- |
| `GET /health` | 服务健康 | 200 |
| `GET /ready` | 七张业务表可读性 | 200。未迁移和缺表时的 503 由自动测试验证 |
| `GET /api/v1/data-sources` | 来源列表及分页 | 200，共 17 个来源 |
| `POST /api/v1/raw-posts` | 单条 JSON 导入并生成证据 | 201，重复请求返回 409 和已有记录编号 |
| `POST /api/v1/raw-posts/import` | JSON/CSV 批量导入 | 两种格式均返回 200，JSON 含重复项仍能导入有效记录 |
| `GET /api/v1/raw-posts` | 分页和多字段筛选 | 200，按 review 类型及模拟标识筛选命中 1 条 |
| `GET /api/v1/raw-posts/{id}` | 原始内容和证据 | 200，核对返回证据的归属记录 |
| `GET /api/v1/stats` | 模拟与非模拟分组统计 | 200，模拟需求及证据各 3 条，非模拟分组均为 0 |
| `GET /docs`、`GET /openapi.json` | 文档及接口规范 | HTML 与 JSON 均为 200，OpenAPI 含 7 条业务路径 |

## 6. 测试与验收

| 项目 | 结果 |
| --- | --- |
| 独立虚拟环境及锁文件安装 | 通过。当前环境的 PyPI 域名解析失败，使用本机缓存完成 `uv sync --locked --offline` |
| pytest | 总计 40，通过 40，失败 0，跳过 0 |
| 测试覆盖 | 空库迁移、回退及重升、数据约束、三种导入、格式校验、并发去重、批次部分成功及异常整批回滚、证据关联、分页筛选、模拟隔离、健康就绪、统计和 OpenAPI |
| Alembic 与默认库 | `upgrade head`、`downgrade base`、重新升级通过，`alembic check` 无差异。默认库完整性及外键检查通过 |
| 服务启动及 HTTP | 应用启动生命周期通过。Uvicorn H11 经成对 Unix 套接字完成 13 次 HTTP/1.1 请求。启动入口绑定 TCP 8765 时收到 `Operation not permitted` |
| 范围 | 本轮仅实现 P0 的本地后端和人工数据管理。前端、采集、模型调用和 Agent 按路线图分期。工作未涉及 Git 提交、推送或部署 |

## 7. 启动命令

```sh
cd /Users/vision/Projects/keys-radar
uv sync --locked
uv run --locked alembic upgrade head
uv run --locked python -m radar
```

uv 根据 `.python-version` 选择 Python 3.11 并建立 `.venv`。可复制 `.env.example` 为 `.env` 后修改路径、端口和日志等级。更多试用命令及三种导入格式见 [README](../README.md)。

## 8. 本机访问地址

在允许回环 TCP 监听的环境启动后使用下列地址。对应路由已通过 Uvicorn HTTP 协议验证。

- [API 健康检查](http://127.0.0.1:8765/health)
- [数据库就绪检查](http://127.0.0.1:8765/ready)
- [Swagger 文档](http://127.0.0.1:8765/docs)
- [OpenAPI JSON](http://127.0.0.1:8765/openapi.json)

## 9. 未解决事项

- 在允许端口绑定的本机环境，复核 Uvicorn 的回环 TCP 启动和浏览器访问。Swagger 页返回的 HTML 已核验，浏览器加载页面资源未测试。
- 业务样本仍空库。自动化和 HTTP 联调均使用显式模拟数据，真实来源和内容由后续人工核实。
- P0 导入默认待核实，当前已支持按核实状态筛选。修改核实状态的人工工作流属于后续阶段。

## 10. P1 建议及前置条件

P0 的 TCP 验收完成、项目负责人确认后，先核实 V2EX 官方接口规则、认证及限流，确定采集字段和保留范围。按采集任务记录、幂等去重、来源追溯和失败处理建设首个适配器。受限平台继续通过人工导入或授权数据接入。
