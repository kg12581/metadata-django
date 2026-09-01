# flink_sql - Flink SQL 实时 CDC 作业

与 `etl/`(Python T+1 批量) 互补的**实时**同步方案:

| 文件 | 数据链路 | Kafka topic 示例 | pipeline.name |
| --- | --- | --- | --- |
| `postgresql_debezium_kafka2doris.sql` | PostgreSQL -> Debezium -> Kafka -> Flink -> Doris | `cdcpg.public.orders` | `pg-debezium-kafka-to-doris` |
| `mysql_canal_kafka2doris.sql` | MySQL -> Canal -> Kafka -> Flink -> Doris | `mysql_canal.users` | `mysql-canal-kafka-to-doris` |

## 环境 (192.168.3.100, 已在文件头注明)

- Flink 1.20.5 standalone: `/opt/flink` (Web UI http://192.168.3.100:8081)
- Kafka 2.13-4.3.1: `192.168.3.100:9092`
- Debezium Connect 3.6.1.Final: http://192.168.3.100:8083
- Canal 1.1.x: 输出 canal-json 到 Kafka
- Doris 2.1.11: FE MySQL 9030 / FE HTTP 8030
- 依赖 jar(放到 `/opt/flink/lib` 后重启集群):
  - `flink-sql-connector-kafka-3.4.0-1.20.jar`
  - `flink-doris-connector-1.20-25.1.0.jar`

## 提交作业

```bash
./submit_flink_sql.sh postgresql_debezium_kafka2doris.sql
./submit_flink_sql.sh mysql_canal_kafka2doris.sql
```

`FLINK_HOME` 默认 `/opt/flink`, 可用环境变量覆盖; 提交日志写到 `../logs/flink_submit_*.log`。

## 停止作业

```bash
./stop_flink_sql.sh "pg-debezium-kafka-to-doris"
./stop_flink_sql.sh "mysql-canal-kafka-to-doris"
```

## 与 etl/ 的关系

- `flink_sql/`: 实时 CDC, 秒级延迟, 需要常驻 Flink 集群
- `etl/`: 每日 T+1 批量消费 Kafka 一天数据, 增量写 Doris, 适合日终补数/对账

两者可并存: 实时作业保证及时性, T+1 批量做兜底对账。详细 SQL 说明(建表/字段变更/FAQ)
见各 .sql 文件头部注释。
