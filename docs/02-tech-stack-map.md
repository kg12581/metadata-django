# 大数据开发技术栈对照与扩展建议

对照"大数据开发常用技术分层", 逐项给出**业界主流方案 → 本项目现状 → 建议**。
本项目已覆盖从"元数据到数据同步"的闭环, 下面按是否已落地/待补齐标记:

✅ 已落地  ⏳ 已有雏形(文档/模板)  ❌ 待补齐

## 1. 数据采集 (CDC / 同步)

| 能力 | 主流技术 | 本项目现状 | 建议 |
| --- | --- | --- | --- |
| MySQL 增量 | Canal / Flink CDC | ✅ Kafka topic `mysql_canal.*` + Flink SQL canal-json 作业 | 可再引入 Flink CDC YAML 全库同步(Doris connector 官方示例) |
| PostgreSQL 增量 | Debezium | ✅ `cdcpg.*` + Flink SQL debezium-json 作业 | 增量快照(signal table)、`REPLICA IDENTITY FULL` 规范文档化 |
| 离线批量 | DataX / Sqoop | ✅ MySQL→Doris job 生成与执行 | 接入 DataX-Web 可视化调度(可选) |
| 日志/对象存储 | Flume / Filebeat | ❌ | 按需补日志采集到 Kafka |

## 2. 消息传输

| 能力 | 主流技术 | 本项目现状 | 建议 |
| --- | --- | --- | --- |
| 消息总线 | Kafka | ✅ 已使用, topic 命名 `<prefix>.<schema>.<table>` | 补 topic 规范与保留期/容量规划文档 |
| 消费语义 | 精确一次 | ⏳ ETL 幂等 upsert + Flink checkpoint | Kafka offset 提交与幂等键说明已含于 etl/README |

## 3. 存储

| 层 | 主流技术 | 本项目现状 | 建议 |
| --- | --- | --- | --- |
| OLTP 源 | MySQL / PostgreSQL | ✅ 元数据读取 + 源配置 | Oracle 读取器待接(oracledb) |
| OLAP | Doris / ClickHouse | ✅ Unique Key 建表/自动 DDL/校验 | 补数据模型分层(dwd/dws/ads)示例 |
| 离线数仓 | Hive | ⏳ `hive_sql/` 模板与 DDL 生成 | 部署 HiveServer2 后补 beeline 提交/执行脚本 |
| 数据湖 | Iceberg / Paimon / Hudi | ❌ | 建议下一步: Flink + Paimon 湖仓一体(见 03 链接) |

## 4. 计算引擎

| 能力 | 主流技术 | 本项目现状 | 建议 |
| --- | --- | --- | --- |
| 实时计算 | Flink SQL / Flink CDC | ✅ Flink 1.20 作业(含自动结构变更重启) | 补 SQL 模板分层: ODS→DWD→ADS 流式 |
| 离线计算 | Spark / Hive | ❌ | 建议补 Spark SQL ETL 示例与提交脚本(Spark 3.x + Hive 数仓) |
| 即席查询 | Doris / Spark Thrift | ✅ Doris SQL 助手 | 补 Doris 物化视图/异步物化视图示例 |

## 5. 任务调度

| 能力 | 主流技术 | 本项目现状 | 建议 |
| --- | --- | --- | --- |
| 工作流调度 | DolphinScheduler / Airflow | ⏳ 自研 crontab + 管理页面 | 接入 DolphinScheduler: 元数据同步/结构同步/T+1/重跑依赖 |
| 失败重试与告警 | 调度器 + 通知 | ⏳ crontab 日志落盘 | 补钉钉/邮件告警脚本或接入 DolphinScheduler 告警 |

## 6. 元数据与治理

| 能力 | 主流技术 | 本项目现状 | 建议 |
| --- | --- | --- | --- |
| 元数据目录/资产 | DataHub / Atlas / 自研 | ✅ 本项目自研(库表字段索引约束 + Web) | 提供 OpenAPI 推送资产到 DataHub/Atlas(接口见 01 文档) |
| 数据血缘 | Atlas Lineage / 自研 | ❌ | P1: 记录 ETL/DataX 血缘(source→target), 页面展示或推送 Atlas |
| 数据源配置 | 集中管理 | ✅ `/sources/` JDBC 配置 + 测试 + 同步 | 补密钥加密存储(当前为明文本地库, 生产需加密) |
| 数据字典/注释 | 平台展示 | ✅ 注释随元数据采集 | 打通业务元数据(负责人/口径)录入 |

## 7. 数据质量

| 能力 | 主流技术 | 本项目现状 | 建议 |
| --- | --- | --- | --- |
| 完整性/一致性 | 结构校验 + 行数校验 | ✅ MySQL vs Doris 结构校验 | P1: 增加 T+1 行数/关键指标对账任务 |
| 质量规则 | Great Expectations / dbt test | ❌ | 建议 P2: 抽样规则 + 告警, 或接入 Apache Griffin |

## 8. 监控与运维

| 能力 | 主流技术 | 本项目现状 | 建议 |
| --- | --- | --- | --- |
| 引擎监控 | Prometheus + Grafana | ⏳ Flink Web UI / REST 可用 | 接入 Prometheus: Flink/Kafka/Doris 指标大盘 |
| 链路告警 | 告警规则 | ⏳ ETL 日志 | 补 Kafka 消费延迟(LAG)与 Doris 导入失败告警 |
| 数据量观测 | 元数据行数 | ❌ | 元数据模型加 row_count 采集任务(P1) |

## 建议演进路线 (Roadmap)

### P0(近期, 提升可靠性与闭环)

1. 调度统一: 接入 DolphinScheduler, 元数据同步 → 结构同步 → T+1 数据同步串成工作流
2. 对账任务: 每日 MySQL/PG 行数与 Doris/Hive 行数对账 + 告警
3. Oracle/Hive 读取器: 支持 `sources` 页面配置后一键同步 Oracle、Hive(metastore)

### P1(中期, 治理与体验)

4. 血缘记录: ETL/DataX/Flink 作业自动登记 source→target, 提供血缘 API/页面
5. 元数据导出到 DataHub/Atlas, 或与离线数仓元数据打通
6. 数据源密码加密存储(非对称/密钥环), 连接信息审计

### P2(远期, 湖仓与智能)

7. Flink + Paimon/Iceberg 湖仓一体, Hive 层逐步迁移
8. 基于元数据的智能建仓: 按源表模板批量生成 Doris/Hive 分层 DDL + 同步作业
9. SQL 助手增强: 语法校验(经 Doris/PG explain)、慢查询与执行计划收藏

## 项目能力速查(相对传统"只写 SQL"工程的差异点)

- **元数据驱动 DDL**: 源端加字段 → `schema_sync` 自动 ALTER Doris, 无需手写
- **双链路增量**: Flink 实时(秒级) + Python T+1(兜底对账)
- **结构前置校验**: DataX 同步前强制 MySQL vs Doris 结构一致
- **可视化调度**: 结构同步任务页面直接写 crontab
