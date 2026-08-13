import json
import psycopg
import os
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from operator import itemgetter

load_dotenv()

BASE = Path(__file__).parent.parent
RAW_DIR = BASE / "data" / "raw"
file_path = RAW_DIR / "youbike_20260810T1600+0800.json"
with open(file_path, "r", encoding="utf-8") as f:
    data = json.load(f)
stations_rows = []
for station in data:
    result = itemgetter('sno', 'sna', 'snaen', 'sarea', 'sareaen', 'ar',
                         'aren', 'latitude', 'longitude', 'Quantity')(station)
    stations_rows.append(result)

STATIONS_SQL = """
            INSERT INTO stations (sno, name_zh, name_en, area_zh, area_en, address_zh, address_en, latitude, longitude, quantity)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (sno) DO UPDATE SET
            name_zh      = EXCLUDED.name_zh,
            name_en      = EXCLUDED.name_en,
            area_zh      = EXCLUDED.area_zh,
            area_en      = EXCLUDED.area_en,
            address_zh   = EXCLUDED.address_zh,
            address_en   = EXCLUDED.address_en,
            latitude     = EXCLUDED.latitude,
            longitude    = EXCLUDED.longitude,
            quantity     = EXCLUDED.quantity,
            last_seen_at = now()
            """


snapshot_rows = []
for snapshot in data:
    naive = datetime.strptime(snapshot["infoTime"], "%Y-%m-%d %H:%M:%S")
    info_time = naive.replace(tzinfo=ZoneInfo("Asia/Taipei"))
    
    snapshot_rows.append((
        snapshot["sno"],
        info_time,  
        snapshot["available_rent_bikes"],
        snapshot["available_return_bikes"],
        snapshot["act"],
    ))
SNAPSHOTS_SQL = """
            INSERT INTO snapshots (sno, info_time, available_rent_bikes, available_return_bikes, act)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (sno, info_time) DO UPDATE SET last_fetched_at = now()
            """

with psycopg.connect(f"host=localhost port=5432 dbname=youbike user=postgres password={os.getenv('DB_PASSWORD')}") as conn:
    with conn.cursor() as cur:
        cur.executemany(STATIONS_SQL, stations_rows)
        cur.executemany(SNAPSHOTS_SQL, snapshot_rows)
        conn.commit()
        cur.execute("SELECT count(*) FROM snapshots;")
        result = cur.fetchone()
        print(result)