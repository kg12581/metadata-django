# etl - Kafka(PG Debezium) -> Doris 每日 T+1 增量同步

## 文件

| 文件 | 说明 |
| --- | --- |
| `etl_kafka_doris.py` | ETL 主程序: 消费 Kafka Debezium 变更事件, 按日期过滤, 增量写入 Doris |
| `run_daily_t1.sh` | T+1 调度脚本: 每天处理昨天一天的数据, 写日志到 `logs/` |
| `config.json` | topic -> Doris 表映射及连接配置(环境变量可覆盖) |

## 数据链路

```text
PostgreSQL (WAL) -> Debezium -> Kafka (cdcpg.public.<table>)
    -> etl_kafka_doris.py (每天 T+1 跑一次, 按事件时间过滤昨天)
    -> Doris Unique Key 表 (INSERT ON DUPLICATE KEY UPDATE / DELETE / TRUNCATE)
```

## 运行

```bash
# 处理昨天一天的数据
python etl/etl_kafka_doris.py

# 指定日期(补数)
python etl/etl_kafka_doris.py --date 2026-08-31

# 只消费统计不写 Doris
python etl/etl_kafka_doris.py --dry-run

# 全量重放某一天(全新消费组, 从 earliest 开始, 仍按日期过滤)
python etl/etl_kafka_doris.py --date 2026-08-31 --replay
```

## T+1 调度 (crontab)

```bash
chmod +x etl/run_daily_t1.sh
```

crontab 每天 01:30 执行:

```cron
30 1 * * * /Users/kgt/code/metadata-django/etl/run_daily_t1.sh >> /Users/kgt/code/metadata-django/logs/cron_t1.log 2>&1
```

每次运行日志: `logs/etl_<日期>.log`。

## 配置

`config.json` 里 `topics` 把 Kafka topic 映射到 Doris 表:

```json
{
  "topics": {
    "cdcpg.public.orders": {
      "doris_database": "test_db",
      "doris_table": "orders",
      "primary_keys": ["id"]
    }
  }
}
```

未配置的 topic 会自动取 topic 最后一段作为表名, 主键从 Debezium key 推断。
环境变量覆盖: `KAFKA_BOOTSTRAP_SERVERS` / `KAFKA_GROUP_ID` / `KAFKA_TOPICS` /
`DORIS_HOST` / `DORIS_PORT` / `DORIS_USER` / `DORIS_PASSWORD` / `DORIS_DATABASE` /
`ETL_TIMEZONE`。

## 注意事项

- Doris 目标表必须是 **Unique Key 模型**(支持 upsert/delete)
- PG 表建议 `ALTER TABLE ... REPLICA IDENTITY FULL`, 保证 UPDATE 的 before 完整
- Debezium `decimal.handling.mode=string` 时, 小数以字符串输出, 直接透传
- 依赖: `pip install kafka-python pymysql`
