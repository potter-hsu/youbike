import json
from pathlib import Path
from datetime import datetime
from db import connect

BASE = Path(__file__).parent.parent
WEATHER_DIR = BASE / "data" / "weather"


# ── 特殊碼轉換 ──────────────────────────────────────────

PRECIP_SPECIAL = {
    "-98": (0.0, "-98"),   # 連續 6 小時無降水 → 語意是 0，不是缺值
    "T":   (0.0, "T"),     # 雨跡：有降水但量小於儀器刻度
    "-99": (None, "-99"),  # 缺值或資料異常
    "X":   (None, "X"),    # 儀器故障
}

NUM_SPECIAL = {"-99", "X", "990"}


def parse_precip(raw):
    """降雨值 → (數值, flag)。flag 為 None 表示正常觀測。"""
    if raw is None:
        return None, None
    raw = raw.strip()
    if raw in PRECIP_SPECIAL:
        return PRECIP_SPECIAL[raw]
    try:
        return float(raw), None
    except ValueError:
        return None, raw        # 未知代碼：存原字串，之後查得出來


def parse_num(raw):
    """溫濕風等要素 → 數值。特殊碼一律 None（不做 flag）。"""
    if raw is None:
        return None
    raw = raw.strip()
    if raw in NUM_SPECIAL:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def parse_text(raw):
    """文字欄位：-99 視為缺值。"""
    if raw is None:
        return None
    raw = raw.strip()
    return None if raw == "-99" else raw


# ── 解析單一測站 ────────────────────────────────────────

def parse_station(s):
    geo = s["GeoInfo"]
    # ⚠️ 座標陣列含 TWD67 與 WGS84，順序不保證，必須用名稱篩
    coord = next(c for c in geo["Coordinates"]
                 if c["CoordinateName"] == "WGS84")
    return (
        s["StationId"],
        s["StationName"],
        geo["CountyName"],
        geo["TownName"],
        float(coord["StationLatitude"]),
        float(coord["StationLongitude"]),
        float(geo["StationAltitude"]),
    )


def parse_rain_obs(s, fetched_at):
    r = s["RainfallElement"]
    p10, f10 = parse_precip(r["Past10Min"]["Precipitation"])
    p1h, f1h = parse_precip(r["Past1hr"]["Precipitation"])
    return (
        s["StationId"],
        datetime.fromisoformat(s["ObsTime"]["DateTime"]),
        p10, f10, p1h, f1h,
        fetched_at, fetched_at,
    )


def parse_weather_obs(s, fetched_at):
    w = s["WeatherElement"]
    return (
        s["StationId"],
        datetime.fromisoformat(s["ObsTime"]["DateTime"]),
        parse_text(w["Weather"]),
        parse_text(w["VisibilityDescription"]),
        parse_num(w["SunshineDuration"]),
        parse_num(w["WindDirection"]),
        parse_num(w["WindSpeed"]),
        parse_num(w["AirTemperature"]),
        parse_num(w["RelativeHumidity"]),
        parse_num(w["UVIndex"]),
        fetched_at, fetched_at,
    )


# ── SQL ────────────────────────────────────────────────

STATIONS_SQL = """
INSERT INTO weather_stations
    (station_id, station_name, county_name, town_name,
     latitude, longitude, altitude)
VALUES (%s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (station_id) DO UPDATE SET
    station_name = EXCLUDED.station_name,
    county_name  = EXCLUDED.county_name,
    town_name    = EXCLUDED.town_name,
    latitude     = EXCLUDED.latitude,
    longitude    = EXCLUDED.longitude,
    altitude     = EXCLUDED.altitude,
    last_seen_at = now()
"""

RAIN_SQL = """
INSERT INTO weather_obs
    (station_id, obs_time,
     precipitation_10min, precip_10min_flag,
     precipitation_1hr, precip_1hr_flag,
     first_fetched_at, last_fetched_at)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (station_id, obs_time) DO UPDATE SET
    precipitation_10min = EXCLUDED.precipitation_10min,
    precip_10min_flag   = EXCLUDED.precip_10min_flag,
    precipitation_1hr   = EXCLUDED.precipitation_1hr,
    precip_1hr_flag     = EXCLUDED.precip_1hr_flag,
    last_fetched_at     = EXCLUDED.last_fetched_at,
    loaded_at           = now()
"""

# ⚠️ 只更新氣象要素，不碰 precipitation_*
#    否則會把 RAIN_SQL 剛寫入的雨量蓋成 NULL
WEATHER_SQL = """
INSERT INTO weather_obs
    (station_id, obs_time,
     weather, visibility, sunshine_duration,
     wind_direction, wind_speed, air_temperature,
     relative_humidity, uv_index,
     first_fetched_at, last_fetched_at)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (station_id, obs_time) DO UPDATE SET
    weather           = EXCLUDED.weather,
    visibility        = EXCLUDED.visibility,
    sunshine_duration = EXCLUDED.sunshine_duration,
    wind_direction    = EXCLUDED.wind_direction,
    wind_speed        = EXCLUDED.wind_speed,
    air_temperature   = EXCLUDED.air_temperature,
    relative_humidity = EXCLUDED.relative_humidity,
    uv_index          = EXCLUDED.uv_index,
    last_fetched_at   = EXCLUDED.last_fetched_at,
    loaded_at         = now()
"""


# ── 主流程 ──────────────────────────────────────────────

def fetched_at_from(path):
    """檔名 rain_20260820T1451+0800.json → aware datetime"""
    ts = path.stem.split("_", 1)[1]
    return datetime.strptime(ts, "%Y%m%dT%H%M%z")


def load_pair(rain_path, obs_path, cur):
    fetched_at = fetched_at_from(rain_path)

    rain = json.load(open(rain_path, encoding="utf-8"))["records"]["Station"]
    obs = json.load(open(obs_path, encoding="utf-8"))["records"]["Station"]

    # 外鍵順序：測站必須先寫入
    cur.executemany(STATIONS_SQL, [parse_station(s) for s in rain])
    cur.executemany(STATIONS_SQL, [parse_station(s) for s in obs])

    cur.executemany(RAIN_SQL, [parse_rain_obs(s, fetched_at) for s in rain])
    cur.executemany(WEATHER_SQL, [parse_weather_obs(s, fetched_at) for s in obs])


def main():
    rain_files = sorted(WEATHER_DIR.glob("rain_*.json"))[-100:]

    with connect() as conn:
        with conn.cursor() as cur:
            for rain_path in rain_files:
                obs_path = rain_path.with_name(
                    rain_path.name.replace("rain_", "obs_", 1)
                )
                if not obs_path.exists():
                    print(f"SKIP: no matching obs file for {rain_path.name}")
                    continue
                try:
                    load_pair(rain_path, obs_path, cur)
                except json.JSONDecodeError as e:
                    print(f"SKIP broken file: {rain_path.name} ({e})")
        conn.commit()


if __name__ == "__main__":
    main()