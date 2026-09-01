-- =====================================================================
-- MySQL -> Canal -> Kafka -> Flink SQL -> Doris
-- 文件名: mysql_canal_kafka2doris.sql
-- =====================================================================
--
-- 【数据链路】
--   MySQL binlog
--     -> Canal (伪装 MySQL slave 解析 binlog, 输出 canal-json 到 Kafka)
--     -> Kafka topic: mysql_canal.users
--     -> Flink SQL: kafka source(format=canal-json) 解析 changelog
--     -> Doris sink: Unique Key 模型表, 支持 INSERT/UPDATE/DELETE
--
-- 【版本信息】(与 postgresql_debezium_kafka2doris.sql 同一套环境)
--   Flink            : 1.20.5 standalone (/opt/flink)
--   Kafka            : 2.13-4.3.1 (192.168.3.100:9092)
--   Canal            : 1.1.x (deployer 输出 json 到 Kafka)
--   Doris            : 2.1.11 (FE MySQL 9030 / FE HTTP 8030)
--   Kafka connector  : flink-sql-connector-kafka-3.4.0-1.20.jar
--   Doris connector  : flink-doris-connector-1.20-25.1.0.jar
--
-- 【与 PG 文件的区别】
--   - 源格式是 canal-json 而不是 debezium-json
--   - Canal 的 JSON 结构: {"data":[{...}],"old":[{...}],"type":"INSERT"/"UPDATE"/"DELETE",...}
--   - canal-json 同样需要声明 PRIMARY KEY 才能生成 +I/-U/+U/-D changelog
--
-- =====================================================================
-- 一、前置条件
-- =====================================================================
--
-- 1) MySQL 建表 (示例)
--    CREATE TABLE `users` (
--        id          BIGINT       NOT NULL,
--        name        VARCHAR(64)  NOT NULL,
--        age         INT          NOT NULL DEFAULT 0,
--        email       VARCHAR(128) NULL,
--        create_time DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
--        update_time DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
--        PRIMARY KEY (id)
--    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
--
-- 2) Canal 配置要点 (conf/canal.properties + 实例 properties)
--    canal.serverMode = kafka
--    canal.mq.topic   = mysql_canal.users        (可按表指定)
--    canal.mq.flatMessage = true                  (输出扁平 JSON)
--    canal.instance.master.address = 192.168.3.100:3306
--    canal.instance.dbUsername / dbPassword
--    canal.instance.filter.regex = test_db\\..*     (库表过滤)
--
-- 3) Doris 建表 (Unique Key, 支持 upsert + delete)
--    CREATE TABLE test_db.users (
--        id          BIGINT NOT NULL,
--        name        VARCHAR(64) NOT NULL,
--        age         INT NOT NULL,
--        email       VARCHAR(128),
--        create_time DATETIME(3) NOT NULL,
--        update_time DATETIME(3) NOT NULL
--    ) UNIQUE KEY(id)
--      DISTRIBUTED BY HASH(id) BUCKETS 1
--      PROPERTIES ("replication_num" = "1");
--
-- =====================================================================
-- 二、全局参数
-- =====================================================================
SET 'execution.runtime-mode' = 'STREAMING';
SET 'pipeline.name' = 'mysql-canal-kafka-to-doris';
SET 'parallelism.default' = '1';
SET 'table.local-time-zone' = 'Asia/Shanghai';

SET 'execution.checkpointing.interval' = '10000';
SET 'execution.checkpointing.mode' = 'EXACTLY_ONCE';
SET 'execution.checkpointing.min-pause' = '5000';
SET 'execution.checkpointing.externalized-checkpoint-retention' = 'RETAIN_ON_CANCELLATION';
SET 'state.backend' = 'rocksdb';
SET 'state.checkpoints.dir' = 'file:///data/flink/checkpoint/mysql2doris';

-- =====================================================================
-- 三、Kafka 源表 (canal-json)
-- =====================================================================
-- 注意:
-- 1) canal-json 里时间字段是 'yyyy-MM-dd HH:mm:ss.SSS' 格式,
--    表字段用 TIMESTAMP_LTZ(3)/TIMESTAMP(3) 即可
-- 2) 必须声明 PRIMARY KEY, 否则 UPDATE/DELETE 无法映射成 changelog
CREATE TABLE mysql_kafka_source (
    id          BIGINT,
    name        STRING,
    age         INT,
    email       STRING,
    create_time TIMESTAMP_LTZ(3),
    update_time TIMESTAMP_LTZ(3),
    PRIMARY KEY (id) NOT ENFORCED
) WITH (
    'connector'                    = 'kafka',
    'topic'                        = 'mysql_canal.users',
    'properties.bootstrap.servers' = '192.168.3.100:9092',
    'properties.group.id'          = 'flink_mysql2doris_group',
    'scan.startup.mode'            = 'latest-offset',
    'format'                       = 'canal-json',
    'canal-json.ignore-parse-errors' = 'false'
);

-- =====================================================================
-- 四、Doris 目标表
-- =====================================================================
-- Doris connector 25.x 选项, 详见 postgresql_debezium_kafka2doris.sql
CREATE TABLE doris_mysql_target (
    id          BIGINT,
    name        STRING,
    age         INT,
    email       STRING,
    create_time TIMESTAMP_LTZ(3),
    update_time TIMESTAMP_LTZ(3),
    PRIMARY KEY (id) NOT ENFORCED
) WITH (
    'connector'                = 'doris',
    'fenodes'                  = '192.168.3.100:8030',
    'table.identifier'         = 'test_db.users',
    'username'                 = 'root',
    'password'                 = '',
    'sink.label-prefix'        = 'flink_mysql2doris_',
    'sink.enable.batch-mode'   = 'false',
    'sink.properties.format'   = 'json',
    'sink.properties.read_json_by_line' = 'true'
);

-- =====================================================================
-- 五、同步 SQL
-- =====================================================================
-- Canal 的 delete 消息只有主键 + old 字段, 由 canal-json 自动生成 -D 行,
-- Doris Unique Key 表直接消费即可, 无需特殊处理
INSERT INTO doris_mysql_target
SELECT
    id,
    name,
    age,
    email,
    create_time,
    update_time
FROM mysql_kafka_source;

-- =====================================================================
-- 六、常见问题 FAQ
-- =====================================================================
-- Q1: 报错 "JSON parser error" / 数据不进
--     检查 Canal 是否开了 flatMessage=true, canal-json 需要扁平结构
--
-- Q2: UPDATE 到了 Doris 没变化
--     确认 source 表声明了 PRIMARY KEY, 且 Doris 是 Unique Key 表
--
-- Q3: 时间字段差 8 小时
--     确认 SET table.local-time-zone = 'Asia/Shanghai', 并检查 canal 实例
--     是否配置了时区(canal.instance.connectionCharset)
--
-- Q4: Doris connector 报 Unsupported options
--     25.x 不再支持 sink.batch.size / sink.enable-2pc 等旧选项
--
-- =====================================================================
