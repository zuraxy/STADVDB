// #1 Revenue Rollup by time granularity
export const QUERY1 = 
`WITH base AS (
  SELECT
    fo.total_price,
    fo.quantity,
    to_date(d.date_id::text,'YYYYMMDD') AS dateval,
    CASE $4
      WHEN 'year'  THEN to_char(to_date(d.date_id::text,'YYYYMMDD'), 'YYYY')
      WHEN 'month' THEN to_char(to_date(d.date_id::text,'YYYYMMDD'), 'YYYY-MM')
      WHEN 'day'   THEN to_char(to_date(d.date_id::text,'YYYYMMDD'), 'YYYY-MM-DD')
    END AS period
  FROM fact_orders fo
  JOIN dim_product p ON fo.product_id = p.product_id
  JOIN dim_date d ON fo.delivery_date_id = d.date_id
  WHERE ($3::text IS NULL OR p.category = $3::text)
)
SELECT
  period,
  SUM(total_price) AS revenue,
  SUM(quantity)    AS units_sold
FROM base
WHERE dateval BETWEEN $1::date AND $2::date
GROUP BY period
ORDER BY period;
`
//# 2 Customer distribution by country and by city via WITH ROLLUP
export const QUERY2=
`
SELECT
    du.country,
    du.city,
    COUNT(DISTINCT du.user_id) AS total_customers
FROM dim_user du
GROUP BY ROLLUP (du.country, du.city);
`

//# 3 Top N products by revenue from either all customers, or filter by country or by city and by category 

export const QUERY3 = 
`
-- Parameters you can adjust:
-- :N → number of top products to return
-- :country → filter by specific country (optional)
-- :city → filter by specific city (optional)
-- :category → filter by product category (optional)

SELECT
    dp.name AS product_name,
    dp.category,
    SUM(fo.quantity) AS total_quantity_sold,
    SUM(fo.total_price) AS total_sales
FROM fact_orders fo
JOIN dim_product dp ON fo.product_id = dp.product_id
JOIN dim_user du ON fo.user_id = du.user_id
WHERE
    ($2::text IS NULL OR du.country = $2::text)
    AND ($3::text IS NULL OR du.city = $3::text)
    AND ($4::text IS NULL OR dp.category = $4::text)
GROUP BY
    dp.name, dp.category
ORDER BY
    total_sales DESC
LIMIT $1;
`


//#4 3-month moving average and optionally filters (or not) by country

export const QUERY4 =
`
WITH monthly_sales AS (
    SELECT
        d.year,
        d.month,
        du.country,
        SUM(fo.total_price) AS total_sales
    FROM fact_orders fo
    JOIN dim_date d ON fo.delivery_date_id = d.date_id
    JOIN dim_user du ON fo.user_id = du.user_id
    GROUP BY d.year, d.month, du.country
)
SELECT
    year,
    month,
    country,
    total_sales,
    ROUND(
        AVG(total_sales) OVER (
            PARTITION BY country
            ORDER BY year, month
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ), 2
    ) AS moving_avg_3_month
FROM monthly_sales
WHERE ($1::text IS NULL OR country = $1::text)
ORDER BY year, month, country;
`

// # 5 Rank Riders by their total deliveries (and optionally) by country

export const QUERY5 =
`
WITH rider_deliveries AS (
    SELECT
        du.country,
        r.rider_id,
        r.courier_name,
        COUNT(*) AS total_deliveries
    FROM fact_orders fo
    JOIN dim_rider r ON fo.rider_id = r.rider_id
    JOIN dim_user du ON fo.user_id = du.user_id
    GROUP BY du.country, r.rider_id, r.courier_name
)
SELECT
    country,
    rider_id,
    courier_name,
    total_deliveries,
    RANK() OVER (
        PARTITION BY 
            CASE 
                WHEN $1::text IS NULL THEN NULL  -- Global rank if no filter
                ELSE country                     -- Separate ranks per country
            END
        ORDER BY total_deliveries DESC
    ) AS delivery_rank
FROM rider_deliveries
WHERE ($1::text IS NULL OR country = $1::text)
ORDER BY delivery_rank;
`

//# 6  Total Deliveries by Vehicle Type (Optionally by Year and Month), WITH ROLLUP
export const QUERY6= 
`
SELECT
    d.year,
    d.month,
    dr.vehicle_type,
    COUNT(fo.fact_id) AS total_deliveries
FROM fact_orders fo
JOIN dim_rider dr ON fo.rider_id = dr.rider_id
JOIN dim_date d ON fo.delivery_date_id = d.date_id
WHERE
    ($1::int IS NULL OR d.year = $1::int)
    AND ($2::int IS NULL OR d.month = $2::int)
GROUP BY ROLLUP (d.year, d.month, dr.vehicle_type)
ORDER BY d.year, d.month, dr.vehicle_type;

`

