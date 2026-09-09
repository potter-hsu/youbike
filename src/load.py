import json
import gzip
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from operator import itemgetter
from db import connect

BASE = Path(__file__).parent.parent
RAW_DIR = BASE / "data" / "raw"

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

SNAPSHOTS_SQL = """
            INSERT INTO snapshots (sno, info_time, available_rent_bikes,
                       available_return_bikes, act,
                       first_fetched_at, last_fetched_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (sno, info_time) DO UPDATE SET
                last_fetched_at = EXCLUDED.last_fetched_at,
                loaded_at       = now()
            """


def open_maybe_gz(path):
    """依副檔名決定用 gzip 還是一般開檔。
    gzip 預設為 binary 模式，需明確指定 'rt' 才能給 json.load。"""
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8")
    return open(path, "r", encoding="utf-8")


def fetched_at_from(path):
    """檔名 → 抓取時間。
    ⚠️ 不可用 path.stem：youbike_XXX.json.gz 的 stem 是 youbike_XXX.json，
    只會剝掉最後一層副檔名。改用第一個 '.' 之前的部分。"""
    ts_part = path.name.split(".", 1)[0].split("_", 1)[1]
    return datetime.strptime(ts_part, "%Y%m%dT%H%M%z")


def load_one_file(file_path, cur):
    fetched_at = fetched_at_from(file_path)

    with open_maybe_gz(file_path) as f:
        data = json.load(f)

    stations_rows = []
    for station in data:
        result = itemgetter('sno', 'sna', 'snaen', 'sarea', 'sareaen', 'ar',
                            'aren', 'latitude', 'longitude', 'Quantity')(station)
        stations_rows.append(result)

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
            fetched_at,
            fetched_at
        ))

    cur.executemany(STATIONS_SQL, stations_rows)
    cur.executemany(SNAPSHOTS_SQL, snapshot_rows)


def main():
    # 同時涵蓋壓縮與未壓縮的檔案。
    # 檔名前綴相同，故 sorted 後仍為時間順序。
    files = sorted(
        list(RAW_DIR.glob("youbike_*.json"))
        + list(RAW_DIR.glob("youbike_*.json.gz"))
    )[-100:]

    with connect() as conn:
        with conn.cursor() as cur:
            for f in files:
                try:
                    load_one_file(f, cur)
                except json.JSONDecodeError as e:
                    print(f"SKIP broken file: {f.name} ({e})")
        conn.commit()


if __name__ == "__main__":
    main()