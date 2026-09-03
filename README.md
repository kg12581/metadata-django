# metadata-django

元数据采集平台(Django): 定时/手动把远端数据库(MySQL / PostgreSQL)的**表结构元数据**
(库、表、字段、索引、约束、注释)同步到 Django 自己的表中, 并通过 REST API 对外提供查询。

## 📚 文档导航

| 文档 | 说明 |
| --- | --- |
| [docs/01-architecture.md](docs/01-architecture.md) | 架构图 / 模块地图 / 页面与定时任务清单 |
| [docs/02-tech-stack-map.md](docs/02-tech-stack-map.md) | 大数据开发技术栈对照与扩展建议(Roadmap) |
| [docs/03-official-docs-and-links.md](docs/03-official-docs-and-links.md) | 官方文档与学习资源链接大全 |
| [docs/04-api-reference.md](docs/04-api-reference.md) | API 调用文档(全部接口 + curl 示例) |
| [mcp/README.md](mcp/README.md) | MCP 服务接入与 Tools 清单 |

> 面向大数据开发场景: 元数据采集 → 结构校验/自动 DDL → Flink 实时 + T+1 批量双链路增量,
> DataX 离线同步, Doris/Hive SQL 资产沉淀。技术栈逐层对照见 docs/02。

## 功能

- 支持读取 MySQL / PostgreSQL 的 information_schema 元数据
- 同步数据源、表、字段、索引、约束到 Django 模型
- 幂等同步: 重复执行按唯一键更新, 自动清理远端已删除的表/字段/索引/约束
- 内置 Web 界面(数据源总览/表列表/表详情) + REST API + Django Admin
- 页面定时自动同步(默认每 10 分钟, 可开关/调间隔)
- 单个数据源元数据导出 Excel(.xlsx, 表/字段/索引/约束 四个工作表)
- 行数对账: `manage.py reconcile_counts`(MySQL/PG vs Doris, 可选 webhook 告警)
- 对账中心: 行数 / 主键快照 / 字段值 / 业务指标 / 元数据 五种对账(页面 + API)
- SQL 文件库(本地目录或远程 Linux SFTP) + SQL 血缘解析 + 大模型分析
- Markdown 文档在线查看(/docs/)
- 服务端埋点与运营看板(/ops/)
- MCP 服务: 平台 API 暴露为 MCP tools(`mcp/server.py`)
- 脚本管理平台: 集中浏览/编辑/运行 shell 与 python 脚本(/scripts/)
- 自动化测试: pytest 套件(见 `testcase/`), 含 HTML 报告与页面截图

### 测试与报告

```bash
pip install -r requirements-dev.txt
python -m pytest testcase -q --html=testcase/reports/report.html --self-contained-html
```

31 项用例覆盖: 模型加密、schema 类型映射/差异、血缘解析、Debezium/ETL 逻辑、
API 冒烟、页面快照、调度/脚本安全。报告与截图见 `testcase/reports/`、`testcase/screenshots/`,
详情见 [docs/05-testing.md](docs/05-testing.md)。

### 部署(可选)

```bash
docker compose up -d --build   # PostgreSQL + gunicorn
```

生产环境变量: `DJANGO_SECRET_KEY` / `DJANGO_DEBUG=0` / `DJANGO_ALLOWED_HOSTS` /
`DJANGO_DB_ENGINE=postgres` 等(见 [core/settings.py](core/settings.py)); 健康检查 `/healthz/`。

