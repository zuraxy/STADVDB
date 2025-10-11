#IMPORTANT: MAKE SURE UR NET IS NOT OBSOLETE 1990 TECHNOLOGY - MAKE SURE IT SUPPORTS FRICKEN IPV6

# installations:
# pip install sqlalchemy
# pip install dotenv
# pip install pymysql
# pip install psycopg2

import os
import pandas as pd
import json
from datetime import datetime
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

# Config to connect to source db and db warehouse (.env)
MYSQL_CONN_STR = os.environ.get("MYSQL_CONNECTION_STRING")
SUPABASE_CONN_STR = os.environ.get("SUPABASE_CONNECTION_STRING")

mysql_engine = create_engine(MYSQL_CONN_STR)
supabase_engine = create_engine(SUPABASE_CONN_STR)

# 1. EXTRACT (SQL Tables -> Panda DataFrames)
orders_df = pd.read_sql(
    """
    SELECT id, orderNumber,  userId,  deliveryDate,  deliveryRiderId,  createdAt,  updatedAt
    FROM Orders
    """, 
    mysql_engine
)

order_items_df = pd.read_sql(
   """
   SELECT OrderId, ProductId, quantity, notes, createdAt, updatedAt 
   FROM OrderItems
   """, 
   mysql_engine
)

products_df = pd.read_sql(
   """
   SELECT id, productCode, category, description, name, price, createdAt, updatedAt 
   FROM Products
   """, 
   mysql_engine
)

users_df = pd.read_sql(
    """
    SELECT id, username, firstName, lastName, address1, address2, city, country, zipCode, phoneNumber, dateOfBirth, gender, createdAt, updatedAt 
    FROM Users
    """, 
    mysql_engine
)

riders_df = pd.read_sql(
   """
   SELECT id, firstName, lastName, vehicleType, courierId, age, gender, createdAt, updatedAt 
   FROM Riders
   """, 
   mysql_engine
)

couriers_df = pd.read_sql(
   """
   SELECT id, name AS courier_name, createdAt, updatedAt 
   FROM Couriers
   """, 
   mysql_engine
)

# 2. TRANSFORM (using pandas to fit our datawarehouse schema in supabase)
# Side note: Primary keys in SQL are adapted to be the primary keys in our data warehouse in supabase 
# other data sources can be factored in, in the future (but not now), because our current scope is currently pretty well defined 

# 2.1 orders_df and order_items_df
orders_df = orders_df.rename(columns={'id': 'orders_id', 'createdAt':'orders_created_at', 'updatedAt': 'orders_updated_at'})
orders_df = orders_df.drop_duplicates(subset=['orders_id'])

order_items_df = order_items_df.rename(columns={'OrderId': 'order_items_id', 'createdAt': 'order_items_created_at', 'updatedAt': 'order_items_updated_at'})
order_items_df = order_items_df.drop_duplicates(subset=['order_items_id'])

# 2.2 DIM_PRODUCT: Pre-processing
dim_product = products_df[['id', 'name', 'category', 'price', 'updatedAt']].copy()
dim_product = dim_product.rename(columns={'id': 'product_id', 'name': 'name', 'price': 'current_price'})
dim_product = dim_product.drop_duplicates(subset=['product_id'])

# 2.3 DIM_USER: Pre-processing
dim_user = users_df[['id', 'city', 'country', 'gender', 'dateOfBirth', 'updatedAt']].copy()
dim_user = dim_user.rename(columns={'id': 'user_id', 'dateOfBirth': 'date_of_birth'})
dim_user = dim_user.drop_duplicates(subset=['user_id'])
dim_user['date_of_birth'] = pd.to_datetime(dim_user['date_of_birth'], errors='coerce', utc=True,  format='%m/%d/%Y').dt.date

