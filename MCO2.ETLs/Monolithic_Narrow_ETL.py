import pandas as pd
import traceback
from datetime import datetime
import sys
from sqlalchemy import text  # Import text from SQLAlchemy

# Reuse the robust utilities from our existing ETL modules
from etl_modules.utils import load_env_variables, create_robust_engine

# Try to ensure the script prints UTF-8 safely on Windows consoles that default to cp1252.
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass


def main():
    start_time = datetime.now()
    try:
        print("Starting one-shot narrow ETL (OrderItems -> order_id, quantity)")

        # 1) Initialize DB connections (no incremental logic, one-shot only)
        mysql_conn_str, supabase_conn_str = load_env_variables()

        # Validate connection strings
        if not mysql_conn_str:
            raise ValueError("MySQL connection string is missing. Please set the appropriate environment variable.")
        if not supabase_conn_str:
            raise ValueError("Supabase connection string is missing. Please set the appropriate environment variable.")

        mysql_engine = create_robust_engine(mysql_conn_str, name="mysql-source")
        supabase_engine = create_robust_engine(supabase_conn_str, name="supabase-target")

        # 2) Extract minimal dataset from MySQL
        print("Extracting OrderItems (OrderId, quantity) from source...")
        order_items_df = pd.read_sql(
            """
            SELECT OrderId AS order_id, quantity
            FROM OrderItems
            """,
            mysql_engine,
        )

        # 3) Basic transform: ensure integer types and drop nulls if any
        print(f"Rows extracted: {len(order_items_df)}")
        order_items_df['order_id'] = pd.to_numeric(order_items_df['order_id'], errors='coerce').astype('Int64')
        order_items_df['quantity'] = pd.to_numeric(order_items_df['quantity'], errors='coerce').astype('Int64')
        cleaned = order_items_df.dropna(subset=['order_id', 'quantity'])
        cleaned = cleaned.astype({'order_id': 'int64', 'quantity': 'int64'})
        print(f"Rows after cleaning: {len(cleaned)}")

        # 4) Load into target (truncate-then-insert, one-shot)
        print("Preparing target table: truncating then loading...")
        with supabase_engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS order_items_narrow (
                        order_id INTEGER NOT NULL,
                        quantity INTEGER NOT NULL
                    )
                    """
                )
            )
            conn.execute(text("TRUNCATE TABLE order_items_narrow"))

        cleaned.to_sql(
            'order_items_narrow',
            supabase_engine,
            if_exists='append',
            index=False,
            method='multi',
            chunksize=1000,
        )

        print(f"Loaded rows: {len(cleaned)} into order_items_narrow")
        try:
            sample = pd.read_sql("SELECT order_id, quantity FROM order_items_narrow LIMIT 10", supabase_engine)
            print("Sample rows from target:")
            print(sample)
        except Exception as e:
            print(f"Warning: unable to read back sample from target ({e})")
        elapsed = datetime.now() - start_time
        print(f"ETL completed successfully. Runtime: {elapsed}")

    except Exception as e:
        print(f"Critical error in narrow ETL: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    main()

