import pandas as pd

def _singularize_simple(token: str) -> str:
    t = token
    if t.endswith('ies') and len(t) > 3:
        return t[:-3] + 'y'          # batteries -> battery
    if t.endswith('sses'):
        return t[:-2]                # classes -> class
    if t.endswith('es'):
        return t                     # keep clothes/shoes/etc.
    if t.endswith('s') and not t.endswith('ss'):
        return t[:-1]                # bags -> bag, toys -> toy, gadgets -> gadget
    return t

def transform_product_dimension(products_df):
    """Transform product data into dim_product table"""
    dim_product = products_df[['id', 'name', 'category', 'price', 'updatedAt']].copy()
    dim_product = dim_product.rename(columns={'id': 'product_id', 'name': 'name', 'price': 'current_price'})
    # normalize category
    cat = dim_product['category'].astype('string')
    cat = cat.str.strip().str.lower().str.replace(r'\s+', '', regex=True)
    dim_product['category'] = cat.fillna('').map(lambda x: _singularize_simple(x) if isinstance(x, str) else x).replace({'': None})
    dim_product = dim_product.drop_duplicates(subset=['product_id'])
    dim_product['updatedAt'] = pd.to_datetime(dim_product['updatedAt'], utc=True)
    return dim_product

def transform_user_dimension(users_df):
    """Transform user data into dim_user table"""
    dim_user = users_df[['id', 'city', 'country', 'gender', 'dateOfBirth', 'updatedAt']].copy()
    dim_user = dim_user.rename(columns={'id': 'user_id', 'dateOfBirth': 'date_of_birth_raw'})
    dim_user = dim_user.drop_duplicates(subset=['user_id'])

    # Parse date_of_birth with multiple formats
    dim_user['date_of_birth_raw'] = dim_user['date_of_birth_raw'].astype(str).str.strip().replace({'nan': None})
    s = dim_user['date_of_birth_raw']

    # known formats (iso is y-m-d, mdy is m/d/y)
    mask_iso = s.str.match(r'^\d{4}-\d{2}-\d{2}$', na=False) 
    mask_mdy = s.str.match(r'^\d{1,2}/\d{1,2}/\d{4}$', na=False)

    # Prepare an empty Series of dtype datetime64[ns]
    parsed = pd.Series(pd.NaT, index=s.index, dtype='datetime64[ns]')

    # Parse slices with explicit formats (fast + strict)
    if mask_iso.any():
        parsed.loc[mask_iso] = pd.to_datetime(s.loc[mask_iso], format='%Y-%m-%d', errors='coerce')
    if mask_mdy.any():
        parsed.loc[mask_mdy] = pd.to_datetime(s.loc[mask_mdy], format='%m/%d/%Y', errors='coerce')

    # Fallback: try pandas generic parser for any remaining non-null strings
    remaining = parsed.isna() & s.notna()
    if remaining.any():
        parsed.loc[remaining] = pd.to_datetime(s.loc[remaining], errors='coerce', infer_datetime_format=True)

    # Final column as python date (no timezone — DOB is a date)
    dim_user['date_of_birth'] = parsed.dt.date

    # Ensure updatedAt is UTC-aware for comparison
    dim_user['updatedAt'] = pd.to_datetime(dim_user['updatedAt'], utc=True)
    
    return dim_user

def transform_rider_dimension(riders_df, couriers_df):
    """Transform rider and courier data into dim_rider table"""
    riders_table = riders_df[['id', 'vehicleType', 'courierId', 'gender', 'updatedAt']].copy()
    riders_table = riders_table.rename(columns={
        'id': 'rider_id', 
        'vehicleType': 'vehicle_type', 
        'courierId': 'courier_id', 
        'updatedAt': 'rider_updatedAt'
    })
    
    couriers_table = couriers_df[['id', 'courier_name', 'updatedAt']].copy()
    couriers_table = couriers_table.rename(columns={'id': 'courier_id', 'updatedAt': 'courier_updatedAt'})

    # Merge riders and couriers table to one dimension table
    dim_rider = riders_table.merge(couriers_table, on='courier_id', how='left')

    # Use the most recent updatedAt 
    dim_rider['rider_updatedAt'] = pd.to_datetime(dim_rider['rider_updatedAt'], errors='coerce', utc=True)
    dim_rider['courier_updatedAt'] = pd.to_datetime(dim_rider['courier_updatedAt'], errors='coerce', utc=True)
    dim_rider['updatedAt'] = dim_rider[['rider_updatedAt', 'courier_updatedAt']].max(axis=1)

    # Final selection of columns matching our DW schema
    dim_rider = dim_rider[['rider_id', 'vehicle_type', 'courier_name', 'gender', 'updatedAt']]
    dim_rider = dim_rider.drop_duplicates(subset=['rider_id'])
    
    return dim_rider

