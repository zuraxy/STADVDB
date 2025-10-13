import pandas as pd
from datetime import datetime
from sqlalchemy import text

def extract_source_tables(mysql_engine):
    """Extract all required tables from source database"""
    orders_df = pd.read_sql(
        """
        SELECT id, orderNumber, userId, deliveryDate, deliveryRiderId, createdAt, updatedAt
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
    
    return orders_df, order_items_df, products_df, users_df, riders_df, couriers_df

def get_last_etl_run(engine):
    """Retrieve the last ETL run timestamp"""
    etl_runs = pd.read_sql(
        "SELECT run_date FROM etl_runs ORDER BY run_date DESC LIMIT 1",
        engine
    )
    return etl_runs