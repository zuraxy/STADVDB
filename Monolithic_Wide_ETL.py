import pandas as pd
from datetime import datetime
from sqlalchemy import text

from etl_modules.utils import load_env_variables, create_robust_engine
from etl_modules.extract import extract_source_tables

# Local helpers (reuse logic similar to your dim transforms)
def _singularize_simple(token: str) -> str:
    t = token or ""
    t = t.strip().lower()
    if t.endswith('ies') and len(t) > 3:
        return t[:-3] + 'y'
    if t.endswith('sses'):
        return t[:-2]
    if t.endswith('es'):
        return t
    if t.endswith('s') and not t.endswith('ss'):
        return t[:-1]
    return t or None

def _normalize_gender(value):
    if pd.isna(value):
        return None
    s = str(value).strip().lower()
    if s in ('f', 'female'):
        return 'F'
    if s in ('m', 'male'):
        return 'M'
    return None

def build_wide_df(orders_df, order_items_df, products_df, users_df, riders_df, couriers_df) -> pd.DataFrame:
    # Rename for clarity
    orders = orders_df.rename(columns={'id': 'order_id'})
    order_items = order_items_df.rename(columns={'OrderId': 'order_id', 'ProductId': 'product_id'})
    products = products_df.rename(columns={'id': 'product_id', 'name': 'product_name'})
    users = users_df.rename(columns={'id': 'user_id'})
    riders = riders_df.rename(columns={'id': 'rider_id'})
    couriers = couriers_df.rename(columns={'id': 'courier_id'})

    # Merge item -> order
    wide = order_items.merge(
        orders,
        on='order_id',
        how='left',
        suffixes=('_item', '_order')
    )

    # Merge product
    wide = wide.merge(
        products[['product_id','productCode','category','description','product_name','price','createdAt','updatedAt']],
        on='product_id',
        how='left'
    )

    # Merge user
    wide = wide.merge(
        users[['user_id','username','firstName','lastName','address1','address2','city','country','zipCode','phoneNumber','dateOfBirth','gender','createdAt','updatedAt']],
        left_on='userId',
        right_on='user_id',
        how='left'
    )

    # Merge rider and courier
    wide = wide.merge(
        riders[['rider_id','firstName','lastName','vehicleType','courierId','age','gender','createdAt','updatedAt']],
        left_on='deliveryRiderId',
        right_on='rider_id',
        how='left'
    )
    wide = wide.merge(
        couriers[['courier_id','courier_name','createdAt','updatedAt']],
        left_on='courierId',
        right_on='courier_id',
        how='left',
        suffixes=('_courier_created','_courier_updated')  # we'll rename later
    )

    # Normalize/derive fields
    # Timestamps
    to_ts_utc = lambda s: pd.to_datetime(s, errors='coerce', utc=True)

    wide['order_created_at']  = to_ts_utc(wide['createdAt_order'])
    wide['order_updated_at']  = to_ts_utc(wide['updatedAt_order'])
    wide['item_created_at']   = to_ts_utc(wide['createdAt_item'])
    wide['item_updated_at']   = to_ts_utc(wide['updatedAt_item'])

    # Delivery date raw + parsed
    wide['delivery_date_raw'] = wide['deliveryDate']
    delivery_ts = to_ts_utc(wide['deliveryDate'])
    wide['delivery_ts_utc']   = delivery_ts
    wide['delivery_date_id']  = delivery_ts.dt.strftime('%Y%m%d').astype('Int64')

    # Product data
    wide['product_code']     = wide['productCode']
    wide['product_category'] = wide['category'].astype('string').str.strip().str.lower().str.replace(r'\s+', '', regex=True).map(_singularize_simple)
    wide['unit_price']       = wide['price'].fillna(0).astype('float')
    wide['product_name']     = wide['product_name']
    wide['total_price']      = (wide['quantity'].fillna(0).astype('int') * wide['unit_price']).astype('float')

    # User snapshot + normalization
    wide['user_username']     = wide['username']
    wide['user_first_name']   = wide['firstName']
    wide['user_last_name']    = wide['lastName']
    wide['user_address1']     = wide['address1']
    wide['user_address2']     = wide['address2']
    wide['user_city']         = wide['city']
    wide['user_country']      = wide['country']
    wide['user_zip_code']     = wide['zipCode']
    wide['user_phone_number'] = wide['phoneNumber']
    wide['user_gender']       = wide['gender_order'].apply(_normalize_gender) if 'gender_order' in wide.columns else wide['gender'].apply(_normalize_gender)
    # Parse DOB (try ISO and M/D/Y, else coerce)
    dob_raw = wide['dateOfBirth'].astype(str).str.strip().replace({'nan': None})
    mask_iso = dob_raw.str.match(r'^\d{4}-\d{2}-\d{2}$', na=False)
    mask_mdy = dob_raw.str.match(r'^\d{1,2}/\d{1,2}/\d{4}$', na=False)
    dob_parsed = pd.Series(pd.NaT, index=dob_raw.index, dtype='datetime64[ns]')
    if mask_iso.any():
        dob_parsed.loc[mask_iso] = pd.to_datetime(dob_raw.loc[mask_iso], format='%Y-%m-%d', errors='coerce')
    if mask_mdy.any():
        dob_parsed.loc[mask_mdy] = pd.to_datetime(dob_raw.loc[mask_mdy], format='%m/%d/%Y', errors='coerce')
    remaining = dob_parsed.isna() & dob_raw.notna()
    if remaining.any():
        dob_parsed.loc[remaining] = pd.to_datetime(dob_raw.loc[remaining], errors='coerce', infer_datetime_format=True)
    wide['user_dob_date']     = dob_parsed.dt.date
    wide['user_updated_at']   = to_ts_utc(wide['updatedAt'])  # user updatedAt

    # Rider + courier snapshot
    wide['rider_first_name']  = wide['firstName_rider']
    wide['rider_last_name']   = wide['lastName_rider']
    wide['rider_vehicle_type']= wide['vehicleType']
    wide['rider_age']         = wide['age']
    wide['rider_gender']      = wide['gender_rider']
    wide['courier_name']      = wide['courier_name']
    rider_upd = to_ts_utc(wide['updatedAt_rider'])
    courier_upd = to_ts_utc(wide['updatedAt_courier_updated'])
    wide['rider_courier_updated_at'] = pd.concat([rider_upd.rename('r'), courier_upd.rename('c')], axis=1).max(axis=1)

    # Derived calendar from delivery_ts_utc
    wide['cal_year']        = delivery_ts.dt.year.astype('Int64')
    wide['cal_quarter']     = delivery_ts.dt.quarter.astype('Int64')
    wide['cal_month']       = delivery_ts.dt.month.astype('Int64')
    wide['cal_day']         = delivery_ts.dt.day.astype('Int64')
    wide['cal_day_of_week'] = delivery_ts.dt.dayofweek.astype('Int64')
    wide['cal_is_weekend']  = delivery_ts.dt.dayofweek.isin([5,6])

    # Final selection + rename to DW_OrdersWide schema
    out = wide[[
        'order_id','product_id','user_id','rider_id',
        'orderNumber','order_created_at','order_updated_at',
        'delivery_date_raw','delivery_ts_utc','delivery_date_id',
        'quantity','notes','item_created_at','item_updated_at',
        'product_code','product_name','product_category','unit_price','total_price',
        'user_username','user_first_name','user_last_name','user_address1','user_address2',
        'user_city','user_country','user_zip_code','user_phone_number','user_gender','user_dob_date','user_updated_at',
        'rider_first_name','rider_last_name','rider_vehicle_type','rider_age','rider_gender','courier_name','rider_courier_updated_at',
        'cal_year','cal_quarter','cal_month','cal_day','cal_day_of_week','cal_is_weekend'
    ]].rename(columns={
        'orderNumber': 'order_number'
    })

    # Types and null handling
    out['quantity'] = out['quantity'].fillna(0).astype('int32')
    out['unit_price'] = out['unit_price'].fillna(0).astype('float')
    out['total_price'] = out['total_price'].fillna(0).astype('float')

    return out

