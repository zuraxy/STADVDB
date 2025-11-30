import os
import time
import urllib.parse
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.pool import QueuePool
from sqlalchemy.engine.url import make_url
from dotenv import load_dotenv

def load_env_variables():
    """Load environment variables from .env file

    Tolerant lookup: accept multiple common env var names for backward compatibility.
    Returns (mysql_conn_str, supabase_conn_str_optimized)
    """
    load_dotenv()

    # Prefer canonical names but accept common legacy/alternate names
    mysql_keys = ["MYSQL_CONNECTION_STRING", "MYSQL_CONN_STR", "MYSQL_URL", "MYSQL_CONNECTION"]
    supabase_keys = ["SUPABASE_CONNECTION_STRING", "SUPABASE_CONN_STR", "SUPABASE_POOL_STRING", "SUPABASE_CONNECTION"]

    def first_env(keys):
        for k in keys:
            v = os.environ.get(k)
            if v:
                return k, v
        return None, None

    used_mysql_key, mysql_conn_str = first_env(mysql_keys)
    used_sup_key, supabase_conn_str = first_env(supabase_keys)

    if mysql_conn_str is None:
        print("Warning: MYSQL connection string not found in environment. Checked keys: " + ", ".join(mysql_keys))
    elif used_mysql_key != mysql_keys[0]:
        print(f"Warning: using fallback env var '{used_mysql_key}' for MySQL connection string")

    if supabase_conn_str is None:
        print("Warning: SUPABASE connection string not found in environment. Checked keys: " + ", ".join(supabase_keys))
    elif used_sup_key != supabase_keys[0]:
        print(f"Warning: using fallback env var '{used_sup_key}' for Supabase connection string")

    # Optimize Supabase connection string by ensuring a reasonable connect_timeout param
    supabase_conn_str_optimized = supabase_conn_str
    if supabase_conn_str:
        try:
            parsed_url = urllib.parse.urlparse(supabase_conn_str)
            query_params = urllib.parse.parse_qs(parsed_url.query)
            # set or override connect_timeout (use list values to be compatible with urlencode doseq)
            query_params.setdefault('connect_timeout', ['30'])
            new_query = urllib.parse.urlencode(query_params, doseq=True)
            parsed_url_with_query = parsed_url._replace(query=new_query)
            # Ensure all components are strings before un-parsing
            parts = []
            for comp in parsed_url_with_query:
                if comp is None:
                    parts.append("")
                elif isinstance(comp, str):
                    parts.append(comp)
                else:
                    parts.append(str(comp))
            supabase_conn_str_optimized = urllib.parse.urlunparse(parts)
        except Exception as e:
            print(f"Warning: failed to parse/optimize SUPABASE connection string ({e}), using original value")

    return mysql_conn_str, supabase_conn_str_optimized

def create_robust_engine(conn_str, retries=5, delay=5, pool_size=5, max_overflow=10, name=None):
    """database engine + connection retry logic"""
    # print database
    label = name
    if not label:
        try:
            u = make_url(conn_str)
            label = f"{u.drivername}://{u.host}/{u.database}"
        except Exception:
            label = "database"

    for attempt in range(retries):
        try:
            print(f"[{label}] Connection attempt {attempt+1}/{retries}...")
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
            print(f"[{label}] Connection successful!")
            return engine
        except OperationalError as e:
            print(f"[{label}] Connection attempt {attempt+1} failed: {e}")
            if attempt < retries - 1:
                print(f"[{label}] Retrying in {delay} seconds...")
                time.sleep(delay)
            else:
                print(f"[{label}] All connection attempts failed.")
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