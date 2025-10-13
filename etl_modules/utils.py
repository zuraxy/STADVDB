import os
import time
import urllib.parse
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.pool import QueuePool
from dotenv import load_dotenv

def load_env_variables():
    """Load environment variables from .env file"""
    load_dotenv()
    mysql_conn_str = os.environ.get("MYSQL_CONNECTION_STRING")
    supabase_conn_str = os.environ.get("SUPABASE_CONNECTION_STRING")
    
    # Optimize Supabase connection string
    parsed_url = urllib.parse.urlparse(supabase_conn_str)
    query_params = urllib.parse.parse_qs(parsed_url.query)
    query_params.update({
        'connect_timeout': ['30']  # Only keep the connect_timeout parameter
    })
    new_query = urllib.parse.urlencode(query_params, doseq=True)
    url_parts = list(parsed_url)
    url_parts[4] = new_query
    supabase_conn_str_optimized = urllib.parse.urlunparse(url_parts)
    
    return mysql_conn_str, supabase_conn_str_optimized

def create_robust_engine(conn_str, retries=5, delay=5, pool_size=5, max_overflow=10):
    """Create a database engine with connection retry logic"""
    for attempt in range(retries):
        try:
            print(f"Connection attempt {attempt+1}/{retries}...")
            engine = create_engine(
                conn_str,
                poolclass=QueuePool,
                pool_size=pool_size,
                max_overflow=max_overflow,
                pool_timeout=30,
                pool_pre_ping=True
            )
            # Test connection with a simple query
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            print("Connection successful!")
            return engine
        except OperationalError as e:
            print(f"Connection attempt {attempt+1} failed: {e}")
            if attempt < retries - 1:
                print(f"Retrying in {delay} seconds...")
                time.sleep(delay)
            else:
                print("All connection attempts failed.")
                raise

def execute_with_retry(engine, query_func, retries=3, delay=5):
    """Execute a database operation with retries"""
    for attempt in range(retries):
        try:
            return query_func(engine)
        except OperationalError as e:
            print(f"Database operation failed (attempt {attempt+1}): {e}")
            if attempt < retries - 1:
                print(f"Retrying in {delay} seconds...")
                time.sleep(delay)
            else:
                raise