# 2.4 DIM_RIDER & DIM_COURIER: Pre-processing & joining
riders_table = riders_df[['id', 'vehicleType', 'courierId', 'age', 'gender', 'updatedAt']].copy()
riders_table = riders_table.rename(columns={'id': 'rider_id', 'vehicleType': 'vehicle_type', 'courierId': 'courier_id', 'updatedAt': 'rider_updatedAt'})
couriers_table = couriers_df[['id', 'courier_name', 'updatedAt']].copy()
couriers_table = couriers_table.rename(columns={'id': 'courier_id', 'updatedAt': 'courier_updatedAt'})

# 2.4.1 Merge riders and couriers table to one dimension table
dim_rider = riders_table.merge(couriers_table, on='courier_id', how='left')

# 2.4.2 Use the most recent updatedAt 
dim_rider['rider_updatedAt'] = pd.to_datetime(dim_rider['rider_updatedAt'], errors='coerce')
dim_rider['courier_updatedAt'] = pd.to_datetime(dim_rider['courier_updatedAt'], errors='coerce')
dim_rider['updatedAt'] = dim_rider[['rider_updatedAt', 'courier_updatedAt']].max(axis=1)

# 2.4.3 Final selection of columns matching our DW schema
dim_rider = dim_rider[['rider_id', 'vehicle_type', 'courier_name', 'age', 'gender', 'updatedAt']]
dim_rider = dim_rider.drop_duplicates(subset=['rider_id'])

# 2.5 DIM_DATE: Pre-processing
unique_delivery_dates = pd.to_datetime(orders_df['deliveryDate'], errors='coerce', utc=True, format='%Y/%m/%d').dt.date
unique_delivery_dates = unique_delivery_dates.dropna().unique()

date_series = pd.Series(unique_delivery_dates)

dim_date = pd.DataFrame()
dim_date['date_id'] = date_series.map(lambda d: int(d.strftime('%Y%m%d')))
dim_date['year'] = date_series.dt.year
dim_date['quarter'] = date_series.dt.quarter
dim_date['month'] = date_series.dt.month
dim_date['day'] = date_series.dt.day
dim_date['day_of_week'] = date_series.dt.dayofweek
dim_date['is_weekend'] = dim_date['day_of_week'].isin([5, 6])

# Check data types
dim_date['date_id'] = dim_date['date_id'].astype('int64') 
dim_date['year'] = dim_date['year'].astype('int16')
dim_date['quarter'] = dim_date['quarter'].astype('int16')
dim_date['month'] = dim_date['month'].astype('int16')
dim_date['day'] = dim_date['day'].astype('int16')
dim_date['day_of_week'] = dim_date['day_of_week'].astype('int16')
dim_date['is_weekend'] = dim_date['is_weekend'].astype('bool')

# 2.6 FACT TABLE: build
# 2.6.1: Join order_items with orders to get all needed columns
fact_orders = order_items_df.merge(
    orders_df,
    left_on='order_items_id',
    right_on='orders_id',
    how='left'
)

# 2.6.2: Join with products for price (unit_price)
fact_orders = fact_orders.merge(
    products_df[['id', 'price', 'updatedAt']],
    left_on='ProductId',
    right_on='id',
    how='left',
    suffixes=('', '_product')
)

# 2.6.3: After all merges, find the most recent updatedAt timestamp
fact_orders['orders_updated_at'] = pd.to_datetime(fact_orders['orders_updated_at'], errors='coerce')
fact_orders['order_items_updated_at'] = pd.to_datetime(fact_orders['order_items_updated_at'], errors='coerce')
fact_orders['updatedAt'] = pd.to_datetime(fact_orders['updatedAt'], errors='coerce')

fact_orders['most_recent_updated_at'] = fact_orders[['orders_updated_at', 'order_items_updated_at', 'updatedAt']].max(axis=1)

# 2.6.3: Convert delivery date to match the date_id format in dim_date
fact_orders['delivery_date'] = pd.to_datetime(fact_orders['deliveryDate'], errors='coerce', utc=True).dt.date
fact_orders['delivery_date'] = fact_orders['delivery_date'].map(lambda d: int(d.strftime('%Y%m%d')) if pd.notnull(d) else None)

