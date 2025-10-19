// Query #1 -> Revenue Rollup by time granularity (OPTIMIZED)
// $1::int  -> start_date_id (e.g., 20240101)
// $2::int  -> end_date_id   (e.g., 20241231)
// $3::text -> category (optional, pass NULL for all categories)
// $4::text -> granularity ('year', 'month', 'day')
const QUERY1 = 
`WITH base AS (
  SELECT 
    fo.total_price,
    fo.quantity,
    d.date_id,  -- raw numeric date
    CASE $4::text
      WHEN 'year'  THEN to_char(to_date(d.date_id::text, 'YYYYMMDD'), 'YYYY')
      WHEN 'month' THEN to_char(to_date(d.date_id::text, 'YYYYMMDD'), 'YYYY-MM')
      WHEN 'day'   THEN to_char(to_date(d.date_id::text, 'YYYYMMDD'), 'YYYY-MM-DD')
    END AS period
  FROM fact_orders fo
  JOIN dim_product p ON fo.product_id = p.product_id
  JOIN dim_date d ON fo.delivery_date_id = d.date_id
  WHERE ($3::text IS NULL OR p.category = $3::text)
    AND d.date_id BETWEEN $1::int AND $2::int  -- raw, indexable filter
)
SELECT
  period,
  SUM(total_price) AS revenue,
  SUM(quantity) AS units_sold
FROM base
GROUP BY period
ORDER BY period;`;

// Query #2 -> Customer distribution by country and by city via WITH ROLLUP (OPTIMIZED)
const QUERY2 = 
`SELECT
    du.country,
    du.city,
    COUNT(DISTINCT du.user_id) AS total_customers
FROM dim_user du
GROUP BY ROLLUP (du.country, du.city);`;

// Query #3 -> Top N products by revenue from either all customers, or filter by country or by city and by category (OPTIMIZED)
// $1::int  -> N (number of top products to return, e.g., 10)
// $2::text -> country (optional, pass NULL for all countries)
// $3::text -> city (optional, pass NULL for all cities)
// $4::text -> category (optional, pass NULL for all categories)
const QUERY3 = 
`SELECT
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
LIMIT $1::int;`;

// Query #4 -> 3-month moving average and optionally filters (or not) by country (OPTIMIZED)
// $1::text -> country (optional, pass NULL for all countries)
const QUERY4 =
`SELECT
  ms.year,
  ms.month,
  ms.country,
  ms.total_sales,
  ROUND(
    AVG(ms.total_sales) OVER (
      PARTITION BY ms.country
      ORDER BY ms.year, ms.month
      ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ), 2
  ) AS moving_avg_3_month
FROM (
  SELECT
    d.year,
    d.month,
    du.country,
    SUM(fo.total_price) AS total_sales
  FROM fact_orders fo
  JOIN dim_date d ON fo.delivery_date_id = d.date_id
  JOIN dim_user du ON fo.user_id = du.user_id
  WHERE ($1::text IS NULL OR du.country = $1::text)
  GROUP BY d.year, d.month, du.country
) AS ms
ORDER BY ms.year, ms.month, ms.country;`;

// Query #5 -> Rank Riders by their total deliveries (and optionally) by country (OPTIMIZED)
// $1::text -> country (optional, pass NULL for all countries)
const QUERY5 =
`WITH rider_deliveries AS (
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
ORDER BY delivery_rank;`;

// Query #6 -> Total Deliveries by Vehicle Type (Optionally by Year and Month), WITH ROLLUP (OPTIMIZED)
// $1::int  -> year (optional, pass NULL for all years)
// $2::int  -> month (optional, pass NULL for all months)
const QUERY6 = 
`SELECT
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
ORDER BY d.year, d.month, dr.vehicle_type;`;

//This query identifies the top X% of riders in total revenue in a particular COUNTRY in a particular quarterly time period with time based on delivery date. Include also previous sales records
// (to put simply, Top X% riders in _ Country, _ Period)

