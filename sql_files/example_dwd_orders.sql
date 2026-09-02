-- 示例: 明细层加工 (用于血缘解析演示)
INSERT INTO dwd.dwd_order_detail (
    order_id, user_id, product_name, amount, dt
)
SELECT
    o.id            AS order_id,
    o.user_id       AS user_id,
    p.name          AS product_name,
    o.amount        AS amount,
    '${dt}'         AS dt
FROM dws.ods_orders o
JOIN dws.dim_product p ON p.id = o.product_id
WHERE o.dt = '${dt}';
