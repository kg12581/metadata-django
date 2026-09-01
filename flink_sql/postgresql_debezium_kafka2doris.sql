-- =====================================================================
-- PostgreSQL -> Debezium -> Kafka -> Flink SQL -> Doris
-- 文件名: postgresql_debezium_kafka2doris.sql
-- =====================================================================
--
-- 【数据链路】
--   PostgreSQL (WAL, 逻辑复制)
--     -> Debezium Connect (CDC 采集, 输出 Debezium JSON 到 Kafka)
--     -> Kafka topic: <topic.prefix>.<schema>.<table>  例如 cdcpg.public.orders
--     -> Flink SQL: kafka source(format=debezium-json) 解析 changelog
--     -> Doris sink: Unique Key 模型表, 支持 INSERT/UPDATE/DELETE
--
-- 【版本信息】(已在 Rocky 9.8 / 192.168.3.100 上验证通过)
--   Flink            : 1.20.5 standalone (/opt/flink, Web UI: http://192.168.3.100:8081)
--   PyFlink(可选)    : 1.20.5 (/root/pyflink-venv, 本地跑 SQL 用)
--   Kafka            : 2.13-4.3.1 (192.168.3.100:9092)
--   Debezium Connect : 3.6.1.Final (docker, http://192.168.3.100:8083)
--   Doris            : 2.1.11 (FE MySQL 9030 / FE HTTP 8030 / BE 8040)
--   Kafka connector  : flink-sql-connector-kafka-3.4.0-1.20.jar
--                      (注意: Flink 1.20 对应的 Kafka connector 版本号是 3.4.0-1.20,
--                       不是 1.20.5, maven 坐标:
--                       org.apache.flink:flink-sql-connector-kafka:3.4.0-1.20)
--   Doris connector  : flink-doris-connector-1.20-25.1.0.jar
--                      (maven 坐标: org.apache.doris:flink-doris-connector-1.20:25.1.0,
--                       建议用阿里云镜像下载, 服务器直连 maven central 较慢)
--
-- 【依赖 jar 放置位置】
--   本地跑/standalone 提交时, 将下面两个 jar 放到 /opt/flink/lib:
--     /opt/flink/lib/flink-sql-connector-kafka-3.4.0-1.20.jar
--     /opt/flink/lib/flink-doris-connector-1.20-25.1.0.jar
--   放到 lib 后需要重启 Flink 集群才生效:
--     /opt/flink/bin/stop-cluster.sh && /opt/flink/bin/start-cluster.sh
--
-- =====================================================================
-- 一、前置条件 (PG / Debezium / Doris)
-- =====================================================================
--
-- 1) PostgreSQL 建表 + 关键设置
--    ---------- PG 建表 (示例) ----------
--    CREATE TABLE public.orders (
--        id         INTEGER         NOT NULL,
--        product    VARCHAR(100)    NOT NULL,
--        quantity   INTEGER         NOT NULL DEFAULT 0,
--        price      NUMERIC(10,2)   NOT NULL DEFAULT 0,
--        updated_at TIMESTAMPTZ     NOT NULL DEFAULT now(),
--        PRIMARY KEY (id)
--    );
--
--    ---------- 必须执行: REPLICA IDENTITY FULL ----------
--    ALTER TABLE public.orders REPLICA IDENTITY FULL;
--    原因: 默认(主键)级别下, Debezium 的 UPDATE 消息 before 为 null,
--          Flink debezium-json 格式解析 UPDATE 时要求 before 完整,
--          否则作业报错:
--          "The before field of UPDATE message is null ... please check
--           the Postgres table has been set REPLICA IDENTITY to FULL level"
--
-- 2) Debezium Connect 注册 connector (POST /connectors)
--    {
--      "name": "cdc-demo-postgres",
--      "config": {
--        "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
--        "database.hostname": "192.168.3.100",
--        "database.port": "5432",
--        "database.user": "debezium",
--        "database.password": "debezium",
--        "database.dbname": "cdc_demo",
--        "topic.prefix": "cdcpg",
--        "table.include.list": "public.orders",
--        "plugin.name": "pgoutput",
--        "publication.autocreate.mode": "filtered",
--        "publication.name": "dbz_publication",
--        "slot.name": "cdc_demo_slot",
--        "snapshot.mode": "initial",
--        "decimal.handling.mode": "string",
--        "tasks.max": "1"
--      }
--    }
--    说明:
--    - topic 命名: <topic.prefix>.<schema>.<table> => cdcpg.public.orders
--    - decimal.handling.mode=string: 小数以字符串形式输出(如 "1234.56"),
--      与下方 source 表 price 定义为 STRING 对应
--
-- 3) Doris 建表 (Unique Key 模型, 支持 upsert + delete)
--    ---------- 执行: mysql -h127.0.0.1 -P9030 -uroot ----------
--    CREATE TABLE test_db.orders (
--        id         INT NOT NULL,
--        product    VARCHAR(100) NOT NULL,
--        quantity   INT NOT NULL,
--        price      DECIMAL(10,2) NOT NULL,
--        updated_at DATETIME(6) NOT NULL
--    ) UNIQUE KEY(id)
--      DISTRIBUTED BY HASH(id) BUCKETS 1
--      PROPERTIES ("replication_num" = "1");
--    说明:
--    - 必须用 UNIQUE KEY 模型(默认开启 merge-on-write), 才能正确同步
--      Debezium 的 UPDATE / DELETE
--    - 字段类型要和 Flink sink 表对齐: DECIMAL(10,2) <-> DECIMAL(10,2),
--      DATETIME(6) <-> STRING(导入时由 Doris 解析)
--
-- =====================================================================
-- 二、全局参数
-- =====================================================================