def main():
    mysql_conn_str, supabase_conn_str = load_env_variables()
    mysql_engine = create_robust_engine(mysql_conn_str, name="mysql")
    pg_engine = create_robust_engine(supabase_conn_str, name="postgres")

    # Extract
    orders_df, order_items_df, products_df, users_df, riders_df, couriers_df = extract_source_tables(mysql_engine)

    # Build wide dataframe
    wide_df = build_wide_df(orders_df, order_items_df, products_df, users_df, riders_df, couriers_df)

    print(f"Wide rows to load: {len(wide_df)}")

    # Full rebuild: truncate and reload
    with pg_engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE DW_OrdersWide RESTART IDENTITY CASCADE"))

    # Load
    # Use method='multi' to batch insert efficiently
    wide_df.to_sql(
        'DW_OrdersWide',
        pg_engine,
        if_exists='append',
        index=False,
        method='multi',
        chunksize=1000
    )

    print("DW_OrdersWide load complete.")

if __name__ == "__main__":
    main()

# make sure this schema exists in postgresql:
# -- Create denormalized wide table (full rebuilds per run)
# 
# DROP TABLE IF EXISTS DW_OrdersWide CASCADE;
# 
# CREATE TABLE DW_OrdersWide (
#   fact_id              BIGSERIAL PRIMARY KEY,
# 
#   -- Natural keys
#   order_id             INT NOT NULL,
#   product_id           INT NOT NULL,
#   user_id              INT NULL,
#   rider_id             INT NULL,
# 
#   -- Order attributes
#   order_number         VARCHAR(255) NULL,
#   order_created_at     TIMESTAMP WITH TIME ZONE NOT NULL,
#   order_updated_at     TIMESTAMP WITH TIME ZONE NOT NULL,
# 
#   delivery_date_raw    VARCHAR(255) NULL,
#   delivery_ts_utc      TIMESTAMP WITH TIME ZONE NULL,
#   delivery_date_id     INT NULL,
# 
#   -- Order item attributes
#   quantity             INT NOT NULL DEFAULT 0,
#   notes                VARCHAR(255) NULL,
#   item_created_at      TIMESTAMP WITH TIME ZONE NOT NULL,
#   item_updated_at      TIMESTAMP WITH TIME ZONE NOT NULL,
# 
#   -- Product snapshot
#   product_code         VARCHAR(255) NULL,
#   product_name         VARCHAR(255) NULL,
#   product_category     VARCHAR(255) NULL,
#   unit_price           DOUBLE PRECISION NOT NULL DEFAULT 0,
#   total_price          DOUBLE PRECISION NOT NULL DEFAULT 0,
# 
#   -- User snapshot
#   user_username        VARCHAR(255) NULL,
#   user_first_name      VARCHAR(255) NULL,
#   user_last_name       VARCHAR(255) NULL,
#   user_address1        VARCHAR(255) NULL,
#   user_address2        VARCHAR(255) NULL,
#   user_city            VARCHAR(255) NULL,
#   user_country         VARCHAR(255) NULL,
#   user_zip_code        VARCHAR(50) NULL,
#   user_phone_number    VARCHAR(50) NULL,
#   user_gender          CHAR(1) NULL,
#   user_dob_date        DATE NULL,
#   user_updated_at      TIMESTAMP WITH TIME ZONE NOT NULL,
# 
#   -- Rider + Courier snapshot
#   rider_first_name     VARCHAR(255) NULL,
#   rider_last_name      VARCHAR(255) NULL,
#   rider_vehicle_type   VARCHAR(255) NULL,
#   rider_age            INT NULL,
#   rider_gender         VARCHAR(10) NULL,
#   courier_name         VARCHAR(255) NULL,
#   rider_courier_updated_at TIMESTAMP WITH TIME ZONE NULL,
# 
#   -- Derived calendar components
#   cal_year             SMALLINT NULL,
#   cal_quarter          SMALLINT NULL,
#   cal_month            SMALLINT NULL,
#   cal_day              SMALLINT NULL,
#   cal_day_of_week      SMALLINT NULL,
#   cal_is_weekend       BOOLEAN NULL,
# 
#   -- Ingestion metadata
#   row_ingested_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
# 
#   -- Uniqueness for idempotency
#   CONSTRAINT uq_order_item UNIQUE (order_id, product_id),
# 
#   -- Data quality checks
#   CONSTRAINT chk_qty_nonneg CHECK (quantity >= 0),
#   CONSTRAINT chk_unit_price_nonneg CHECK (unit_price >= 0),
#   CONSTRAINT chk_total_price_nonneg CHECK (total_price >= 0),
#   CONSTRAINT chk_user_gender CHECK (user_gender IN ('F','M') OR user_gender IS NULL)
# );
# 
# CREATE INDEX ix_dw_orderswide_order ON DW_OrdersWide (order_id);
# CREATE INDEX ix_dw_orderswide_user ON DW_OrdersWide (user_id);
# CREATE INDEX ix_dw_orderswide_rider ON DW_OrdersWide (rider_id);
# CREATE INDEX ix_dw_orderswide_product ON DW_OrdersWide (product_id);
# CREATE INDEX ix_dw_orderswide_delivery_date ON DW_OrdersWide (delivery_date_id);
# CREATE INDEX ix_dw_orderswide_updated_at ON DW_OrdersWide (item_updated_at, order_updated_at);

