-- =====================================================================
-- Doris 建表模板 (Unique Key 模型, 支持 INSERT/UPDATE/DELETE)
-- 执行: mysql -h192.168.3.100 -P9030 -uroot
-- 建议由 doris_sql/generate_ddl.py 根据 MySQL 元数据自动生成
-- =====================================================================

CREATE TABLE IF NOT EXISTS test_db.orders (
    id          BIGINT       NOT NULL COMMENT '主键',
    product     VARCHAR(100) NOT NULL COMMENT '商品',
    quantity    INT          NOT NULL DEFAULT 0 COMMENT '数量',
    price       DECIMAL(10, 2) NOT NULL COMMENT '单价',
    updated_at  DATETIME(6)  NOT NULL COMMENT '更新时间'
) UNIQUE KEY (id)                    -- 主键字段放这里; 复合键: UNIQUE KEY (id, ts)
  DISTRIBUTED BY HASH (id) BUCKETS 1  -- 分桶键一般=主键; 生产按数据量调 BUCKETS
  PROPERTIES ("replication_num" = "1");  -- 生产建议 3

-- =====================================================================
-- 通用模板(带占位符)
-- =====================================================================
-- CREATE TABLE IF NOT EXISTS `库名`.`表名` (
--     `col1`  TYPE  NOT NULL COMMENT '字段说明',
--     `col2`  TYPE  NULL  DEFAULT 'xxx' COMMENT '字段说明',
--     ...
--     UNIQUE KEY (`pk1`, `pk2`)
-- ) DISTRIBUTED BY HASH (`pk1`) BUCKETS 10
--   PROPERTIES ("replication_num" = "3");
--
-- 类型约定:
--   MySQL int(11)       -> INT
--   MySQL bigint(20)    -> BIGINT
--   MySQL tinyint(1)    -> BOOLEAN
--   MySQL varchar(n)    -> VARCHAR(n)  (n > 65533 用 STRING)
--   MySQL text/mediumtext/longtext -> STRING
--   MySQL decimal(p,s)  -> DECIMAL(p,s)
--   MySQL datetime/timestamp -> DATETIME
--   MySQL json          -> JSON
-- =====================================================================
