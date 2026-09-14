import json
import gzip
import time
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from operator import itemgetter
from db import connect

BASE = Path(__file__).parent.parent
RAW_DIR = BASE / "data" / "raw"


def open_maybe_gz(path):
    """依副檔名決定用 gzip 還是一般開檔。
    gzip 預設為 binary 模式，需明確指定 'rt' 才能給 json.load。"""
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8")
    return open(path, "r", encoding="utf-8")


def fetched_at_from(path):
    """檔名 → 抓取時間。
    ⚠️ 不可用 path.stem：youbike_XXX.json.gz 的 stem 是 youbike_XXX.json，
    只會剝掉最後一層副檔名。改取第一個 '.' 之前的部分。"""
    ts_part = path.name.split(".", 1)[0].split("_", 1)[1]
    return datetime.strptime(ts_part, "%Y%m%dT%H%M%z")


STATIONS_SQL = """
INSERT INTO stations (sno, name_zh, name_en, area_zh, area_en,
                      address_zh, address_en, latitude, longitude, quantity)
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

LOAD_LOG_SQL = """
INSERT INTO load_log
    (fetch_id, started_at, duration_ms,
     files_processed, files_skipped, rows_affected, error_message)
VALUES (%s, %s, %s, %s, %s, %s, %s)
"""


def load_one_file(file_path, cur):
    """回傳這個檔案影響的列數。"""
    fetched_at = fetched_at_from(file_path)

    with open_maybe_gz(file_path) as f:
        data = json.load(f)

    stations_rows = []
    for station in data:
        stations_rows.append(itemgetter(
            'sno', 'sna', 'snaen', 'sarea', 'sareaen', 'ar',
            'aren', 'latitude', 'longitude', 'Quantity')(station))

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
            fetched_at,
        ))

    # 外鍵順序：stations 必須先寫（決策 8）
    cur.executemany(STATIONS_SQL, stations_rows)
    cur.executemany(SNAPSHOTS_SQL, snapshot_rows)
    # upsert 下 rowcount 無法區分插入與更新，故只記合計（見 schema_design）
    return cur.rowcount


def main(conn=None, fetch_id=None):
    """conn 為 None 時自行建立連線（單獨執行 load.py 的情況）。
    由 fetch.py 呼叫時共用同一連線，使 load_log.fetch_id 的外鍵有效。"""
    own_conn = conn is None
    if own_conn:
        conn = connect()

    started_at = datetime.now(ZoneInfo("Asia/Taipei"))
    t0 = time.monotonic()

    files = sorted(
        list(RAW_DIR.glob("youbike_*.json"))
        + list(RAW_DIR.glob("youbike_*.json.gz"))
    )[-100:]

    processed = 0
    skipped = 0
    rows = 0
    errors = []

    try:
        with conn.cursor() as cur:
            for f in files:
                try:
                    rows += load_one_file(f, cur)
                    processed += 1
                except json.JSONDecodeError as e:
                    # 檔案本身壞掉，重試無意義 → 跳過並記錄
                    # 不捕捉其他例外：DB 連線失敗不該被靜靜跳過
                    skipped += 1
                    errors.append(f"{f.name}: {e}")
                    print(f"SKIP broken file: {f.name} ({e})")
        conn.commit()
    except Exception as e:
        conn.rollback()
        errors.append(f"{type(e).__name__}: {e}")
        raise
    finally:
        duration_ms = int((time.monotonic() - t0) * 1000)
        # log 另開交易：即使上面 rollback，這一列仍要留下
        try:
            with conn.cursor() as cur:
                cur.execute(LOAD_LOG_SQL, (
                    fetch_id, started_at, duration_ms,
                    processed, skipped, rows,
                    "; ".join(errors)[:2000] if errors else None,
                ))
            conn.commit()
        except Exception as e:
            print(f"WARN: failed to write load_log ({e})")

        if own_conn:
            conn.close()


if __name__ == "__main__":
    main()