-- 流式模式(默认就是 streaming, 显式声明更清晰)
SET 'execution.runtime-mode' = 'STREAMING';

SET 'pipeline.name' = 'pg-debezium-kafka-to-doris';
-- 按实际资源调整, 生产可给 2~4
SET 'parallelism.default' = '1';

-- 时区: Debezium 输出的 timestamptz 是 UTC(ISO-8601 带 Z),
-- 这里声明本地时区, 让 DATE_FORMAT 输出北京时间
SET 'table.local-time-zone' = 'Asia/Shanghai';

-- Checkpoint: Doris sink 依赖 checkpoint 做两阶段提交/幂等
SET 'execution.checkpointing.interval' = '10000';
SET 'execution.checkpointing.mode' = 'EXACTLY_ONCE';
SET 'execution.checkpointing.timeout' = '300000';
SET 'execution.checkpointing.min-pause' = '5000';
SET 'execution.checkpointing.max-concurrent-checkpoints' = '1';
SET 'execution.checkpointing.externalized-checkpoint-retention' = 'RETAIN_ON_CANCELLATION';

-- 状态后端: 生产建议 RocksDB
SET 'state.backend' = 'rocksdb';
-- 或 hdfs://...
SET 'state.checkpoints.dir' = 'file:///data/flink/checkpoint/pg2doris';
SET 'state.backend.rocksdb.localdir' = '/data/flink/rocksdb';

-- Kafka 分区长时间无新数据时保持源不空闲退出
SET 'table.exec.source.idle-timeout' = '60s';
SET 'table.exec.source.idle-state.retention' = '1h';

