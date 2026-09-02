# hive_sql - Hive 建表 SQL 资产

用于从 MySQL(或 PostgreSQL) 元数据生成 Hive 贴源层(ODS)外部表 DDL:

| 文件 | 说明 |
| --- | --- |
| `create_external_table_template.sql` | Hive 外部表模板(ORC + 注释 + 可选分区) |
| `generate_ddl.py` | 从 MySQL 元数据自动生成 Hive 建表 DDL |
| `generated/` | 生成结果输出目录(gitignore) |

## 生成 Hive DDL

```bash
python3 hive_sql/generate_ddl.py --database ai_chatbot --table analytics_event
python3 hive_sql/generate_ddl.py --database ai_chatbot --tables a,b --hive-db ods \
  --location-prefix hdfs://nameservice1/user/hive/warehouse/ --partition-dt dt
```

输出文件: `hive_sql/generated/<表名>.hive.sql`。

## MySQL -> Hive 类型映射摘要

| MySQL | Hive |
| --- | --- |
| tinyint(1) / boolean | BOOLEAN |
| tinyint | TINYINT |
| smallint | SMALLINT |
| int / mediumint / integer | INT |
| bigint | BIGINT |
| float / double | FLOAT / DOUBLE |
| decimal(p,s) / numeric | DECIMAL(p,s) |
| char(n) | CHAR(n) |
| varchar / text / json / enum / set / uuid | STRING |
| date | DATE |
| datetime / timestamp | TIMESTAMP |
| time | STRING |
| binary / blob | BINARY |

## 说明

- Hive 无主键/唯一约束, 生成的 DDL 只做字段+注释对齐; 若需精确去重/更新,
  建议 Hive 3 + ACID(primary key 需 `TBLPROPERTIES ('transactional'='true')`), 一般 ODS 用快照覆盖即可
- 建议 ODS 表加 `dt`(STRING/日期) 分区, 每次跑批先 `ALTER TABLE ... DROP IF EXISTS PARTITION (dt='...')` 再覆盖写入
- Hive 自身元数据存放在 metastore(如 MySQL 的 `hive_metastore` 库: `TBLS`/`COLUMNS_V2`/`SDS` 等表),
  如需从 Hive 反向读表结构, 可在此平台上把 metastore MySQL 配成数据源后扩展 Hive 读取器
- 类型映射与字段来源与平台 `common/` 的元数据读取保持一致(MySQL information_schema)
