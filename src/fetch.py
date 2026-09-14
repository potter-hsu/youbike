import requests, time
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from db import connect
from load import main as load_main

URL = 'https://tcgbusfs.blob.core.windows.net/dotapp/youbike/v2/youbike_immediate.json'

BASE = Path(__file__).parent.parent
RAW_DIR = BASE / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)


FETCH_LOG_SQL = """
INSERT INTO fetch_log
    (started_at, duration_ms, status_code, etag, content_length,
     update_time, stations_received, saved_file, error_message)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
RETURNING fetch_id
"""

def parse_update_time(raw):
    """updateTime 為不帶時區的字串，須在 Python 端標記（決策：時區處理）"""
    if not raw:
        return None
    return datetime.strptime(raw, "%Y-%m-%d %H:%M:%S").replace(
        tzinfo=ZoneInfo("Asia/Taipei"))

def fetch_with_retry():
    for i in range(3):
        try:
            response = requests.get(URL, timeout=10)
            response.raise_for_status()
            response.json()          # 完整性驗證，殘缺 JSON 會進入 retry
            return response
        except (requests.exceptions.Timeout,
                requests.exceptions.ConnectionError,
                requests.exceptions.JSONDecodeError):
            if i != 2:
                time.sleep(2 ** i)
            else:
                raise


def write_fetch_log(cur, started_at, duration_ms, response, saved_file, error):
    """成功與失敗都要寫一列。
    失敗時 response 為 None，多數欄位取不到值——
    這正是決策 7 讓這些欄位允許 NULL 的原因。"""
    if response is None:
        params = (started_at, duration_ms, None, None, None,
                  None, None, None, error)
    else:
        data = response.json()
        params = (
            started_at,
            duration_ms,
            response.status_code,
            response.headers.get("ETag"),
            response.headers.get("Content-Length"),
            # updateTime 全站共用，屬「整包資料」的屬性（決策 6）
            parse_update_time(data[0].get("updateTime")) if data else None,
            len(data),
            saved_file,
            None,
        )
    cur.execute(FETCH_LOG_SQL, params)
    return cur.fetchone()[0]


def main():
    started_at = datetime.now(ZoneInfo("Asia/Taipei"))
    t0 = time.monotonic()

    response = None
    saved_file = None
    error = None

    try:
        response = fetch_with_retry()
        now = datetime.now(ZoneInfo("Asia/Taipei"))
        path = RAW_DIR / f"youbike_{now.strftime('%Y%m%dT%H%M%z')}.json"
        with open(path, "w", encoding="utf-8") as f:
            f.write(response.text)
        saved_file = path.name
        print(f"{now.isoformat()} saved {path.name} ({len(response.text)} bytes)")
    except Exception as e:
        # 抓取或存檔失敗：仍要留下紀錄，否則只能靠「沒有記錄」推斷
        error = f"{type(e).__name__}: {e}"
        print(f"{started_at.isoformat()} FETCH FAILED: {error}")

    duration_ms = int((time.monotonic() - t0) * 1000)

    # fetch_log 與 load 用同一個連線，確保 fetch_id 的外鍵有效
    with connect() as conn:
        with conn.cursor() as cur:
            fetch_id = write_fetch_log(
                cur, started_at, duration_ms, response, saved_file, error
            )
        conn.commit()

        # 抓取失敗時仍執行 load——先前積壓的檔案可能還沒入庫
        load_main(conn=conn, fetch_id=fetch_id)


if __name__ == "__main__":
    main()