## 快速开始

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # 按需修改连接配置
python manage.py migrate
python manage.py runserver
```

打开 http://127.0.0.1:8000/docs/ 在线查看文档(含 [API 调用文档](docs/04-api-reference.md))。

## Web 界面

浏览器打开 http://127.0.0.1:8000/ 即可使用:

- `/` — 数据源总览, 一键「立即同步」
- `/schema-sync/` — 结构同步定时任务管理(配置/保存 crontab/立即执行/日志)
- `/datax/` — DataX 同步管理(MySQL -> Doris: 结构校验/生成 job/执行)
- `/etl/` — ETL 管理(Kafka Debezium -> Doris: 配置/后台运行/日志)
- `/flink-sql/` — Flink SQL 实时 CDC 作业文件查看
- `/sources/` — 元数据源配置(MySQL/PG/Oracle/Hive/Doris/ClickHouse/DB2/ODPS/OceanBase/GaussDB/DWS/openGauss 等, JDBC)
- `/sql-helper/` — SQL 助手: 选库选表一键生成 SELECT/INSERT/UPDATE/DELETE/COUNT
- `/dictionary/` — 数据字典: 字段级字典浏览/搜索/导出 Excel
- `/ai-sql/` — AI 辅助写 SQL(生成/优化/解释, 可关联元数据上下文)
- `/spark2sql/` — Spark 代码 → Hive SQL(Java/Scala/Python, AI 转换)
- `/oracle2hive/` — Oracle 存储过程 → Hive SQL(AI 转换)
- `/scheduler/` — 调度中心: 调度脚本管理中的 shell/python 与 ETL 脚本(cron 写 crontab)
- `/reconcile/` — 数据对账中心(五种对账任务)
- `/sql-files/` — SQL 文件库(可配置远程 Linux 目录)
- `/lineage/` — SQL 血缘关系
- `/docs/` — 在线文档
- `/ops/` — 运营看板(请求量/成功率/热点接口/错误)
- `/scripts/` — 脚本管理(shell/python: 查看/编辑/运行/历史)
- `/databases/<id>/` — 某数据源下的表列表(支持按表名/注释搜索)
- `/tables/<id>/` — 表详情: 字段/索引/约束

界面为 Django 模板实现(位于项目根目录 `templates/common/`), 无外部 CDN 依赖, 可离线使用。

## Flink SQL 实时 CDC 作业 (flink_sql/)

[flink_sql/](flink_sql/) 下两个 Flink SQL 实时作业(与 `etl/` 的 T+1 批量互补):

| 文件 | 链路 | pipeline.name |
| --- | --- | --- |
| `postgresql_debezium_kafka2doris.sql` | PostgreSQL -> Debezium -> Kafka -> Flink -> Doris | `pg-debezium-kafka-to-doris` |
| `mysql_canal_kafka2doris.sql` | MySQL -> Canal -> Kafka -> Flink -> Doris | `mysql-canal-kafka-to-doris` |

提交 / 停止(需 Flink standalone, 默认 `/opt/flink`):

```bash
./flink_sql/submit_flink_sql.sh postgresql_debezium_kafka2doris.sql
./flink_sql/submit_flink_sql.sh mysql_canal_kafka2doris.sql
./flink_sql/stop_flink_sql.sh "pg-debezium-kafka-to-doris"
```

环境版本、建表要求、字段变更指南、FAQ 见各 .sql 文件头注释与 [flink_sql/README.md](flink_sql/README.md)。

### 定时自动同步

页面顶部的「定时自动同步」开关(默认每 10 分钟, 可选 5/10/30/60 分钟)会在
**页面打开期间**自动调用同步接口, 设置保存在浏览器 localStorage 中。

如果希望**不打开页面也定时同步**, 用内置管理命令 + crontab:

```bash
python manage.py sync_metadata            # 同步全部业务库
python manage.py sync_metadata --schema hive_metastore  # 只同步指定库
```

crontab 示例(每 10 分钟):

```cron
*/10 * * * * cd /Users/kgt/code/metadata-django && .venv/bin/python manage.py sync_metadata >> /tmp/metadata_sync.log 2>&1
```

### 导出 Excel

数据源详情页点击「导出 Excel」, 或直接访问:

```text
GET /api/metadata/databases/<id>/export/
```

导出文件包含四个工作表: 表、字段、索引、约束。

## MySQL -> Doris 结构校验与 DataX 同步

先校验 MySQL 与 Doris 表结构是否一致, 一致才执行 DataX 同步表数据。

### 配置

```ini
DORIS_HOST=192.168.3.100
DORIS_PORT=9030
DORIS_USER=root
DORIS_PASSWORD=
DORIS_DATABASE=test_db
DATAX_HOME=/opt/datax          # DataX 安装目录(bin/datax.py), 未配置则无法执行
DATAX_PYTHON=python3
```

### 1. 结构校验

```bash
curl -X POST http://127.0.0.1:8000/api/metadata/datax/check/ \
  -H "Content-Type: application/json" \
  -d '{"database": "ai_chatbot", "table": "analytics_event", "doris_database": "test_db"}'
```

返回 `data.consistent`(true/false) 及每张表的差异明细:
字段缺失/多余、类型不一致、可空性/顺序差异(警告)。

### 2. 校验通过后同步

```bash
curl -X POST http://127.0.0.1:8000/api/metadata/datax/sync/ \
  -H "Content-Type: application/json" \
  -d '{"database": "ai_chatbot", "table": "analytics_event", "doris_database": "test_db"}'
