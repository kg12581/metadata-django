# doris_sql - Doris 建表与结构变更 SQL

用于 MySQL -> Doris 同步场景的 Doris 端 SQL 资产:

| 文件 | 说明 |
| --- | --- |
| `create_table_unique_key.sql` | Unique Key 模型建表模板(支持 upsert/delete) |
| `alter_table_examples.sql` | 字段新增/删除/修改、分区示例 |
| `generate_ddl.py` | 从 MySQL 元数据自动生成 Doris 建表 DDL |
| `generated/` | 生成结果输出目录(gitignore) |

## 生成 Doris DDL

```bash
# 单表(默认 create 模式: 直接生成 CREATE TABLE)
python3 doris_sql/generate_ddl.py --database ai_chatbot --table analytics_event

# 多表
python3 doris_sql/generate_ddl.py --database ai_chatbot --tables analytics_event,auth_user

# sync 模式: 若 Doris 已有该表, 输出 ALTER(新增/删除/修改字段) 对齐语句
python3 doris_sql/generate_ddl.py --database ai_chatbot --table analytics_event --mode sync --doris-db test_db
```

输出文件: `doris_sql/generated/<表名>.ddl.sql`。

## 注意

- Doris 目标表必须 **Unique Key 模型**, 才能正确同步 Debezium/Canal 的 UPDATE/DELETE
- 线上自动变更推荐走平台接口 `/api/metadata/schema-sync/` 或
  `python manage.py schema_sync --apply`(带 preview)
- 字段类型由 MySQL 自动映射: `int(11)->INT`、`tinyint(1)->BOOLEAN`、`varchar(n)->VARCHAR(n)`、
  `text->STRING`、`datetime(6)->DATETIME(6)`、`json->JSON` 等
