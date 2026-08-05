import os
import sqlite3
import pandas as pd


def create_database_connection(db_path, db_name):

    #Create (or connect to) the SQLite database at db_path/db_name and return the open connection.

    try:
        os.makedirs(db_path, exist_ok=True)
        db_file = os.path.join(db_path, db_name)
        sql_connection = sqlite3.connect(db_file)
        return sql_connection
    except Exception as e:
        print(f"Error creating database connection: {e}")
        return None


def load_to_csv(df, target_file):
    # Save the final integrated dataset as a CSV file.
    try:
        os.makedirs(os.path.dirname(target_file), exist_ok=True)
        df.to_csv(target_file, index=False)
        return True
    except Exception as e:
        print(f"Error loading data to CSV: {e}")
        return False


def load_to_db(df, sql_connection, table_name):
  
    #Load the final integrated dataset into the given SQLite table, replacing it if it already exists.
    
    try:
        df.to_sql(table_name, sql_connection, if_exists='replace', index=False)
        return True
    except Exception as e:
        print(f"Error loading data to database: {e}")
        return False