```

请求体参数:

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `table` / `tables` | 必填 | 单表或表名数组 |
| `doris_database` | `DORIS_DATABASE` | Doris 目标库 |
| `truncate` | `true` | 同步前 TRUNCATE 目标表 |
| `channel` | `3` | DataX 并发通道数 |
| `force` | `false` | `true` 时跳过结构校验直接同步 |
| `preview` | `false` | `true` 时只返回生成的 DataX job, 不执行 |
| `split_pk` | 空 | 分片主键(可选) |

校验不一致时接口返回 **409**, 不会执行 DataX; 需先解决结构差异, 或显式传 `force=true`。

### 执行脚本 (推荐)

项目内置了 [tools/datax_sync.py](tools/datax_sync.py): 先调 Django 校验接口,
结构一致(consistent=true) 才执行 DataX, 不一致自动拦截并打印差异。

```bash
# 1. 校验 -> 通过后从接口获取 job 并执行 DataX
python tools/datax_sync.py --database ai_chatbot --table analytics_event --doris-database test_db

# 2. 只校验 + 生成 job, 不执行
python tools/datax_sync.py --database ai_chatbot --table analytics_event --doris-database test_db --no-run

# 3. 使用已生成的 job 文件执行
python tools/datax_sync.py --database ai_chatbot --table analytics_event \
  --job-file datax/jobs/ai_chatbot_analytics_event.json

# 4. 跳过校验强制同步
python tools/datax_sync.py --database ai_chatbot --table analytics_event --doris-database test_db --force
```

脚本参数: `--api-url`(默认 http://127.0.0.1:8000)、`--channel`、`--split-pk`、
`--no-truncate`、`--datax-home` / `--datax-python`(也可用环境变量 `DATAX_HOME`/`DATAX_PYTHON`)、
`--timeout`。

预生成的示例 job 在 [datax/jobs/ai_chatbot_analytics_event.json](datax/jobs/ai_chatbot_analytics_event.json)
(含数据库连接信息, 该目录已加入 `.gitignore` 不会提交)。

## ETL: Kafka(PG Debezium) -> Doris 每日 T+1 增量同步

代码位于 [etl/](etl/):

- [etl/etl_kafka_doris.py](etl/etl_kafka_doris.py) — ETL 主程序: 消费 Kafka
  Debezium 变更事件(topic 形如 `cdcpg.public.orders`), 按事件时间过滤指定日期,
  增量写入 Doris(upsert / delete / truncate), 完成后提交 Kafka offset
- [etl/run_daily_t1.sh](etl/run_daily_t1.sh) — T+1 调度脚本, 每天处理昨天一天的数据
- [etl/config.json](etl/config.json) — topic -> Doris 表映射及连接配置

运行:

```bash
python etl/etl_kafka_doris.py                      # 处理昨天
python etl/etl_kafka_doris.py --date 2026-08-30    # 指定日期补数
python etl/etl_kafka_doris.py --dry-run            # 只统计不写 Doris
./etl/run_daily_t1.sh                              # T+1 调度(写 logs/etl_<日期>.log)
```

crontab 每天 01:30:

```cron
30 1 * * * /Users/kgt/code/metadata-django/etl/run_daily_t1.sh >> /Users/kgt/code/metadata-django/logs/cron_t1.log 2>&1
```

要求: Doris 目标表为 Unique Key 模型; 依赖 `kafka-python`; 更多说明见 [etl/README.md](etl/README.md)。

## MySQL -> Doris 表结构自动同步 (schema-sync)

根据 MySQL 元数据自动对齐 Doris 表结构:

- Doris 表不存在 -> 自动建表(Unique Key 模型, 主键取 MySQL 主键)
- MySQL 有、Doris 没有的字段 -> `ADD COLUMN`
- Doris 有、MySQL 没有的字段 -> `DROP COLUMN`(可用 `drop_columns=false` 关闭)
- 类型/长度/可空性不一致 -> `MODIFY COLUMN`(自动做 MySQL -> Doris 类型映射)

### API

```bash
# 预览(默认, 不执行任何 DDL)
curl -X POST http://127.0.0.1:8000/api/metadata/schema-sync/ \
  -H "Content-Type: application/json" \
  -d '{"database": "ai_chatbot", "table": "analytics_event", "doris_database": "test_db"}'

# 执行(真正在 Doris 上变更结构)
curl -X POST http://127.0.0.1:8000/api/metadata/schema-sync/ \
  -H "Content-Type: application/json" \
  -d '{"database": "ai_chatbot", "tables": ["analytics_event", "auth_user"], "doris_database": "test_db", "preview": false}'