# 2.6.4 Calculate total_price
fact_orders['unit_price'] = fact_orders['price']
fact_orders['total_price'] = fact_orders['quantity'] * fact_orders['unit_price']

# 2.6.5 Create fact_id as a simple auto-increment
fact_orders['fact_id'] = range(1, len(fact_orders) + 1)

# 2.6.6 Select columns to keep and rename to match fact table schema
fact_orders_final = fact_orders[[
    'fact_id',
    'order_items_id',
    'ProductId',
    'userId',
    'deliveryRiderId',
    'delivery_date',
    'quantity',
    'unit_price',
    'total_price',
    'most_recent_updated_at'
]].rename(columns={
    'order_items_id': 'order_id',
    'ProductId': 'product_id',
    'userId': 'user_id',
    'deliveryRiderId': 'rider_id',
    'delivery_date': 'delivery_date_id',
    'most_recent_updated_at': 'updated_at'
})

# 2.6.7 Handle missing values and ensure correct data types
fact_orders_final['fact_id'] = fact_orders_final['fact_id'].astype('int64')
fact_orders_final['order_id'] = fact_orders_final['order_id'].astype('int64')
fact_orders_final['product_id'] = fact_orders_final['product_id'].astype('int32')
fact_orders_final['user_id'] = fact_orders_final['user_id'].astype('int32')
fact_orders_final['rider_id'] = fact_orders_final['rider_id'].fillna(-1).astype('int32')
fact_orders_final['quantity'] = fact_orders_final['quantity'].fillna(0).astype('int32')
fact_orders_final['unit_price'] = fact_orders_final['unit_price'].fillna(0).astype('float')
fact_orders_final['total_price'] = fact_orders_final['total_price'].fillna(0).astype('float')
fact_orders_final['updated_at'] = pd.to_datetime(fact_orders_final['updated_at'], utc=True)

# 2.6.8 fast logs
print(f"Total fact records: {len(fact_orders_final)}")
print(f"Records with missing product_id: {fact_orders_final['product_id'].isna().sum()}")
print(f"Records with missing unit_price: {fact_orders_final['unit_price'].isna().sum()}")

# 3. LOAD to actual Data Warehouse (DW) in Supabase
# 3.1 Check for the last ETL run timestamp
etl_runs = pd.read_sql(
    """
    SELECT run_date 
    FROM etl_runs 
    ORDER BY run_date DESC 
    LIMIT 1
    """, 
    supabase_engine
)

if len(etl_runs) > 0:
    run_date = etl_runs.iloc[0]['last_run']
    print(f"Last ETL run was at: {run_date}")
else:
    # No previous runs, do full load
    run_date = pd.Timestamp.min
    print("No previous ETL runs found. Performing full load.")

# Current timestamp for this ETL run
current_run_timestamp = datetime.now()

# 3.2 Load dimension tables
# 3.2.1 Load dim_product
# Filter records updated since last ETL run
updated_products = dim_product[pd.to_datetime(products_df['updatedAt']) > run_date]
print(f"Loading {len(updated_products)} updated products")

if len(updated_products) > 0:
    with supabase_engine.begin() as conn:
        # Delete records that will be updated
        if len(updated_products) < len(dim_product):  # Don't delete all if it's not a full refresh
            product_ids_to_update = tuple(updated_products['product_id'].tolist())
            if len(product_ids_to_update) == 1:
                conn.execute(text(f"DELETE FROM dim_product WHERE product_id = {product_ids_to_update[0]}"))
            else:
                conn.execute(text(f"DELETE FROM dim_product WHERE product_id IN {product_ids_to_update}"))
        else:
            # Full refresh
            conn.execute(text("TRUNCATE TABLE dim_product"))
            
        # Insert updated records
        updated_products.drop(columns=['updatedAt'], errors='ignore').to_sql(
            'dim_product', 
            conn, 
            if_exists='append', 
            index=False
        )