-- =====================================================================
-- 三、Kafka 源表 (debezium-json)
-- =====================================================================
-- 注意:
-- 1) 所有 key 必须用 ASCII 连字符 '-' (不要复制非断行连字符 U+2011, 会解析失败)
-- 2) 必须声明 PRIMARY KEY, debezium-json 才能把 op 映射成 +I/-U/+U/-D changelog
-- 3) timestamp-format.standard 必须设 ISO-8601, 否则解析
--    "2026-08-29T11:35:34.080617Z" 这种时间会失败
-- 4) price 定义成 STRING: Debezium 配了 decimal.handling.mode=string
CREATE TABLE pg_kafka_source (
    id         INT,
    product    STRING,
    quantity   INT,
    price      STRING,             -- Debezium decimal string 模式
    updated_at TIMESTAMP_LTZ(6),   -- timestamptz -> ISO-8601 UTC
    PRIMARY KEY (id) NOT ENFORCED
) WITH (
    'connector'                    = 'kafka',
    'topic'                        = 'cdcpg.public.orders',
    'properties.bootstrap.servers' = '192.168.3.100:9092',
    'properties.group.id'          = 'flink_pg2doris_group',
    'scan.startup.mode'            = 'latest-offset',   -- 全量重放用 earliest-offset
    'format'                       = 'debezium-json',
    'debezium-json.timestamp-format.standard' = 'ISO-8601',
    -- 可选: 容忍个别脏消息(解析失败静默跳过), 生产建议先不开, 让问题暴露
    'debezium-json.ignore-parse-errors'       = 'false'
);

-- =====================================================================
-- 四、Doris 目标表
-- =====================================================================
-- 注意:
-- 1) Doris connector 25.x 的选项和旧版(1.x/24.x 早期)不同:
--    - 流式模式用 sink.enable.batch-mode = 'false' (默认)
--    - 不再支持 sink.batch.size / sink.batch.interval /
--      sink.buffer-flush.max-rows / sink.buffer-flush.interval-ms /
--      sink.enable-2pc 这些旧选项, 写了会报 "Unsupported options"
-- 2) delete 不需要额外开关: Unique Key 模型表默认支持, 提交 delete 即可
-- 3) JSON 格式导入时不需要 column_separator/line_delimiter(那是 CSV 的)
CREATE TABLE doris_pg_target (
    id         INT,
    product    STRING,
    quantity   INT,
    price      DECIMAL(10, 2),
    updated_at STRING,
    PRIMARY KEY (id) NOT ENFORCED
) WITH (
    'connector'                = 'doris',
    'fenodes'                  = '192.168.3.100:8030',      -- FE HTTP 端口
    'table.identifier'         = 'test_db.orders',
    'username'                 = 'root',
    'password'                 = '',
    'sink.label-prefix'        = 'flink_pg2doris_',         -- 保证幂等, 需全局唯一
    'sink.enable.batch-mode'   = 'false',                   -- false=流式(两阶段提交)
    'sink.max-retries'         = '3',
    'sink.properties.format'   = 'json',
    'sink.properties.read_json_by_line' = 'true'
);

-- =====================================================================
-- 五、同步 SQL
-- =====================================================================
-- 1) price: Debezium 输出字符串, CAST 成 DECIMAL; 非法数字(如历史脏数据)
--    通过正则过滤掉, 不让作业挂
-- 2) updated_at: ISO-8601 UTC -> 按 Asia/Shanghai 格式化成
--    'yyyy-MM-dd HH:mm:ss.SSSSSS', 与 PG 里看到的 +08 时间一致
-- 3) 正则转义: Flink SQL 字符串里写一个反斜杠 \. 即可;
--    若写 \\ 会被 Java 正则当成"匹配反斜杠", 导致所有行被过滤
INSERT INTO doris_pg_target
SELECT
    id,
    product,
    quantity,
    CAST(price AS DECIMAL(10, 2)) AS price,
    DATE_FORMAT(updated_at, 'yyyy-MM-dd HH:mm:ss.SSSSSS') AS updated_at
FROM pg_kafka_source
WHERE price IS NOT NULL
  AND REGEXP(price, '^[0-9]+(\.[0-9]+)?$');

