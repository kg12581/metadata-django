-- =====================================================================
-- Hive 外部表模板 (ODS 贴源层, ORC + Snappy)
-- 执行: beeline -u jdbc:hive2://192.168.3.100:10000
-- 建议由 hive_sql/generate_ddl.py 根据 MySQL 元数据自动生成
-- =====================================================================

CREATE EXTERNAL TABLE IF NOT EXISTS ods.orders (
    id          BIGINT       COMMENT '主键',
    product     STRING       COMMENT '商品',
    quantity    INT          COMMENT '数量',
    price       DECIMAL(10, 2) COMMENT '单价',
    updated_at  TIMESTAMP    COMMENT '更新时间'
)
COMMENT 'ODS.orders - 来自 MySQL 同步'
PARTITIONED BY (dt STRING COMMENT '分区日期 yyyy-MM-dd')
STORED AS ORC
LOCATION 'hdfs://nameservice1/user/hive/warehouse/ods.db/orders';

-- 全量覆盖某天分区(跑批常用)
-- ALTER TABLE ods.orders DROP IF EXISTS PARTITION (dt='2026-09-01');

-- =====================================================================
-- 通用模板(带占位符)
-- =====================================================================
-- CREATE EXTERNAL TABLE IF NOT EXISTS `库名`.`表名` (
--     `col1`  TYPE  COMMENT '字段说明',
--     `col2`  TYPE  COMMENT '字段说明'
-- )
-- COMMENT '表说明'
-- [PARTITIONED BY (dt STRING COMMENT '分区日期')]
-- STORED AS ORC
-- LOCATION 'hdfs://.../warehouse/库名.db/表名';
-- =====================================================================