// $1::text -> year
// $2::text -> quarter
// $3::text -> previous year 
// $4::int  -> previous quarter
// $5::text  -> country
// $6::int -> percentile
const QUERY7 = 
`WITH rider_quarterly AS (
    SELECT
        du.country, 
        fo.rider_id,
        dd.year,dd.quarter, 
        SUM(fo.total_price) AS total_sales,
        COUNT(DISTINCT fo.user_id) AS customers_served
    FROM fact_orders AS fo
    JOIN dim_date AS dd 
        ON fo.delivery_date_id = dd.date_id
        AND (
            (dd.year = $1::int AND dd.quarter = $2::int)  -- current quarter
             OR (dd.year = $3::int AND dd.quarter = $4::int)  -- previous quarter
        )
    JOIN dim_user AS du 
        ON fo.user_id = du.user_id
        AND du.country = $5::text
    GROUP BY du.country, fo.rider_id, dd.year, dd.quarter
),

ranked_with_growth AS (
    SELECT
        country, 
        rider_id,
        year, quarter,
        total_sales,
        customers_served,
        LAG(total_sales) OVER (
            PARTITION BY country, rider_id 
            ORDER BY year, quarter
        ) AS prev_quarter_sales,
        ROUND(
            ((total_sales - LAG(total_sales) OVER (
                PARTITION BY country, rider_id 
                ORDER BY year, quarter
            )) / NULLIF(LAG(total_sales) OVER (
                PARTITION BY country, rider_id 
                ORDER BY year, quarter
            ), 0)) * 100, 2
        ) AS sales_growth_pct,
        ROUND(
            PERCENT_RANK() OVER (
                PARTITION BY country, year, quarter
                ORDER BY total_sales DESC
            )::numeric * 100, 2
        ) AS sales_percentile
    FROM rider_quarterly
)

SELECT
    country, 
    CONCAT(year, '-Q', quarter) AS period,
    rider_id,
    total_sales,
    prev_quarter_sales, sales_growth_pct,
    customers_served, sales_percentile
FROM ranked_with_growth
WHERE
   CONCAT(year, '-Q', quarter) = CONCAT($1::int, '-Q', $2::int)
    AND sales_percentile <= $6::int  
ORDER BY country, total_sales DESC;
`;

// Query #8 -> Revenue analysis with ROLLUP by country, city, and category for a specific year
// $1::int  -> year (required, e.g., 2025)
// $2::text -> country (optional, pass NULL for all countries, e.g., 'Philippines')
// $3::text -> city (optional, pass NULL for all cities, e.g., 'Canton')
// $4::text -> category (optional, pass NULL for all categories, e.g., 'BAG')
const QUERY8 = 
`WITH yearly_revenue_base AS (
    -- Step 1: Base data for the year being summarized.
    SELECT
        du.country,
        du.city,
        dp.category,
        dr.rider_id,
        fo.total_price
    FROM
        fact_orders AS fo
    JOIN
        dim_rider AS dr ON fo.rider_id = dr.rider_id
    JOIN
        dim_user AS du ON fo.user_id = du.user_id
    JOIN
        dim_date AS dd ON fo.delivery_date_id = dd.date_id
    JOIN
        dim_product AS dp ON fo.product_id = dp.product_id
    WHERE
        dd.year = $1::int
)
-- Final Step: Use a more granular ROLLUP and a flexible HAVING clause.
SELECT
    COALESCE(country, 'Grand Total') AS country,
    COALESCE(city, 'All Cities') AS city,
    COALESCE(category, 'All Categories') AS category,
    SUM(total_price) AS total_revenue,
    COUNT(DISTINCT rider_id) AS unique_riders
FROM
    yearly_revenue_base
GROUP BY
    ROLLUP(country, city, category)
HAVING
    ($2::text IS NULL OR country = $2::text)
    AND ($3::text IS NULL OR city = $3::text)
    AND ($4::text IS NULL OR category = $4::text)
ORDER BY
    country, city, category;`;

// Query #9 -> Revenue analysis with ROLLUP by country, city, and category with enhanced metrics
// $1::int  -> year (required, e.g., 2025)
// $2::text -> country (optional, pass NULL for all countries, e.g., 'Philippines')
// $3::text -> city (optional, pass NULL for all cities, e.g., 'Canton')
// $4::text -> category (optional, pass NULL for all categories, e.g., 'BAG')
const QUERY9 = 
`WITH yearly_revenue_base AS (
    -- Step 1: Base data for the year being summarized.
    SELECT
        du.country,
        du.city,
        dp.category,
        dr.rider_id,
        fo.total_price
    FROM
        fact_orders AS fo
    JOIN
        dim_rider AS dr ON fo.rider_id = dr.rider_id
    JOIN
        dim_user AS du ON fo.user_id = du.user_id
    JOIN
        dim_date AS dd ON fo.delivery_date_id = dd.date_id
    JOIN
        dim_product AS dp ON fo.product_id = dp.product_id
    WHERE
        -- Filters are now applied here for maximum efficiency.
        dd.year = $1::int
        AND ($2::text IS NULL OR du.country = $2::text)
        AND ($3::text IS NULL OR du.city = $3::text)
        AND ($4::text IS NULL OR dp.category = $4::text)
)
-- Final Step: Use ROLLUP to generate summaries for the filtered data.
SELECT
    COALESCE(country, 'Grand Total') AS country,
    COALESCE(city, 'All Cities') AS city,
    COALESCE(category, 'All Categories') AS category,
    SUM(total_price) AS total_revenue,
    COUNT(DISTINCT rider_id) AS unique_riders,
    AVG(total_price) AS average_order_value
FROM
    yearly_revenue_base
GROUP BY
    ROLLUP(country, city, category)
ORDER BY
    country, city, category;`;

// Export all queries using CommonJS
module.exports = {
  QUERY1,
  QUERY2,
  QUERY3,
  QUERY4,
  QUERY5,
  QUERY6,
  QUERY7,
  QUERY8,
  QUERY9
};