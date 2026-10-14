"""天氣解析的純函式。

判準：錯了會造成「系統性」偏誤的才測——
例如 -98 若被當缺值丟棄，等於只留下有下雨的時段（selection bias）。
"""
import gzip
from datetime import timedelta
from pathlib import Path

import pytest

from load_weather import (
    fetched_at_from, find_obs_counterpart, open_maybe_gz,
    parse_num, parse_precip, parse_rain_obs, parse_station, parse_text,
)


# ── parse_precip ────────────────────────────────────────

@pytest.mark.parametrize("raw, expected", [
    ("0.0",   (0.0, None)),
    ("2.5",   (2.5, None)),
    (" 0.5 ", (0.5, None)),
    ("-98",   (0.0, "-98")),    # 連續 6 小時無雨：是 0，不是缺值
    ("-98.0", (0.0, "-98")),    # 同一代碼的小數格式
    ("T",     (0.0, "T")),      # 雨跡
    ("-99",   (None, "-99")),
    ("-99.0", (None, "-99")),
    ("X",     (None, "X")),
    (None,    (None, None)),
])
def test_parse_precip_known_codes(raw, expected):
    assert parse_precip(raw) == expected


def test_parse_precip_unknown_code_keeps_raw_string():
    # 未知代碼不能靜靜變成 None：要留原字串，之後查得出來
    assert parse_precip("Y") == (None, "Y")
    assert parse_precip("-997") == (None, "-997")


# ── parse_num ───────────────────────────────────────────

@pytest.mark.parametrize("raw", ["-99", "-99.0", "990", "990.0", "-990.0", "X", "abc", None])
def test_parse_num_special_codes_are_missing(raw):
    assert parse_num(raw) is None


@pytest.mark.parametrize("raw, expected", [
    ("28.3", 28.3), ("0", 0.0), ("-2.5", -2.5), ("85", 85.0),
])
def test_parse_num_regular_values(raw, expected):
    assert parse_num(raw) == expected


def test_parse_text():
    assert parse_text("-99") is None
    assert parse_text(" 陰 ") == "陰"
    assert parse_text(None) is None


# ── 檔名與檔案 ──────────────────────────────────────────

def test_fetched_at_from_plain_and_gz_agree():
    a = fetched_at_from(Path("rain_20260820T1451+0800.json"))
    b = fetched_at_from(Path("rain_20260820T1451+0800.json.gz"))
    assert a == b
    assert a.utcoffset() == timedelta(hours=8)
    assert (a.hour, a.minute) == (14, 51)


def test_find_obs_counterpart(tmp_path):
    rain = tmp_path / "rain_20260820T1450+0800.json"
    rain.write_text("{}")
    assert find_obs_counterpart(rain) is None

    # 壓縮中斷時可能一個 .json、一個 .gz
    obs = tmp_path / "obs_20260820T1450+0800.json.gz"
    obs.write_bytes(gzip.compress(b"{}"))
    assert find_obs_counterpart(rain) == obs


def test_open_maybe_gz_reads_text(tmp_path):
    p = tmp_path / "x.json.gz"
    p.write_bytes(gzip.compress('{"a": "測站"}'.encode("utf-8")))
    with open_maybe_gz(p) as f:
        assert f.read() == '{"a": "測站"}'


# ── 單一測站解析 ────────────────────────────────────────

def make_station(**rain):
    return {
        "StationId": "C0A9C0",
        "StationName": "天母",
        "ObsTime": {"DateTime": "2026-09-09T15:10:00+08:00"},
        "GeoInfo": {
            # TWD67 放前面：解析不可依賴順序
            "Coordinates": [
                {"CoordinateName": "TWD67", "StationLatitude": "25.1", "StationLongitude": "121.5"},
                {"CoordinateName": "WGS84", "StationLatitude": "25.2", "StationLongitude": "121.6"},
            ],
            "StationAltitude": "36.0", "CountyName": "臺北市", "TownName": "士林區",
        },
        "RainfallElement": {
            "Past10Min": {"Precipitation": rain.get("p10", "0.0")},
            "Past1hr":   {"Precipitation": rain.get("p1h", "0.0")},
        },
    }


def test_parse_station_picks_wgs84_by_name():
    row = parse_station(make_station())
    assert row[4:6] == (25.2, 121.6)


def test_parse_rain_obs_maps_minus_98_to_zero():
    row = parse_rain_obs(make_station(p10="-98", p1h="1.5"), fetched_at=None)
    _, obs_time, p10, f10, p1h, f1h, *_ = row
    assert (p10, f10) == (0.0, "-98")
    assert (p1h, f1h) == (1.5, None)
    assert obs_time.utcoffset() == timedelta(hours=8)
