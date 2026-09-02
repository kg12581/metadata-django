# API 调用文档

统一前缀 `http://127.0.0.1:8000/api/metadata/`, 除标注 GET 外均可按需使用 curl 调试。
写操作均需 `POST` + `Content-Type: application/json`。

## 1. 元数据同步

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/sync/` | 拉取远端元数据入库(可覆盖连接) |
| GET | `/databases/` | 数据源列表(含表数) |
| GET | `/databases/<id>/` | 数据源详情(含全部表) |
| GET | `/tables/<id>/` | 表详情(字段/索引/约束) |
| GET | `/databases/<id>/export/` | 导出 Excel(.xlsx) |

```bash
curl -X POST http://127.0.0.1:8000/api/metadata/sync/ \
  -H "Content-Type: application/json" \
  -d '{"db_type":"mysql","database":"ai_chatbot","schema":"ai_chatbot"}'
```

## 2. 结构校验与自动 DDL

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/datax/check/` | MySQL vs Doris 结构一致性校验, 返回 `data.consistent` |
| POST | `/datax/sync/` | 校验一致后执行 DataX 同步 |
| POST | `/schema-sync/` | 按 MySQL 元数据自动对齐 Doris(增删改字段/自动建表) |
| GET/POST | `/schema-sync/task/` | 定时任务配置 |
| POST | `/schema-sync/task/save/` | 保存任务并写入 crontab |
| POST | `/schema-sync/run/` | 按任务配置立即执行 |
| GET | `/schema-sync/log/` | 最近执行日志 |

```bash
curl -X POST http://127.0.0.1:8000/api/metadata/datax/sync/ \
  -H "Content-Type: application/json" \
  -d '{"database":"ai_chatbot","table":"analytics_event","doris_database":"test_db"}'
```

## 3. ETL (Kafka -> Doris)

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/etl/config/` | ETL 配置 |
| POST | `/etl/config/save/` | 保存 ETL 配置 |
| POST | `/etl/run/` | 后台启动 ETL(`date`, `dry_run`) |
| GET | `/etl/log/` | 最近日志 |

## 4. Flink

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/flink-sql/files/` | SQL 作业文件列表 |
| GET | `/flink-sql/file/?name=xxx.sql` | 文件内容 |
| GET | `/flink-sync/jobs/` | 作业状态与结构差异 |
| POST | `/flink-sync/generate/` | 重新生成运行时 SQL |
| POST | `/flink-sync/apply/` | savepoint 停止 -> 生成 -> 重启 |

## 5. 数据源配置

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/sources/` | 配置列表(密码掩码) |
| POST | `/sources/create/` | 新建(类型/主机/端口/库/JDBC) |
| POST | `/sources/<id>/update/` | 更新 |
| POST | `/sources/<id>/delete/` | 删除 |
| POST | `/sources/<id>/test/` | 连接测试 |
| POST | `/sources/<id>/sync/` | 用该配置同步元数据 |

## 6. SQL 助手

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/sql-helper/options/` | 数据源选项 |
| GET | `/sql-helper/tables/?db_id=1` | 表列表 |
| GET | `/sql-helper/table/<id>/` | 表信息 + 生成 SQL 片段 |

## 7. 对账中心

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/reconcile/tasks/` | 对账任务列表 |
| POST | `/reconcile/tasks/create/` | 新建任务 |
| GET | `/reconcile/tasks/<id>/` | 任务详情 + 历史 |
| POST | `/reconcile/tasks/<id>/update/` | 更新 |
| POST | `/reconcile/tasks/<id>/run/` | 执行 |
| POST | `/reconcile/tasks/<id>/delete/` | 删除 |

```bash
curl -X POST http://127.0.0.1:8000/api/metadata/reconcile/tasks/1/run/
```

## 8. SQL 文件库 / 血缘 / AI / 文档 / 运营

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/sql-files/files/?path=` | 目录列表(本地或远程 SFTP) |
| GET | `/sql-files/file/?path=xxx.sql` | 读取文件 |
| GET | `/lineage/` | 血缘图 |
| POST | `/lineage/parse/` | 解析/保存 SQL 血缘 |
| POST | `/lineage/clear/` | 清空血缘 |
| POST | `/llm/analyze/` | AI 分析 SQL/元数据(需 LLM_API_KEY) |
| POST | `/llm/sql-assist/` | AI 辅助写 SQL(generate/optimize/explain, 可带 table_id) |
| POST | `/llm/spark-to-hive/` | AI 把 Spark 代码(Java/Scala/Python)转为 Hive SQL |
| POST | `/llm/oracle-to-hive/` | AI 把 Oracle 存储过程(PL/SQL)转为 Hive SQL |
| GET | `/docs/` / `/docs/file/?name=` | 文档列表/内容(HTML) |
| GET | `/ops/summary/?days=7` | 运营看板汇总 |

## 9. 脚本管理

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/scripts/` | 脚本列表(按目录分组) |
| GET | `/scripts/file/?path=tools/x.py` | 读取脚本内容 |
| POST | `/scripts/save/` | 保存脚本 |
| POST | `/scripts/create/` | 新建脚本 |
| POST | `/scripts/delete/` | 删除脚本 |
| POST | `/scripts/run/` | 运行脚本(`path`, `args`, `timeout`) |
| GET | `/scripts/runs/` | 运行历史 |

受管目录: `tools/` `etl/` `flink_sql/` `doris_sql/` `hive_sql/`, 仅支持 `.sh` / `.py`。

## 10. 调度中心

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/scheduler/jobs/` | 调度任务列表(含最近执行) |
| POST | `/scheduler/jobs/create/` | 新建(script/etl, cron 时/分, args) |
| POST | `/scheduler/jobs/<id>/update/` | 更新(自动同步 crontab) |
| POST | `/scheduler/jobs/<id>/delete/` | 删除(移除 crontab 行) |
| POST | `/scheduler/jobs/<id>/run/` | 立即执行 |
| GET | `/scheduler/runs/?job=` | 执行历史 |
| POST | `/scheduler/cron/refresh/` | 重建全部启用任务的 crontab 行 |

命令行: `python manage.py scheduler_run --job <id>`(crontab 使用)。

```bash
curl -X POST http://127.0.0.1:8000/api/metadata/llm/analyze/ \
  -H "Content-Type: application/json" \
  -d '{"kind":"sql","sql":"SELECT * FROM t LIMIT 10","table_id":3}'
```

## 通用响应格式

```json
{"code": 0, "message": "ok", "data": {...}}
```

- `code = 0` 成功; 400 参数错误; 404 不存在; 409 前置校验未通过; 500 服务/执行失败
- 对账任务执行后 `data.status`: `success` / `failed`; `data.summary` 含 ok/mismatch 统计

## 环境变量(可选能力)

| 变量 | 作用 |
| --- | --- |
| `LLM_API_KEY` (或 `DEEPSEEK_API_KEY`) | DeepSeek API Key(默认; 申请: https://platform.deepseek.com/) |
| `LLM_BASE_URL` / `LLM_MODEL` | 默认 `https://api.deepseek.com/v1` / `deepseek-chat`, 可指向任意 OpenAI 兼容服务 |
| `SQL_FILE_HOST` / `SQL_FILE_USER` / `SQL_FILE_PASSWORD` / `SQL_FILE_KEY` / `SQL_FILE_DIR` | SQL 文件库远程模式 |
| `RECONCILE_WEBHOOK` | 对账告警 webhook |
| `DATAX_HOME` | DataX 执行 |