-- =====================================================================
-- 六、常见问题 FAQ
-- =====================================================================
--
-- Q1: 作业报 "The before field of UPDATE message is null"
--     原因: PG 表 REPLICA IDENTITY 不是 FULL, UPDATE 消息没有完整 before
--     解决: ALTER TABLE public.orders REPLICA IDENTITY FULL;
--           (已存在于 Kafka 里的旧消息不会变, 可从 latest-offset 开始消费)
--
-- Q2: Kafka 一直在消费, 但 Doris 一条数据都没有
--     检查顺序:
--       1) 先查 Kafka consumer group 的 LAG 是否为 0 (确认消息已消费)
--       2) 再查 WHERE 正则是否把数据全过滤了
--          正则 '^[0-9]+(\.[0-9]+)?$' 里的反斜杠多写一层就会全滤掉
--       3) 最后确认 Doris sink 是否触发 stream load
--          (Doris FE: SHOW LOAD FROM test_db ORDER BY CreateTime DESC)
--
-- Q3: 找不到 'kafka'/'doris' connector
--     解决: jar 没加载成功。确认 jar 在 /opt/flink/lib, 并重启集群;
--           PyFlink 本地跑时用 env.add_jars("a.jar", "b.jar") 逐个传,
--           不要把一个带分号的字符串传给 add_jars
--
-- Q4: Doris connector 报 "Unsupported options"
--     解决: 25.x 选项列表只有:
--           sink.enable.batch-mode / sink.flush.queue-size /
--           sink.ignore.commit-error / sink.ignore.update-before /
--           sink.label-prefix / sink.max-retries / sink.parallelism /
--           sink.properties.* / sink.use-cache / sink.write-mode
--           旧版的 sink.batch.size / sink.enable-2pc 等已移除
--
-- Q5: 时间比 PG 少 8 小时
--     原因: Debezium 输出 UTC, 未设置本地时区
--     解决: SET table.local-time-zone = 'Asia/Shanghai';
--           并在 SELECT 里用 DATE_FORMAT 格式化
--
-- Q6: 作业启动后立刻失败 "Corrupt Debezium JSON message"
--     原因: 历史消息里 before=null 的 UPDATE, 或 decimal 脏数据
--     解决: 从 earliest-offset 重放前先保证 REPLICA IDENTITY FULL 已设置;
--           只关心新数据用 latest-offset
--
-- Q7: 想同步历史全量数据怎么办
--     解决: 把 scan.startup.mode 改成 'earliest-offset',
--           Debezium snapshot 消息(op=r)会被当成 INSERT 同步进 Doris
--
-- =====================================================================
-- 七、表字段变更指南
-- =====================================================================
--
-- 核心原则: 先改 Doris -> 再改 PG -> 最后改 SQL 文件, 三处一起改, 顺序不能乱。
-- Debezium 不会把 DDL 事件发到数据 topic(Flink 也不消费 schemachange topic),
-- 所以字段变更必须人工改 SQL 和 Doris, 没有自动 schema 同步。
--
-- 示例: 给 orders 表新增字段 remark
--   1) 先改 Doris(先扩容目标, 避免写入失败):
--      ALTER TABLE test_db.orders ADD COLUMN remark VARCHAR(50) NULL;
--   2) 再改 PG:
--      ALTER TABLE public.orders ADD COLUMN remark VARCHAR(50);
--   3) 修改本 SQL 文件三处:
--      source 表:   ..., updated_at TIMESTAMP_LTZ(6), remark STRING, ...
--      Doris 表:    ..., updated_at STRING,           remark STRING, ...
--      INSERT 里:   SELECT id, product, quantity, price, updated_at, remark
--   4) 重启作业:
--      ./stop_flink_sql.sh pg-debezium-kafka-to-doris
--      ./submit_flink_sql.sh streaming/postgresql_debezium_kafka2doris.sql
--
-- 各类变更应对:
--   新增可空字段(需要同步): Doris ADD COLUMN + SQL 三处加字段
--   新增字段(不想同步)    : 不用动, Flink 按 DDL 匹配, 多余字段自动忽略
--   删除字段              : Doris DROP COLUMN + SQL 三处删字段
--   修改类型(int->bigint): 必须两端同时改, 否则 stream load 报
--                           DATA_QUALITY_ERROR: too many filtered rows
--   修改字段名            : 按"删旧字段+加新字段"处理
--
-- 关键坑:
--   1) 顺序: 先 Doris 后 PG 再 SQL, 否则 Doris 少字段 -> 写入失败
--   2) 变更期间 Kafka 会混新旧两种结构消息, 从旧 offset 消费可能报
--      Corrupt Debezium JSON; 稳妥做法: latest-offset 重启(接受空窗),
--      或加 'debezium-json.ignore-parse-errors' = 'true' 跳过旧消息
--   3) 想不丢变更期间数据可从 checkpoint 恢复, 但字段变更后状态 schema
--      可能不兼容; 简单作业(无聚合)问题不大, 复杂作业建议 latest 重启+补数
--
-- ---------------------------------------------------------------------
-- 【场景 A】实时任务运行中, 怎么保证新增字段数据不少
--   核心: Debezium 新消息始终带新字段(在 Kafka 里不会丢), 旧作业只是
--         按自己的 DDL 忽略它。让新作业"重放"变更期间的消息即可补上。
--   推荐做法: 按时间戳启动重放(不需要 checkpoint)
--     1) 变更开始前记一个时间戳: date +%s%3N   (Unix 毫秒, 如 1788050000000)
--     2) ALTER TABLE test_db.orders ADD COLUMN remark VARCHAR(50) NULL;   (Doris 先加列)
--     3) ALTER TABLE public.orders ADD COLUMN remark VARCHAR(50);         (PG)
--     4) SQL 三处加字段, 并把 source 启动方式改成:
--          'scan.startup.mode'             = 'timestamp',
--          'scan.startup.timestamp-millis' = '1788050000000',   -- 步骤 1 记的值
--     5) 停旧作业 -> 提交新作业
--    原理: 新作业从 T0 重放, T0 之前不重放(无新字段), T0 之后全部重放
--          (含变更期间被旧作业忽略的新字段), Doris Unique Key 幂等覆盖,
--          无丢失、无重复。timestamp 取的是 Kafka 消息写入时间, 所以
--          取"变更开始前"即可, 别取 Doris ALTER 之后。
--   备选: 从 checkpoint 恢复
--         SET 'execution.savepoint.path' = 'file:///data/flink/checkpoint/pg2doris/<jobid>/chk-<n>';
--         简单透传作业可行, 复杂作业(聚合/join)状态 schema 可能不兼容。
--
-- ---------------------------------------------------------------------
-- 【场景 B】如果已经先改了 PostgreSQL 字段, 怎么办
--   没破坏数据: 当前作业不会挂(debezium-json 多余字段忽略), 新字段一直
--   在 Kafka 消息里, 补回来即可:
--     1) 确定重放起点 T0(PG 变更时刻):
--        没记录时间戳时, 查 Kafka 第一条带新字段消息的时间:
--        kafka-console-consumer.sh --bootstrap-server localhost:9092 \
--          --topic cdcpg.public.orders --from-beginning --max-messages 2000 \
--          --property print.timestamp=true 2>/dev/null | grep '"remark"' | head -1
--        输出 CreateTime:1788051234567|{...}, 取数字减点余量作为 T0
--     2) ALTER TABLE test_db.orders ADD COLUMN remark VARCHAR(50) NULL;   (Doris 先加列)
--     3) SQL 三处加字段 + 'scan.startup.mode'='timestamp' +
--        'scan.startup.timestamp-millis'=T0
--     4) 停旧作业 -> 提交新作业
--   如果 PG 变更已经很久, 更省事: 直接 earliest 全量重放
--     'scan.startup.mode' = 'earliest-offset',
--     'debezium-json.ignore-parse-errors' = 'true',   -- 跳过历史坏消息
--     数据量小几分钟重放完, Doris 幂等覆盖, 最终和 PG 完全一致。
--
-- =====================================================================
-- 八、验证 (PG 执行 -> 等 10~30 秒 -> Doris 查询)
-- =====================================================================
-- PG:
--   insert into public.orders(product, quantity, price)
--   values ('demo', 5, 88.88);
--   update public.orders set quantity = 6 where product = 'demo';
--   delete from public.orders where product = 'demo';
--
-- Doris:
--   select * from test_db.orders order by id;
--
-- =====================================================================
