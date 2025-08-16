import os

def get_db_connection():
    database_url = os.getenv("DATABASE_URL")
    return database_url