// #7 Top percentile categories by quantity with regional sales analysis and YoY growth
// $1::date  -> start_date (e.g., '2023-01-01')
// $2::date  -> end_date   (e.g., '2024-12-31')
// $3::int   -> top_percent (e.g., 20 for top 20%)
// $4::text  -> granularity ('year', 'quarter', 'month')
export const QUERY7 = 
`
WITH base AS (
    SELECT 
        fo.order_date,
        EXTRACT(YEAR FROM fo.order_date)::int AS yr,
        EXTRACT(QUARTER FROM fo.order_date)::int AS qtr,
        EXTRACT(MONTH FROM fo.order_date)::int AS mon,
        fo.total_price,
        fo.quantity,
        dp.category,
        du.country AS region,
        du.user_id AS customer_id
    FROM fact_orders fo
    JOIN dim_product dp ON fo.product_id = dp.product_id
    JOIN dim_user du ON fo.user_id = du.user_id
    WHERE fo.order_date BETWEEN $1::date AND $2::date
),
ranked_products AS (
    SELECT 
        category,
        SUM(quantity) AS total_qty,
        NTILE(100) OVER (ORDER BY SUM(quantity) DESC) AS percentile_rank
    FROM base
    GROUP BY category
),
filtered AS (
    SELECT b.*
    FROM base b
    JOIN ranked_products rp ON b.category = rp.category
    WHERE rp.percentile_rank <= $3::int
),
agg AS (
    SELECT 
        region,
        category,
        CASE 
            WHEN $4 = 'year' THEN yr::text
            WHEN $4 = 'quarter' THEN yr::text || '-Q' || qtr::text
            WHEN $4 = 'month' THEN yr::text || '-' || LPAD(mon::text, 2, '0')
        END AS period,
        SUM(total_price) AS total_sales,
        COUNT(DISTINCT customer_id) AS customers
    FROM filtered
    GROUP BY region, category, period
),
growth AS (
    SELECT 
        a1.region,
        a1.category,
        a1.period,
        ROUND(a1.total_sales / NULLIF(a1.customers, 0), 2) AS avg_spend_per_customer,
        ROUND(((a1.total_sales - a2.total_sales) / NULLIF(a2.total_sales, 0)) * 100, 2) AS sales_growth_pct
    FROM agg a1
    LEFT JOIN agg a2
        ON a1.region = a2.region
        AND a1.category = a2.category
        AND (
            ($4 = 'year' AND a1.period::int = a2.period::int + 1)
            OR ($4 = 'quarter' AND SPLIT_PART(a1.period, '-Q', 1)::int = SPLIT_PART(a2.period, '-Q', 1)::int + 1
                                AND SPLIT_PART(a1.period, '-Q', 2)::int = SPLIT_PART(a2.period, '-Q', 2)::int)
            OR ($4 = 'month' AND TO_DATE(a1.period || '-01', 'YYYY-MM-DD') = TO_DATE(a2.period || '-01', 'YYYY-MM-DD') + INTERVAL '1 month')
        )
)
SELECT *
FROM growth
ORDER BY region, category, period;
`

export const QUERY8 = 
`
-- Parameters
--SET @start_date = '2023-01-01';
--SET @end_date = '2024-12-31';
--SET @top_percent = 20;      -- choose 10, 20, etc.
--SET @granularity = 'quarter';  -- options: 'year', 'quarter', 'month'

WITH base AS (
  SELECT 
    f.order_date,
    YEAR(f.order_date) AS yr,
    QUARTER(f.order_date) AS qtr,
    MONTH(f.order_date) AS mon,
    f.total_price,
    f.quantity,
    p.category,
    s.region,
    c.customer_id
  FROM fact_orders f
  JOIN dim_product p ON f.product_id = p.product_id
  JOIN dim_store s ON f.store_id = s.store_id
  JOIN dim_customer c ON f.customer_id = c.customer_id
  WHERE f.order_date BETWEEN $1 AND $2
),

-- Step 1: Rank categories by total quantity sold
ranked_products AS (
  SELECT 
    category,
    SUM(quantity) AS total_qty,
    NTILE(100) OVER (ORDER BY SUM(quantity) DESC) AS percentile_rank
  FROM base
  GROUP BY category
),

-- Step 2: Filter only the top @top_percent categories
filtered AS (
  SELECT b.*
  FROM base b
  JOIN ranked_products rp ON b.category = rp.category
  WHERE rp.percentile_rank <= $3
),

-- Step 3: Aggregate by region, category, and selected granularity
agg AS (
  SELECT 
    region,
    category,
    CASE 
      WHEN $4 = 'year' THEN CAST(yr AS CHAR)
      WHEN $4 = 'quarter' THEN CONCAT(yr, '-Q', qtr)
      WHEN $4 = 'month' THEN CONCAT(yr, '-', LPAD(mon, 2, '0'))
    END AS period,
    SUM(total_price) AS total_sales,
    COUNT(DISTINCT customer_id) AS customers
  FROM filtered
  GROUP BY region, category, period
),

-- Step 4: Compute average spend per customer and YoY growth
growth AS (
  SELECT 
    a1.region,
    a1.category,
    a1.period,
    a1.total_sales / a1.customers AS avg_spend_per_customer,
    ((a1.total_sales - a2.total_sales) / NULLIF(a2.total_sales, 0)) * 100 AS sales_growth_pct
  FROM agg a1
  LEFT JOIN agg a2
    ON a1.region = a2.region
    AND a1.category = a2.category
    AND (
      ($4 = 'year' AND a1.period = a2.period + 1)
      OR ($4 = 'quarter' AND SUBSTRING_INDEX(a1.period, '-Q', 1) = SUBSTRING_INDEX(a2.period, '-Q', 1) + 1)
      OR ($4 = 'month' AND a1.period = a2.period + 1)
    )
)
SELECT *
FROM growth
ORDER BY region, category, period;

`