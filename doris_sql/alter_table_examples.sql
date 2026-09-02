-- =====================================================================
-- Doris 表结构变更示例 (MySQL -> Doris 结构同步生成的语句格式)
-- 执行: mysql -h192.168.3.100 -P9030 -uroot
-- =====================================================================

-- 新增字段
ALTER TABLE `test_db`.`orders`
    ADD COLUMN `remark` VARCHAR(500) NULL COMMENT '备注';

-- 删除字段(Doris 有、MySQL 没有时)
ALTER TABLE `test_db`.`orders`
    DROP COLUMN `old_col`;

-- 修改类型/可空性(先确认数据可转换, 大表会阻塞写入, 建议低峰执行)
ALTER TABLE `test_db`.`orders`
    MODIFY COLUMN `quantity` BIGINT NOT NULL COMMENT '数量';

-- 动态分区示例(按天分区, 需先开启 dynamic_partition.enable)
ALTER TABLE `test_db`.`orders`
    SET ("dynamic_partition.enable" = "true",
         "dynamic_partition.time_unit" = "DAY",
         "dynamic_partition.start" = "-7",
         "dynamic_partition.end" = "3",
         "dynamic_partition.prefix" = "p",
         "dynamic_partition.buckets" = "1");

-- =====================================================================
-- 变更规范(与 flink_sql/ 文档一致):
--   1. 先改 Doris -> 2. 再改源端(MySQL/PG) -> 3. 最后改 Flink SQL/重启
--   2. 生产环境变更前先预览: POST /api/metadata/schema-sync/ (preview=true)
--   3. 删除字段/改类型属于破坏性操作, 建议先备份或从低峰窗口执行
-- =====================================================================
