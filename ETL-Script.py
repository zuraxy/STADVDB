# Pandas ETL Script
# -> Extract data from MySQL source database, transform to fit to data warehouse, and finally load into PostgreSQL (Supabase)
import os
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

# Config to connect to source db and db warehouse (.env)
MYSQL_CONN_STR = os.environ.get("MYSQL_CONNECTION_STRING")
SUPABASE_CONN_STR = os.environ.get("SUPABASE_CONNECTION_STRING")

mysql_engine = create_engine(MYSQL_CONN_STR)
supabase_engine = create_engine(SUPABASE_CONN_STR)

# EXTRACT (we'll transform sql tables to pandas first)
orders_df = pd.read_sql("SELECT id, orderNumber, userId, deliveryDate, deliveryRiderId, createdAt, updatedAt FROM Orders", mysql_engine)
order_items_df = pd.read_sql("SELECT OrderId, ProductId, quantity, notes, createdAt, updatedAt FROM OrderItems", mysql_engine)
products_df = pd.read_sql("SELECT id, productCode, category, description, name, price, createdAt, updatedAt FROM Products", mysql_engine)
users_df = pd.read_sql("SELECT id, username, firstName, lastName, address1, address2, city, country, zipCode, phoneNumber, dateOfBirth, gender, createdAt, updatedAt FROM Users", mysql_engine)
riders_df = pd.read_sql("SELECT id, firstName, lastName, vehicleType, courierId, age, gender, createdAt, updatedAt FROM Riders", mysql_engine)
couriers_df = pd.read_sql("SELECT id, name AS courier_name, createdAt, updatedAt FROM Couriers", mysql_engine)

# TRANSFORM (using pandas to fit our datawarehouse schema in supabase)

# transforming created products dataframe to fit inside datawarehouse's product dimension table
dim_product = products_df[['id', 'name', 'category', 'price']].copy()
dim_product = dim_product.rename(columns={'id': 'product_id', 'name': 'name', 'price': 'current_price'})
dim_product = dim_product.drop_duplicates(subset=['product_id'])

# transforming created users dataframe to fit inside datawarehouse's user dimension table
dim_user = users_df[['id', 'city', 'country', 'gender', 'dateOfBirth']].copy()
dim_user = dim_user.rename(columns={'id': 'user_id', 'dateOfBirth': 'date_of_birth'})
dim_user['date_of_birth'] = pd.to_datetime(dim_user['date_of_birth'], errors='coerce', utc=True).dt.date
dim_user = dim_user.drop_duplicates(subset=['user_id'])

# dim_rider (join riders -> couriers to get courier_name, while preserving rider names)
riders_small = riders_df[['id', 'firstName', 'lastName', 'vehicleType', 'courierId', 'gender']].copy()
riders_small = riders_small.rename(columns={'id': 'rider_id', 'firstName': 'first_name', 'lastName': 'last_name', 'vehicleType': 'vehicle_type', 'courierId': 'courier_id'})

couriers_small = couriers_df[['id', 'courier_name']].rename(columns={'id': 'courier_id'})
dim_rider = riders_small.merge(couriers_small, on='courier_id', how='left')
# select the schema we want
dim_rider['name'] = dim_rider['first_name'] + ' ' + dim_rider['last_name']
dim_rider = dim_rider[['rider_id', 'first_name', 'last_name', 'vehicle_type', 'courier_name', 'gender']]
dim_rider = dim_rider.drop_duplicates(subset=['rider_id'])

# dim_date (from orders' createdAt and deliveryDate; ensure timezone-aware)
orders_df['createdAt_ts'] = pd.to_datetime(orders_df['createdAt'], errors='coerce', utc=True)
orders_df['delivery_ts'] = pd.to_datetime(orders_df['deliveryDate'], errors='coerce', utc=True)

all_dates = pd.to_datetime(pd.Series(list(orders_df['createdAt_ts'].dt.date.dropna().unique()) +
                                     list(orders_df['delivery_ts'].dt.date.dropna().unique())),
                           utc=True).dropna().unique()
all_dates = pd.to_datetime(sorted(pd.to_datetime(all_dates).date))
dim_date = pd.DataFrame({'date_id': pd.to_datetime(all_dates)})
dim_date['year'] = dim_date['date_id'].dt.year
dim_date['quarter'] = dim_date['date_id'].dt.quarter
dim_date['month'] = dim_date['date_id'].dt.month
dim_date['day'] = dim_date['date_id'].dt.day
dim_date['day_of_week'] = dim_date['date_id'].dt.weekday
dim_date['is_weekend'] = dim_date['day_of_week'].isin([5, 6])
dim_date['date_id'] = pd.to_datetime(dim_date[['year', 'month', 'day']]).dt.date

