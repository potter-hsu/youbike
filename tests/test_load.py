"""YouBike 入庫與抓取紀錄。不連資料庫：以假 cursor 記錄送出的 SQL 與參數。"""
import json
from datetime import timedelta
from pathlib import Path

from fetch import parse_update_time, write_fetch_log
from load import STATIONS_SQL, SNAPSHOTS_SQL, fetched_at_from, load_one_file


class FakeCursor:
    def __init__(self):
        self.calls = []
        self.rowcount = 0

    def executemany(self, sql, rows):
        rows = list(rows)
        self.calls.append((sql, rows))
        self.rowcount = len(rows)

    def execute(self, sql, params):
        self.calls.append((sql, params))

    def fetchone(self):
        return (42,)


STATION = {
    "sno": "500101001", "sna": "YouBike2.0_捷運科技大樓站", "snaen": "MRT Technology Bldg.",
    "sarea": "大安區", "sareaen": "Daan Dist.", "ar": "復興南路二段235號前", "aren": "No.235",
    "latitude": 25.02605, "longitude": 121.5436, "Quantity": 28, "act": "1",
    "infoTime": "2026-09-14 11:28:04", "updateTime": "2026-09-14 11:28:52",
    "available_rent_bikes": 7, "available_return_bikes": 20,
}


def test_fetched_at_from_ignores_double_extension():
    # path.stem 只剝一層副檔名，.json.gz 會解析失敗
    a = fetched_at_from(Path("youbike_20260914T1125+0800.json"))
    b = fetched_at_from(Path("youbike_20260914T1125+0800.json.gz"))
    assert a == b
    assert a.utcoffset() == timedelta(hours=8)


def test_load_one_file(tmp_path):
    path = tmp_path / "youbike_20260914T1130+0800.json"
    path.write_text(json.dumps([STATION]), encoding="utf-8")
    cur = FakeCursor()

    load_one_file(path, cur)

    # 外鍵順序：stations 先於 snapshots（決策 8）
    assert [sql for sql, _ in cur.calls] == [STATIONS_SQL, SNAPSHOTS_SQL]

    sno, info_time, rent, ret, act, first_fetched, last_fetched = cur.calls[1][1][0]
    assert (sno, rent, ret, act) == ("500101001", 7, 20, "1")
    # infoTime 不帶時區，須標記為臺北時間，否則存成 UTC 會差 8 小時
    assert info_time.utcoffset() == timedelta(hours=8)
    assert (info_time.hour, info_time.minute) == (11, 28)
    # 抓取時間取自檔名而非 now()：補跑時才不會把處理延遲混進資料延遲（決策 2）
    assert first_fetched == last_fetched == fetched_at_from(path)


def test_parse_update_time():
    t = parse_update_time("2026-09-14 11:28:52")
    assert t.utcoffset() == timedelta(hours=8)
    assert parse_update_time("") is None
    assert parse_update_time(None) is None


def test_write_fetch_log_on_failure_keeps_error():
    # 抓取失敗也要留一列：只有 started_at、duration 與錯誤訊息
    cur = FakeCursor()
    fetch_id = write_fetch_log(cur, "T0", 1234, None, None, "Timeout: boom")
    params = cur.calls[0][1]
    assert fetch_id == 42
    assert params[0:2] == ("T0", 1234)
    assert params[-1] == "Timeout: boom"
    assert all(p is None for p in params[2:-1])
