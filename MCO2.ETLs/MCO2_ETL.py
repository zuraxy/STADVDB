import pandas as pd
import traceback
from datetime import datetime, timezone
import sys
import os
from pathlib import Path

# Add project root (the folder that contains "etl_modules") to sys.path so local package imports work
_this_file = Path(__file__).resolve()
# start search from the current file's parent
_search_start = _this_file.parent

_found_root = None
for _p in (_search_start, *list(_search_start.parents)):
    if (_p / "etl_modules").is_dir():
        _found_root = _p
        break

if _found_root:
    sys.path.insert(0, str(_found_root))
else:
    # fallback: add the script's grandparent (two levels up) to sys.path
    sys.path.insert(0, str(_this_file.parent.parent))

# Optionally uncomment for debugging:
# print("Added to sys.path:", sys.path[0])

from sqlalchemy import text  # Import text from SQLAlchemy
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB, TIMESTAMP

import uuid
import json

# Reuse the robust utilities from our existing ETL modules
from etl_modules.utils import load_env_variables, create_robust_engine

# Try to ensure the script prints UTF-8 safely on Windows consoles that default to cp1252.
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass


def main():
    start_time = datetime.now(timezone.utc)
    try:
        print("Starting one-shot narrow ETL (OrderItems -> orders (uuid, quantity, payload, timestamps))")

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
            SELECT OrderId AS source_order_id, quantity
            FROM OrderItems
            LIMIT 100000
            """,
            mysql_engine,
        )

        # 3) Basic transform: ensure integer quantity, drop nulls, and build new target columns
        print(f"Rows extracted: {len(order_items_df)}")

        # Keep original source_order_id for payload; coerce quantity only
        order_items_df['quantity'] = pd.to_numeric(order_items_df['quantity'], errors='coerce').astype('Int64')

        # Drop rows with missing quantity
        cleaned = order_items_df.dropna(subset=['quantity']).copy()
        cleaned = cleaned.astype({'quantity': 'int64'})
        print(f"Rows after cleaning: {len(cleaned)}")

        # Generate UUIDv4 for each target row (the target 'order_id' is a UUID)
        cleaned['order_id'] = [str(uuid.uuid4()) for _ in range(len(cleaned))]

        # Build a JSON payload column (will be written to Postgres jsonb)
        # Example payload: {"source_order_id": <original value>}
        cleaned['payload'] = cleaned['source_order_id'].apply(lambda v: {'source_order_id': None if pd.isna(v) else v})

        # Set created_at and updated_at (timezone-aware UTC). DB defaults exist, but we explicitly populate here.
        now_ts = datetime.now(timezone.utc)
        cleaned['created_at'] = now_ts
        cleaned['updated_at'] = now_ts

        # Reorder/prepare dataframe for target
        out_df = cleaned[['order_id', 'quantity', 'payload', 'created_at', 'updated_at']].copy()

        # 4) Load into target (truncate-then-insert, one-shot)
        print("Preparing target table: creating (if needed) then truncating and loading...")
        with supabase_engine.begin() as conn:
            # ensure uuid extension (for DB-side defaults if ever used)
            conn.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"'))
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS orders (
                        order_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                        quantity INTEGER NOT NULL,
                        payload JSONB,
                        created_at TIMESTAMPTZ DEFAULT now(),
                        updated_at TIMESTAMPTZ DEFAULT now()
                    )
                    """
                )
            )
            # safe truncate
            conn.execute(text("TRUNCATE TABLE orders"))

        # Use dtype mapping so pandas/SQLAlchemy will send payload as JSONB and order_id as UUID
        dtype_map = {
            'order_id': PG_UUID(),
            'payload': JSONB(),
            'created_at': TIMESTAMP(timezone=True),
            'updated_at': TIMESTAMP(timezone=True),
        }

        # Ensure payload column is actual dicts (SQLAlchemy's JSON adapter will handle them)
        out_df['payload'] = out_df['payload'].apply(lambda d: d if isinstance(d, dict) else (json.loads(d) if isinstance(d, str) else {}))

        out_df.to_sql(
            'orders',
            supabase_engine,
            if_exists='append',
            index=False,
            method='multi',
            chunksize=1000,
            dtype=dtype_map
        )

        print(f"Loaded rows: {len(out_df)} into orders")
        try:
            sample = pd.read_sql("SELECT order_id, quantity, payload, created_at FROM orders LIMIT 10", supabase_engine)
            print("Sample rows from target:")
            print(sample)
        except Exception as e:
            print(f"Warning: unable to read back sample from target ({e})")
        elapsed = datetime.now(timezone.utc) - start_time
        print(f"ETL completed successfully. Runtime: {elapsed}")

    except Exception as e:
        print(f"Critical error in narrow ETL: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    main()