# FACT TABLE: build order-item fact carefully with explicit suffixes and selected columns
# Merge order_items (left) with orders (right) to bring in userId, createdAt (order) and deliveryDate
oi = order_items_df.merge(
    orders_df[['id', 'userId', 'createdAt', 'deliveryDate', 'deliveryRiderId', 'updatedAt']], 
    left_on='OrderId', right_on='id',
    how='left',
    suffixes=('_item', '_order')
)

# Merge with products to get price (unit_price)
oi = oi.merge(
    products_df[['id', 'price', 'name']].rename(columns={'id': 'prod_id', 'price': 'product_price', 'name': 'product_name'}),
    left_on='ProductId', right_on='prod_id',
    how='left'
)

# Now pick and rename columns deterministically
fact_orders = oi[[
    'OrderId',               # business order id
    'ProductId',
    'userId',
    'deliveryRiderId',
    'createdAt_order',       # order createdAt (from orders)
    'deliveryDate',          # raw delivery date from orders
    'quantity',
    'product_price',         # price from products
    'updatedAt_order'        # order.updatedAt (for incremental watermark)
]].copy()

# rename
fact_orders = fact_orders.rename(columns={
    'OrderId': 'order_id',
    'ProductId': 'product_id',
    'userId': 'user_id',
    'deliveryRiderId': 'rider_id',
    'createdAt_order': 'created_at',
    'deliveryDate': 'delivery_date_raw',
    'product_price': 'unit_price',
    'updatedAt_order': 'updated_at'
})

# parse/normalize timestamps & dates
fact_orders['created_at'] = pd.to_datetime(fact_orders['created_at'], errors='coerce', utc=True)
fact_orders['updated_at'] = pd.to_datetime(fact_orders['updated_at'], errors='coerce', utc=True)
fact_orders['order_date'] = fact_orders['created_at'].dt.date
fact_orders['delivery_date'] = pd.to_datetime(fact_orders['delivery_date_raw'], errors='coerce', utc=True).dt.date

# compute total price and basic validations
fact_orders['quantity'] = pd.to_numeric(fact_orders['quantity'], errors='coerce').fillna(0).astype(int)
fact_orders['unit_price'] = pd.to_numeric(fact_orders['unit_price'], errors='coerce')
fact_orders['total_price'] = fact_orders['quantity'] * fact_orders['unit_price']

# Basic data checks: log rows with missing important fields
missing_price = fact_orders[fact_orders['unit_price'].isna()]
if not missing_price.empty:
    print(f"WARNING: {len(missing_price)} fact rows missing unit_price. Review product joins.")

missing_order_date = fact_orders[fact_orders['order_date'].isna()]
if not missing_order_date.empty:
    print(f"WARNING: {len(missing_order_date)} fact rows missing order_date (created_at parsing failed).")

# select final fact columns in the order matching DDL
fact_orders_final = fact_orders[[
    'order_id', 'product_id', 'user_id', 'rider_id',
    'order_date', 'delivery_date', 'quantity', 'unit_price', 'total_price',
    'created_at', 'updated_at'
]].copy()

# dedupe dims (important when using append)
dim_product = dim_product.drop_duplicates(subset=['product_id'])
dim_user = dim_user.drop_duplicates(subset=['user_id'])
dim_rider = dim_rider.drop_duplicates(subset=['rider_id'])
dim_date = dim_date.drop_duplicates(subset=['date_id'])

# Optional: cast types to expected DB types (e.g., strings, numerics)
# --- 3. LOAD ---
# NOTE: to_sql with if_exists='append' can create duplicates on repeated runs.
# In production prefer:
#  - staging table + INSERT ... ON CONFLICT (upsert), or
#  - use COPY and then SQL upsert, or
#  - set unique constraints in DB and handle conflicts.

try:
    # Cast date_id back to datetime for SQL compatibility
    dim_date['date_id'] = pd.to_datetime(dim_date['date_id'])
    
    # Load the data
    dim_date.to_sql('dim_date', supabase_engine, if_exists='append', index=False)
    dim_product.to_sql('dim_product', supabase_engine, if_exists='append', index=False)
    dim_user.to_sql('dim_user', supabase_engine, if_exists='append', index=False)
    dim_rider.to_sql('dim_rider', supabase_engine, if_exists='append', index=False)
    fact_orders_final.to_sql('fact_orders', supabase_engine, if_exists='append', index=False, chunksize=5000)
    print("ETL completed: dims and fact appended to target.")
    
except Exception as e:
    print("ETL failed with error:", e)
    raise
