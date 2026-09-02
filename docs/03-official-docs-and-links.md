# 官方文档与学习资源链接

按"本项目已使用"与"建议补齐"分组, 便于按需查阅。

## 一、本项目已使用的组件

### 采集 / CDC

- Debezium 官方文档(PostgreSQL 连接器): <https://debezium.io/documentation/reference/stable/connectors/postgresql.html>
- Debezium 中文站: <https://debezium.cn/documentation//reference/connectors/postgresql.html>
- Canal(Mysql binlog): <https://github.com/alibaba/canal/wiki>

### 消息

- Apache Kafka 文档: <https://kafka.apache.org/documentation/>
- Kafka 中文社区/博客(主题与消费语义入门): <https://www.confluent.io/learn/event-driven-architecture/>

### 实时计算

- Apache Flink 文档(中文 stable): <https://nightlies.apache.org/flink/flink-docs-stable/zh/>
- Flink CDC(全库同步/MySQL→Doris 示例): <https://nightlies.apache.org/flink/flink-cdc-docs-master/docs/get-started/introduction/>
- Flink SQL Client 使用: <https://nightlies.apache.org/flink/flink-docs-stable/zh/docs/dev/table/sql-client/>

### 存储 / OLAP

- Apache Doris 官网与中文文档: <https://doris.apache.org/> / <https://doris.apache.org/zh-CN/docs/dev/getting-started/what-is-apache-doris>
- Doris Flink Connector / Stream Load(数据导入): <https://doris.apache.org/zh-CN/docs/dev/ecosystem/flink-doris-connector> 与 <https://doris.apache.org/zh-CN/docs/dev/data-operate/import/stream-load-manual>
- Doris 官方博客(最佳实践/用户案例): <https://doris.apache.org/blog/>(英文)

### 离线同步

- DataX(阿里开源, 异构数据源离线同步): <https://github.com/alibaba/DataX>
- DataX-Web(可视化调度, 可选): <https://github.com/WeiYe-JingCheng/DataX-Web>

### 离线数仓 / Hive

- Apache Hive 文档: <https://hive.apache.org/>
- HiveServer2 / Beeline 客户端: <https://hive.apache.org/docs/latest/user/hiveserver2-clients/>
- Hive 语言手册(DDL/DML): <https://cwiki.apache.org/confluence/display/Hive/LanguageManual>

### 编排 / 调度

- Apache DolphinScheduler(中文文档): <https://dolphinscheduler.apache.org/zh-cn/docs/latest>
- Apache Airflow 文档: <https://airflow.apache.org/docs/>

### 元数据 / 血缘 / 治理

- Apache Atlas: <https://atlas.apache.org/>
- Atlas 数据血缘概念与集成(AWS 中文博客): <https://aws.amazon.com/cn/blogs/china/apache-atlas-data-bloodline/>
- DataHub(现代数据目录): <https://datahubproject.io/docs/>

## 二、建议补齐的组件

### 数据湖 / 湖仓一体

- Apache Paimon(流式数据湖, Flink 友好): <https://paimon.apache.org/docs/master/>
- Apache Iceberg: <https://iceberg.apache.org/docs/latest/>
- Apache Hudi: <https://hudi.apache.org/docs/>

### 离线计算 / Spark

- Apache Spark 文档(SQL/DataFrame): <https://spark.apache.org/docs/latest/sql-programming-guide.html>
- Spark Structured Streaming: <https://spark.apache.org/docs/latest/structured-streaming-programming-guide.html>

### 数据质量

- Great Expectations: <https://docs.greatexpectations.io/>
- dbt tests / dbt docs: <https://docs.getdbt.com/docs/build/tests>
- Apache Griffin(数据质量平台): <http://griffin.apache.org/>

### 监控告警

- Prometheus: <https://prometheus.io/docs/introduction/overview/>
- Grafana: <https://grafana.com/docs/>
- Flink Metrics 集成 Prometheus: <https://nightlies.apache.org/flink/flink-docs-stable/zh/docs/deployment/metric_reporters/>

### BI / SQL 开发

- Apache Superset: <https://superset.apache.org/docs/intro>
- DBeaver(多数据源 SQL 客户端): <https://dbeaver.io/docs/>

## 三、学习路线与行业参考

- Data Engineering Roadmap 2026(GitHub, 技术栈/项目实践): <https://raw.githubusercontent.com/ErdemOzgen/Data-Engineering-Roadmap/refs/heads/main/DATA_ENGINEERING_ROADMAP_2026.md>
- 2026 大数据技术趋势: 湖仓一体与实时分析(行业文章, 仅供参考): <https://m.zpedu.com/it/data/36508.html>
- 2026 大数据工程师技能升级路线: ETL 到实时数据管道(行业文章, 仅供参考): <https://www.zpedu.com/it/data/40327.html>
- Apache Doris 实战案例/博客聚合: <https://doris.apache.org/blog/>

## 四、本项目内置文档

| 文档 | 位置 |
| --- | --- |
| 架构与模块使用 | `docs/01-architecture.md` |
| 技术栈对照与扩展建议 | `docs/02-tech-stack-map.md` |
| 本文件(链接大全) | `docs/03-official-docs-and-links.md` |
| 主 README | `README.md` |
| Kafka T+1 ETL | `etl/README.md` |
| Flink SQL 作业 | `flink_sql/README.md`(文件头含建表/变更/FAQ) |
| Doris SQL 资产 | `doris_sql/README.md` |
| Hive SQL 资产 | `hive_sql/README.md` |