```

请求体参数: `table` / `tables`、`doris_database`、`preview`(默认 true)、
`drop_columns`(默认 true)、`auto_create`(默认 true)。

### 前端按钮

- 表详情页: 「预览结构变更」/「执行结构变更」
- 库详情页: 「预览全部」/「执行全部」(对整库所有表批量对齐)

### 定时任务管理页面

访问 http://127.0.0.1:8000/schema-sync/ (顶部导航「结构同步任务」):

- 配置: MySQL 源库、表名列表、Doris 目标库、是否执行 DDL、每天执行时间(时/分)、启用开关
- 「保存配置」会把任务写入 `tools/schema_sync_task.json` 并自动更新 **crontab**
- 「立即预览」/「立即执行」按任务配置即时运行
- 「查看最近日志」展示 `logs/schema_sync_*.log` 尾部

相关 API: `GET/POST /api/metadata/schema-sync/task/`、`POST /api/metadata/schema-sync/task/save/`、
`POST /api/metadata/schema-sync/run/`、`GET /api/metadata/schema-sync/log/`。

### 定时执行 (管理命令)

```bash
python manage.py schema_sync --database ai_chatbot --tables analytics_event --doris-database test_db
python manage.py schema_sync --database ai_chatbot --tables t1,t2 --apply
```

默认只预览, 加 `--apply` 才执行。crontab 示例(每天 03:00 自动对齐):

```cron
0 3 * * * cd /Users/kgt/code/metadata-django && .venv/bin/python manage.py schema_sync --database ai_chatbot --tables analytics_event --doris-database test_db --apply >> logs/schema_sync.log 2>&1
```

也可用封装脚本 `tools/run_schema_sync.sh`(读取任务配置文件, 环境变量可覆盖):

```bash
./tools/run_schema_sync.sh          # 按 tools/schema_sync_task.json 执行
SCHEMA_SYNC_APPLY=0 ./tools/run_schema_sync.sh   # 只预览
```

## 连接配置 (.env)

| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| `DB_TYPE` | `mysql` 或 `postgresql` | `mysql` |
| `DB_HOST` | 远端数据库主机 | `192.168.3.100` |
| `DB_PORT` | 远端数据库端口 | `3306` |
| `DB_USER` | 用户名 | `root` |
| `DB_PASSWORD` | 密码 | - |
| `DB_NAME` | 连接使用的数据库(MySQL 可用 `mysql`, PostgreSQL 用实际库名) | `mysql` |
| `DB_SCHEMA` | 只同步指定 schema(库), 留空同步全部业务库 | 空 |

`.env` 已加入 `.gitignore`, 不会提交到版本库。**生产环境请勿在请求体中携带明文密码**,
建议改用环境变量注入。

## REST API

所有接口前缀为 `/api/metadata/`:

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/metadata/` | 接口列表 |
| GET | `/api/metadata/databases/` | 已同步的数据源列表(含表数) |
| GET | `/api/metadata/databases/<id>/` | 数据源详情(含全部表) |
| GET | `/api/metadata/tables/<id>/` | 表详情(字段/索引/约束) |
| POST | `/api/metadata/sync/` | 触发同步(可覆盖连接配置) |

### 触发同步

```bash
curl -X POST http://127.0.0.1:8000/api/metadata/sync/
```

请求体可选覆盖配置(不传则使用 `.env`):

```json
{
  "db_type": "mysql",
  "host": "192.168.3.100",
  "port": 3306,
  "user": "root",
  "password": "***",
  "database": "mysql",
  "schema": "hive_metastore"
}
```

## Django Admin

访问 http://127.0.0.1:8000/admin/ 可浏览/检索元数据, 需先创建管理员:

```bash
python manage.py createsuperuser
```

## 项目结构

```text
core/                 Django 项目配置(settings/urls/wsgi/asgi)
api/                 对外 REST 接口(路由 api/urls.py, 视图复用 common.views)
templates/common/     Web 界面模板
doris_sql/            Doris 建表/变更模板 + MySQL->Doris DDL 生成脚本
hive_sql/             Hive 外部表模板 + MySQL->Hive DDL 生成脚本
common/
  models.py           元数据模型(库/表/字段/索引/约束)
  readers/            MySQL / PostgreSQL 元数据读取器
  services/sync.py    同步服务(远端 -> Django 表)
  views.py            业务视图(页面 + 接口实现)
  config.py           .env / 环境变量配置
```
