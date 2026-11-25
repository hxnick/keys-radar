# Keys Radar 商业需求雷达

keys-ai 内部需求管理服务。P0 支持人工录入原始需求、附带证据查询、JSON/CSV 批量导入、分页筛选及分类统计。市场与技术判断纳入 [项目路线](docs/ROADMAP.md)，由后续阶段构建。

## Symphony 研发流程

S0 配置、启动命令、Issue 标签及人工门禁见 [Symphony 操作说明](docs/SYMPHONY.md)。  
[研发验收标准](docs/ACCEPTANCE_CRITERIA.md) · [S0 验收记录](reports/S0_ACCEPTANCE.md)

## 本地启动

要求 Python 3.11 与 uv。在项目根目录执行以下命令。

```sh
uv sync --locked
uv run --locked alembic upgrade head
uv run --locked python -m radar
```

默认数据库为 `data/keys_radar.sqlite3`，默认端口为 8765。可复制 `.env.example` 为 `.env`，或在命令前设置 `RADAR_DATABASE_PATH`、`RADAR_PORT` 和 `RADAR_LOG_LEVEL`。相对路径以启动目录为准。运行迁移后再启动服务。uv 会创建独立的 `.venv`。启动入口绑定 `127.0.0.1`，供本机访问。

- [健康检查](http://127.0.0.1:8765/health)
- [就绪检查](http://127.0.0.1:8765/ready)
- [Swagger 文档](http://127.0.0.1:8765/docs)
- [OpenAPI JSON](http://127.0.0.1:8765/openapi.json)

## API

| 方法与路径 | 用途 |
| --- | --- |
| GET /health | 进程状态，数据库不可用时仍可返回 200 |
| GET /ready | 检查七张业务表，未迁移或不可用时返回 503 |
| GET /api/v1/data-sources | 查询来源目录及可用的 source_code，支持分页 |
| POST /api/v1/raw-posts | 单条 JSON 导入，201 返回需求及证据，重复时 409 |
| POST /api/v1/raw-posts/import | 批量导入 JSON 数组或 CSV，返回批次统计与错误明细 |
| GET /api/v1/raw-posts | 分页查询，可按 source_code、data_type、verification_status、is_simulated 筛选 |
| GET /api/v1/raw-posts/{id} | 查询需求原文及关联证据，缺失时 404 |
| GET /api/v1/stats | 按 real 和 simulated 分别汇总需求及证据数量 |

分页用 `page` 和 `page_size`，默认为第 1 页、每页 50 条，每页最多 100 条。列表按导入时间及记录 ID 倒序，原文和证据通过详情查询。统计中的 `real` 指人工标为非模拟的记录，来源和事实仍需核实。错误采用 `{"error":{"code":"…","message":"…","details":[]}}`，重复录入会附带 `existing_id`。

## 导入示例

下列记录均为模拟样例。必填 `source_code`、`title`、`content`、`original_url`、`data_type`、`is_simulated`。可选 `external_id` 和 `published_at`，发布时间采用含时区的 ISO 8601 格式。JSON 模拟标识须为布尔值。数据类型支持 `post`、`comment`、`review`、`feature_request`、`service_request`、`other`。

单条录入示例。

```sh
curl -X POST http://127.0.0.1:8765/api/v1/raw-posts \
  -H 'Content-Type: application/json' \
  --data-binary '{"source_code":"manual_other","external_id":"demo-1","title":"模拟需求 1","content":"模拟联调用例","original_url":"https://demo.invalid/posts/1","published_at":"2026-11-25T09:00:00+08:00","data_type":"post","is_simulated":true}'
```

JSON 批量文件示例，保存为 `batch.json`。

```json
[
  {
    "source_code": "manual_other",
    "title": "模拟需求 2",
    "content": "模拟 JSON 批量导入用例",
    "original_url": "https://demo.invalid/posts/2",
    "data_type": "feature_request",
    "is_simulated": true
  }
]
```

CSV 批量文件示例，保存为 `batch.csv`。用 UTF-8 编码，可带 BOM，按逗号分列，允许引号包裹含逗号或换行的内容。模拟标识填 `true` 或 `false`，可选字段留空即可。

```csv
source_code,external_id,title,content,original_url,published_at,data_type,is_simulated
manual_other,demo-3,模拟需求 3,"模拟 CSV, 批量导入用例",https://demo.invalid/posts/3,,review,true
```

```sh
curl -X POST http://127.0.0.1:8765/api/v1/raw-posts/import \
  -H 'Content-Type: application/json' --data-binary @batch.json

curl -X POST http://127.0.0.1:8765/api/v1/raw-posts/import \
  -H 'Content-Type: text/csv' --data-binary @batch.csv
```

### 入库与去重

- 录入时间和证据获取时间由服务生成。发布日期统一转换为 UTC，查询输出显式时区。新记录和自动生成的原文摘录均标为 `unverified`，可按验证状态筛选。
- 文本统一 Unicode、换行格式和首尾空白。内容哈希用合并空白后的 SHA-256。在同一来源及模拟状态中，原始记录 ID、规范 HTTP(S) 链接或内容哈希任一相同，都视为重复。评论及子记录使用各自的原始链接或有区分度的永久链接。保留已有记录，导入时只校验链接格式。
- 批量请求大小上限 5 MiB，最多 1,000 条。整份文件不能解析、缺必填表头或表头重复时拒绝整批。一份可解析的文件允许有效行提交，重复及格式错误的记录逐条报告。JSON 行号为数组中从 1 开始的位置，CSV 行号为该记录结束的物理行。
- 每个有效批次用一个数据库事务写入。发生意外数据库错误会回滚整个批次。响应中的 `total = imported + duplicates + failed`。重复项及失败项可从 `issues` 查看，重试不会覆盖已有记录。

## 测试

```sh
uv run --locked pytest -q
```

测试使用临时 SQLite 文件与显式模拟样本。要人工联调并保留默认库为空，先用独立路径运行迁移和启动。

```sh
radar_demo_dir="$(mktemp -d)"
export RADAR_DATABASE_PATH="$radar_demo_dir/keys_radar.sqlite3"
uv run --locked alembic upgrade head
uv run --locked python -m radar
```

[项目说明](docs/PROJECT_BRIEF.md) · [开发架构](docs/ARCHITECTURE.md) · [数据模型](docs/DATA_SCHEMA.md) · [P0 验收范围](tasks/P0.md)
