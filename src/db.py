import os
import psycopg
from dotenv import load_dotenv

load_dotenv()

def connect():
    return psycopg.connect(
        f"host={os.getenv('DB_HOST', 'localhost')} "
        f"port={os.getenv('DB_PORT', '5432')} "
        f"dbname={os.getenv('DB_NAME', 'youbike')} "
        f"user={os.getenv('DB_USER', 'postgres')} "
        f"password={os.getenv('DB_PASSWORD')}"
    )