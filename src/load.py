import json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import os
from dotenv import load_dotenv

load_dotenv()

BASE = Path(__file__).parent.parent
RAW_DIR = BASE / "data" / "raw"
file_path = RAW_DIR / "youbike_20260810T1600+0800.json"
with open(file_path, "r", encoding="utf-8") as f:
    data = json.load(f)
for station in data[:3]:
    sno = station["sno"]
    
    naive = datetime.strptime(station["infoTime"], "%Y-%m-%d %H:%M:%S")
    aware = naive.replace(tzinfo=ZoneInfo("Asia/Taipei"))
    
    print(sno, aware)

import psycopg

with psycopg.connect(f"host=localhost port=5432 dbname=youbike user=postgres password={os.getenv('DB_PASSWORD')}") as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM stations;")
        result = cur.fetchone()
        print(result)