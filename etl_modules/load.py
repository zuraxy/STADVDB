#commit
from sqlalchemy import text
from datetime import datetime
import pandas as pd
import time

def load_dimension_table(engine, df, table_name, id_column, run_date=None):
    """Generic function to load dimension tables with incremental update logic"""
    if run_date is not None:
        updated_records = df[df['updatedAt'] > run_date]
    else:
        updated_records = df
        
    print(f"Loading {len(updated_records)} updated records to {table_name}")
    
    if len(updated_records) > 0:
        with engine.begin() as conn:
            # Determine if we need a full or incremental load
            if len(updated_records) < len(df):
                ids_to_update = tuple(updated_records[id_column].tolist())
                if len(ids_to_update) == 1:
                    conn.execute(text(f"DELETE FROM {table_name} WHERE {id_column} = {ids_to_update[0]}"))
                else:
                    conn.execute(text(f"DELETE FROM {table_name} WHERE {id_column} IN {ids_to_update}"))
            else:
                conn.execute(text(f"TRUNCATE TABLE {table_name} CASCADE"))
            
            # Remove metadata columns before inserting
            columns_to_drop = ['updatedAt']
            if table_name == 'dim_user':
                columns_to_drop.append('date_of_birth_raw')
                
            updated_records.drop(columns=columns_to_drop, errors='ignore').to_sql(
                table_name,
                conn,
                if_exists='append',
                index=False
            )
            
            return len(updated_records)
    return 0

def load_date_dimension(engine, dim_date):
    """Load date dimension while skipping existing dates (by primary key)"""
    print(f"Preparing to load up to {len(dim_date)} date records")
    if len(dim_date) > 0:
        with engine.begin() as conn:
            # Fetch existing keys
            existing_ids = pd.read_sql("SELECT date_id FROM dim_date", conn)['date_id'].astype('int64')
            # Only insert new dates
            to_insert = dim_date[~dim_date['date_id'].isin(existing_ids)]

            print(f"Loading {len(to_insert)} date records")
            if len(to_insert) > 0:
                to_insert.to_sql(
                    'dim_date',
                    conn,
                    if_exists='append',
                    index=False,
                    method='multi',
                    chunksize=500
                )
                print(f"Loaded {len(to_insert)} date records")
                return len(to_insert)
            else:
                print("No new dates to load into dim_date.")
                return 0
    else:
        print("Warning: No dates to load into dim_date!")
        return 0

def load_fact_table(engine, fact_table, run_date=None):
    """Load fact table with incremental update logic"""
    if run_date is not None:
        updated_orders = fact_table[fact_table['updated_at'] > run_date]
    else:
        updated_orders = fact_table
        
    print(f"Loading {len(updated_orders)} updated fact records")
    
    if len(updated_orders) > 0:
        with engine.begin() as conn:
            if len(updated_orders) < len(fact_table):
                order_ids_to_update = updated_orders['order_id'].unique().tolist()
                if len(order_ids_to_update) == 1:
                    conn.execute(text("DELETE FROM fact_orders WHERE order_id = :order_id"), 
                               {'order_id': order_ids_to_update[0]})
                else:
                    # Use IN clause with parameterized query
                    placeholders = ','.join([f':id_{i}' for i in range(len(order_ids_to_update))])
                    params = {f'id_{i}': order_id for i, order_id in enumerate(order_ids_to_update)}
                    conn.execute(text(f"DELETE FROM fact_orders WHERE order_id IN ({placeholders})"), params)
            else:
                conn.execute(text("TRUNCATE TABLE fact_orders"))
            
            # Use pandas to_sql for bulk insert - it handles data types properly
            updated_orders.drop(columns=['updated_at'], errors='ignore').to_sql(
                'fact_orders', 
                conn, 
                if_exists='append', 
                index=False,
                method='multi',
                chunksize=1000  # Insert in batches of 1000 rows
            )
            print(f"Inserted {len(updated_orders)} fact records")
            return len(updated_orders)
    return 0

def record_etl_run(engine, timestamp=None):
    """Record the ETL run in the etl_runs table"""
    if timestamp is None:
        timestamp = datetime.now()
        
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO etl_runs (run_date)
            VALUES (:run_date)
        """), {'run_date': timestamp})
        
    print(f"ETL run recorded at {timestamp}")