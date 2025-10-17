import pandas as pd
import traceback
from datetime import datetime

from etl_modules import (
    # Utils
    load_env_variables, create_robust_engine, execute_with_retry,
    
    # Extract
    extract_source_tables, get_last_etl_run,
    
    # Transform
    transform_product_dimension, transform_user_dimension, 
    transform_rider_dimension, transform_date_dimension,
    transform_fact_table,
    
    # Load
    load_dimension_table, load_date_dimension, 
    load_fact_table, record_etl_run
)

def main():
    start_time = datetime.now()
    try:
        # 1. Initialize connections
        mysql_conn_str, supabase_conn_str = load_env_variables()
        mysql_engine = create_robust_engine(mysql_conn_str)
        supabase_engine = create_robust_engine(supabase_conn_str, retries=5, delay=10)
        
        # 2. Extract data from source
        orders_df, order_items_df, products_df, users_df, riders_df, couriers_df = extract_source_tables(mysql_engine)
        
        # 3. Transform data into dimension and fact tables
        dim_product = transform_product_dimension(products_df)
        dim_user = transform_user_dimension(users_df)
        dim_rider = transform_rider_dimension(riders_df, couriers_df)
        dim_date, parsed_delivery_dates = transform_date_dimension(orders_df)
        fact_orders = transform_fact_table(order_items_df, orders_df, products_df, parsed_delivery_dates)
        
        print(f"Total fact records: {len(fact_orders)}")
        print(f"Records with missing product_id: {fact_orders['product_id'].isna().sum()}")
        print(f"Records with missing unit_price: {fact_orders['unit_price'].isna().sum()}")
        
        # 4. Get last ETL run time for incremental loading
        try:
            etl_runs = execute_with_retry(supabase_engine, get_last_etl_run)
            
            if len(etl_runs) > 0:
                run_date = pd.to_datetime(etl_runs.iloc[0]['run_date'], utc=True)
                print(f"Last ETL run was at: {run_date}")
            else:
                # No previous runs, do full load - use UTC-aware timestamp
                run_date = pd.Timestamp('1970-01-01', tz='UTC')
                print("No previous ETL runs found. Performing full load.")
        except Exception as e:
            print(f"Error checking last ETL run: {e}")
            print("Defaulting to full load.")
            run_date = pd.Timestamp('1970-01-01', tz='UTC')
        
        current_run_timestamp = datetime.now()
        
        # 5. Load data into data warehouse
        # Load dimensions first
        load_dimension_table(supabase_engine, dim_product, 'dim_product', 'product_id', run_date)
        load_dimension_table(supabase_engine, dim_user, 'dim_user', 'user_id', run_date)
        load_dimension_table(supabase_engine, dim_rider, 'dim_rider', 'rider_id', run_date)
        load_date_dimension(supabase_engine, dim_date)
        
        # Then load fact table
        load_fact_table(supabase_engine, fact_orders, run_date)
        
        # 6. Record successful ETL run
        record_etl_run(supabase_engine, current_run_timestamp)
        
        print(f"ETL completed successfully at {current_run_timestamp}")
        elapsed = datetime.now() - start_time
        print(f"ETL total runtime: {elapsed}")
        
    except Exception as e:
        print(f"Critical error in ETL process: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    main()