def transform_date_dimension(orders_df):
    """Transform delivery dates into dim_date table"""
    s = orders_df['deliveryDate']

    # Normalize to strings and strip whitespace
    s_str = s.astype(str).str.strip().replace({'nan': None, 'NaT': None, 'None': None, '': None})

    # Prepare a UTC-aware Series
    parsed = pd.Series(pd.NaT, index=s_str.index, dtype='datetime64[ns, UTC]')

    # Only two known formats: YYYY-MM-DD and MM/DD/YYYY
    mask_iso = s_str.str.match(r'^\d{4}-\d{2}-\d{2}$', na=False)
    mask_mdy = s_str.str.match(r'^\d{1,2}/\d{1,2}/\d{4}$', na=False)

    if mask_iso.any():
        parsed.loc[mask_iso] = pd.to_datetime(
            s_str.loc[mask_iso], format='%Y-%m-%d', errors='coerce', utc=True
        )
    if mask_mdy.any():
        parsed.loc[mask_mdy] = pd.to_datetime(
            s_str.loc[mask_mdy], format='%m/%d/%Y', errors='coerce', utc=True
        )

    # Generic fallback for remaining values (handles e.g. "YYYY-MM-DD HH:MM:SS")
    remaining = parsed.isna() & s_str.notna()
    if remaining.any():
        parsed.loc[remaining] = pd.to_datetime(s_str.loc[remaining], errors='coerce', utc=True)

    # Distinct calendar days present in Orders
    dates_only = parsed.dropna().dt.date
    unique_dates = pd.Series(dates_only, dtype='object').drop_duplicates().sort_values()
    date_series = pd.to_datetime(unique_dates)

    dim_date = pd.DataFrame({
        'date_id': date_series.dt.strftime('%Y%m%d').astype('int64'),
        'year': date_series.dt.year.astype('int16'),
        'quarter': date_series.dt.quarter.astype('int16'),
        'month': date_series.dt.month.astype('int16'),
        'day': date_series.dt.day.astype('int16'),
        'day_of_week': date_series.dt.dayofweek.astype('int16'),
        'is_weekend': date_series.dt.dayofweek.isin([5, 6]).astype('bool'),
    })

    # Return parsed delivery datetimes to keep the existing function signature
    return dim_date, parsed

def transform_fact_table(order_items_df, orders_df, products_df, parsed_delivery_dates):
    """Transform data into fact_orders table"""
    orders_df = orders_df.rename(columns={'id':'order_id', 'updatedAt': 'orders_updated_at'})
    order_items_df = order_items_df.rename(columns={'OrderId':'order_id','updatedAt': 'order_items_updated_at'})

    # Join order_items with orders to get all needed columns
    fact_orders = order_items_df.merge(
        orders_df,
        on='order_id',
        how='left',
        suffixes=('_item', '_order')
    )

    # Bring in product price
    fact_orders = fact_orders.merge(
        products_df[['id', 'price']],
        left_on='ProductId',
        right_on='id',
        how='left'
    ).drop(columns=['id'])

    # After all merges, find the most recent updatedAt timestamp
    fact_orders['orders_updated_at'] = pd.to_datetime(fact_orders['orders_updated_at'], errors='coerce', utc=True)
    fact_orders['order_items_updated_at'] = pd.to_datetime(fact_orders['order_items_updated_at'], errors='coerce', utc=True)
    fact_orders['most_recent_updated_at'] = fact_orders[['orders_updated_at', 'order_items_updated_at']].max(axis=1)

    # Convert delivery date to match the date_id format in dim_date
    fact_orders['delivery_date'] = pd.to_datetime(fact_orders['deliveryDate'], errors='coerce', utc=True).dt.date
    fact_orders['delivery_date'] = fact_orders['delivery_date'].map(lambda d: int(d.strftime('%Y%m%d')) if pd.notnull(d) else None)

    # Calculate total_price
    fact_orders['unit_price'] = fact_orders['price']
    fact_orders['total_price'] = fact_orders['quantity'] * fact_orders['unit_price']

    # Create fact_id as a simple auto-increment
    fact_orders['fact_id'] = range(1, len(fact_orders) + 1)

    # Select columns to keep and rename to match fact table schema
    fact_orders_final = fact_orders[[
        'fact_id',
        'order_id',
        'ProductId',
        'userId',
        'deliveryRiderId',
        'delivery_date',
        'quantity',
        'unit_price',
        'total_price',
        'most_recent_updated_at'
    ]].rename(columns={
        'ProductId': 'product_id',
        'userId': 'user_id',
        'deliveryRiderId': 'rider_id',
        'delivery_date': 'delivery_date_id',
        'most_recent_updated_at': 'updated_at'
    })

    # Handle missing values and ensure correct data types
    fact_orders_final['fact_id'] = fact_orders_final['fact_id'].astype('int64')
    fact_orders_final['order_id'] = fact_orders_final['order_id'].astype('int64')
    fact_orders_final['product_id'] = fact_orders_final['product_id'].astype('int32')
    fact_orders_final['user_id'] = fact_orders_final['user_id'].astype('int32')
    fact_orders_final['rider_id'] = fact_orders_final['rider_id'].fillna(-1).astype('int32')
    fact_orders_final['quantity'] = fact_orders_final['quantity'].fillna(0).astype('int32')
    fact_orders_final['unit_price'] = fact_orders_final['unit_price'].fillna(0).astype('float')
    fact_orders_final['total_price'] = fact_orders_final['total_price'].fillna(0).astype('float')
    fact_orders_final['updated_at'] = pd.to_datetime(fact_orders_final['updated_at'], utc=True)
    
    return fact_orders_final