-- Each query starts with "-- name: <query_name>" and ends with a semicolon.
-- They are run from Python with pandas.read_sql_query().

-- name: kpis
SELECT
    ROUND(SUM(oi.quantity * p.list_price * (1 - oi.discount)), 2)                        AS revenue,
    ROUND(SUM(oi.quantity * (p.list_price * (1 - oi.discount) - p.unit_cost)), 2)        AS profit,
    COUNT(DISTINCT o.order_id)                                                           AS orders,
    COUNT(DISTINCT o.customer_id)                                                        AS customers,
    ROUND(SUM(oi.quantity * p.list_price * (1 - oi.discount)) / COUNT(DISTINCT o.order_id), 2) AS avg_order_value
FROM order_items oi
JOIN orders   o ON o.order_id   = oi.order_id
JOIN products p ON p.product_id = oi.product_id;

-- name: revenue_by_category
SELECT
    p.category,
    COUNT(DISTINCT oi.order_id)                                                   AS orders,
    SUM(oi.quantity)                                                              AS units,
    ROUND(SUM(oi.quantity * p.list_price * (1 - oi.discount)), 2)                 AS revenue,
    ROUND(SUM(oi.quantity * (p.list_price * (1 - oi.discount) - p.unit_cost)), 2) AS profit,
    ROUND(100.0 * SUM(oi.quantity * (p.list_price * (1 - oi.discount) - p.unit_cost))
          / SUM(oi.quantity * p.list_price * (1 - oi.discount)), 1)               AS margin_pct
FROM order_items oi
JOIN products p ON p.product_id = oi.product_id
GROUP BY p.category
HAVING revenue > 0
ORDER BY revenue DESC;

-- name: revenue_by_city_channel
SELECT
    c.city,
    o.channel,
    ROUND(SUM(oi.quantity * p.list_price * (1 - oi.discount)), 2) AS revenue
FROM order_items oi
JOIN orders    o ON o.order_id    = oi.order_id
JOIN customers c ON c.customer_id = o.customer_id
JOIN products  p ON p.product_id  = oi.product_id
GROUP BY c.city, o.channel
ORDER BY c.city, revenue DESC;

-- name: top_product_per_category
WITH product_rev AS (
    SELECT p.category, p.product_name,
           ROUND(SUM(oi.quantity * p.list_price * (1 - oi.discount)), 2) AS revenue
    FROM order_items oi
    JOIN products p ON p.product_id = oi.product_id
    GROUP BY p.category, p.product_name
),
ranked AS (
    SELECT *, RANK() OVER (PARTITION BY category ORDER BY revenue DESC) AS rnk
    FROM product_rev
)
SELECT category, product_name, revenue FROM ranked WHERE rnk = 1 ORDER BY revenue DESC;

-- name: monthly_trend
WITH monthly AS (
    SELECT strftime('%Y-%m', o.order_date) AS month,
           ROUND(SUM(oi.quantity * p.list_price * (1 - oi.discount)), 2) AS revenue
    FROM order_items oi
    JOIN orders   o ON o.order_id   = oi.order_id
    JOIN products p ON p.product_id = oi.product_id
    GROUP BY month
)
SELECT month,
       revenue,
       ROUND(AVG(revenue) OVER (ORDER BY month ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 2) AS moving_avg_3m,
       ROUND(100.0 * (revenue - LAG(revenue) OVER (ORDER BY month)) / LAG(revenue) OVER (ORDER BY month), 1) AS mom_growth_pct
FROM monthly
ORDER BY month;

-- name: customer_value
WITH cust AS (
    SELECT o.customer_id,
           COUNT(DISTINCT o.order_id) AS orders,
           ROUND(SUM(oi.quantity * p.list_price * (1 - oi.discount)), 2) AS total_spend,
           MIN(o.order_date) AS first_order,
           MAX(o.order_date) AS last_order
    FROM orders o
    JOIN order_items oi ON oi.order_id   = o.order_id
    JOIN products    p  ON p.product_id  = oi.product_id
    GROUP BY o.customer_id
)
SELECT customer_id, orders, total_spend,
       ROUND(total_spend * 1.0 / orders, 2) AS avg_order_value,
       CASE WHEN orders = 1 THEN 'One-time'
            WHEN orders <= 3 THEN 'Occasional'
            ELSE 'Repeat' END AS buyer_type,
       NTILE(5) OVER (ORDER BY total_spend DESC) AS spend_quintile,
       first_order, last_order
FROM cust;

-- name: item_level
SELECT oi.item_id, oi.quantity, oi.discount, p.list_price, p.unit_cost, p.category,
       ROUND(oi.quantity * p.list_price * (1 - oi.discount), 2) AS line_revenue,
       ROUND(100.0 * ((p.list_price * (1 - oi.discount)) - p.unit_cost) / (p.list_price * (1 - oi.discount)), 2) AS margin_pct
FROM order_items oi
JOIN products p ON p.product_id = oi.product_id;

-- name: sales_detail
SELECT oi.item_id, o.order_id, o.order_date, o.channel, c.customer_id, c.city, c.segment,
       p.product_name, p.category, oi.quantity, oi.discount, p.list_price, p.unit_cost,
       ROUND(oi.quantity * p.list_price * (1 - oi.discount), 2) AS revenue,
       ROUND(oi.quantity * (p.list_price * (1 - oi.discount) - p.unit_cost), 2) AS profit
FROM order_items oi
JOIN orders    o ON o.order_id    = oi.order_id
JOIN customers c ON c.customer_id = o.customer_id
JOIN products  p ON p.product_id  = oi.product_id;