# 3.2.2 Load dim_user - same thing
updated_users = dim_user[pd.to_datetime(users_df['updatedAt']) > run_date]
print(f"Loading {len(updated_users)} updated users")

if len(updated_users) > 0:
    with supabase_engine.begin() as conn:
        if len(updated_users) < len(dim_user):
            user_ids_to_update = tuple(updated_users['user_id'].tolist())
            if len(user_ids_to_update) == 1:
                conn.execute(text(f"DELETE FROM dim_user WHERE user_id = {user_ids_to_update[0]}"))
            else:
                conn.execute(text(f"DELETE FROM dim_user WHERE user_id IN {user_ids_to_update}"))
        else:
            conn.execute(text("TRUNCATE TABLE dim_user"))
            
        updated_users.drop(columns=['updatedAt'], errors='ignore').to_sql(
            'dim_user', 
            conn, 
            if_exists='append', 
            index=False
        )

# 3.2.3 Load dim_rider
updated_riders = dim_rider[pd.to_datetime(dim_rider['updatedAt']) > run_date]
print(f"Loading {len(updated_riders)} updated riders")

if len(updated_riders) > 0:
    with supabase_engine.begin() as conn:
        if len(updated_riders) < len(dim_rider):
            rider_ids_to_update = tuple(updated_riders['rider_id'].tolist())
            if len(rider_ids_to_update) == 1:
                conn.execute(text(f"DELETE FROM dim_rider WHERE rider_id = {rider_ids_to_update[0]}"))
            else:
                conn.execute(text(f"DELETE FROM dim_rider WHERE rider_id IN {rider_ids_to_update}"))
        else:
            conn.execute(text("TRUNCATE TABLE dim_rider"))
            
        updated_riders.drop(columns=['updatedAt'], errors='ignore').to_sql(
            'dim_rider', 
            conn, 
            if_exists='append', 
            index=False
        )

# 3.2.4 Load dim_date
with supabase_engine.begin() as conn:
    # ON CONFLICT DO NOTHING for avoiding duplicates
    for _, row in dim_date.iterrows():
        conn.execute(text(f"""
            INSERT INTO dim_date (date_id, year, quarter, month, day, day_of_week, is_weekend)
            VALUES ({row['date_id']}, {row['year']}, {row['quarter']}, {row['month']}, 
                    {row['day']}, {row['day_of_week']}, {row['is_weekend']})
            ON CONFLICT (date_id) DO NOTHING
        """))
    print(f"Loaded {len(dim_date)} date records (with upsert)")

# 3.3 Load fact table
# For fact_orders, identify records to update based on order updated_at
updated_orders = fact_orders_final[pd.to_datetime(fact_orders_final['updated_at']) > run_date]
print(f"Loading {len(updated_orders)} updated fact records")

if len(updated_orders) > 0:
    with supabase_engine.begin() as conn:
        if len(updated_orders) < len(fact_orders_final):
            # Get order_ids that were updated
            order_ids_to_update = tuple(updated_orders['order_id'].unique().tolist())
            if len(order_ids_to_update) == 1:
                conn.execute(text(f"DELETE FROM fact_orders WHERE order_id = {order_ids_to_update[0]}"))
            else:
                conn.execute(text(f"DELETE FROM fact_orders WHERE order_id IN {order_ids_to_update}"))
        else:
            # Full refresh
            conn.execute(text("TRUNCATE TABLE fact_orders"))
            
        # Insert updated records
        updated_orders.drop(columns=['updated_at'], errors='ignore').to_sql(
            'fact_orders', 
            conn, 
            if_exists='append', 
            index=False
        )

# 3.4 Record this ETL run
with supabase_engine.begin() as conn:
    conn.execute(text(f"""
        INSERT INTO etl_runs (run_date)
        VALUES ('{current_run_timestamp.isoformat()}')
    """))

print(f"ETL completed successfully at {current_run_timestamp}")