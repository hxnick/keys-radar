# 数据模型

## P0 物理表

| 表 | 主要字段 | 关系及约束 |
| --- | --- | --- |
| data_sources | id、code、name | code 唯一。迁移预置来源目录，列入目录仅表示可人工登记 |
| raw_posts | id、data_source_id、external_id、title、content、original_url、published_at、imported_at、collection_method、content_hash、data_type、is_simulated、verification_status | 来源外键。来源及数据性质内分别对平台记录 ID、标准化网址、内容哈希建唯一约束。列表筛选字段有索引 |
| evidence_records | id、evidence_type、data_source_id、original_url、summary、raw_post_id、acquired_at、credibility_status、is_simulated | 复合外键保证需求、来源及模拟标识一致。原始内容、证据摘要及链接可通过详情追溯 |
| demand_signals | id、raw_post_id、scenario、pain_point、evidence_grade、created_at | 原始需求外键及索引，评级可空或为 S/A/B/C/D |
| business_opportunities | id、product_name、positioning、target_users、pain_point、use_case、validation_status、is_simulated、created_at、updated_at | 独立产品机会记录，验证状态有约束 |
| opportunity_evidence | opportunity_id、evidence_id、is_simulated | 机会与证据多对多，组合主键。复合外键保证同一数据性质 |
| analysis_runs | id、task_type、status、input_ref、model_version、result_ref、started_at、finished_at、error_summary | 运行骨架，状态有约束，按状态和启动时间索引 |

SQLite 连接均开启外键。UTC 时间以固定格式保存，输入发布时间需要时区。原始需求及证据导入即为待核实。后三类分析及机会业务由后续阶段写入。Alembic 另外管理版本表。

## 分阶段关系

| 阶段 | 实体与关系 |
| --- | --- |
| P1 | collection_runs 关联 data_sources，记录起止、计数和失败原因，按数据源及启动时间索引 |
| P2 | 扩展 demand_signals 与 analysis_runs。model_usage_logs 关联运行，记录 Provider、模型、令牌和估算成本。evidence_links 规划通用来源关系，关联时维护实体完整性 |
| P3 | demand_clusters 与 demand_signals 通过 cluster_members 多对多关联，成员唯一，记录证据独立性判断 |
| P4 | market_solutions 统一存名称、类型、目标用户、官网及调查时间。competitor_products 一对一扩展产品信息。competitor_features、competitor_prices、competitor_reviews 挂接产品及来源。价格保存币种、周期、版本和调查日期 |
| P5 | market_gaps 关联需求及解决方案对比证据。competitive_advantages 关联缺口及目标方案。advantage_validations 记录指标、成本、验证状态、结果和证据 |
| P6 | open_source_projects 按规范仓库地址唯一。open_source_licenses 按项目、组件、版本审查。project_matches 关联项目和机会，technical_validations 记录运行及配置证据 |
| P7 | opportunity_scores 按机会、规则版本、维度及时间保存依据。feasibility_reports 记录报告版本。validation_tasks 记录验证方法、状态和结果 |
| P8–P9 | project_decisions 关联机会及人工决策，保存决策人、原因、时间。system_settings 记录非秘密配置，凭证引用环境变量 |

后续表及索引通过独立迁移落地。来源调查时间和验证时间分别记录。待验证字段保留为空或明确标记待验证。
