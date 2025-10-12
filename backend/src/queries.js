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