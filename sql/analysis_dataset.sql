-- 分析資料集：站點層級的車輛數變化 × 對應測站的天氣
--
-- 每一列 = 某站在某個 info_time 的觀測，包含：
--   - 與前一筆的車輛數差值（delta）及其標準化值（delta_per_min）
--   - 該時刻對應的降雨與溫度
--
-- 用法（日期為具名參數，勿用 f-string 拼接）：
--   sql = open('sql/analysis_dataset.sql').read()
--   df = pd.read_sql(sql, conn, params={'start': '2026-08-21', 'end': '2026-08-25'})
--
-- ── 三個 WHERE 條件對應的決策 ──────────────────────────
--   last_fetched_at - info_time < 15 min
--       決策 9：資料延遲不在寫入時過濾，門檻留給查詢層
--   act = '1' AND prev_act = '1'
--       決策 4：act 轉換是結構性斷點，跨越斷點的差值非騎乘行為
--   info_time - prev_time BETWEEN 1 min AND 15 min
--       排除跨越失聯期的假差值（東門站失聯 532 天，恢復時差值會失真）
--
-- ── 兩組空間對應 ──────────────────────────────────────
--   降雨 → station_weather_map（50 個低海拔測站，avg 873m）
--   溫度 → station_temp_map（6 個低海拔綜觀站，avg 2869m）
--   分開的理由見決策 13：71 個雨量站中僅 9 站有溫度，
--   共用一張表時溫度缺失率達 100%
--
-- ── 時間對齊 ──────────────────────────────────────────
--   決策 12：info_time 往下取整到 10 分鐘，配對「該時刻之前」的天氣。
--   Past10Min 為過去 10 分鐘累積，取後一筆會納入觀測時點之後的降雨
--   → look-ahead bias。寧可承受測量誤差，不引入內生性。
--
-- ⚠️ 建模注意：同一測站底下的站點共用天氣值，誤差項不獨立
--    → 標準誤需以 station_id 為層級 cluster

WITH base AS (
    SELECT
        s.sno,
        s.info_time,
        s.available_rent_bikes,
        s.available_return_bikes,
        s.act,
        LAG(s.available_rent_bikes) OVER w AS prev_bikes,
        LAG(s.info_time)            OVER w AS prev_time,
        LAG(s.act)                  OVER w AS prev_act
    FROM snapshots s
    WHERE s.info_time >= %(start)s
      AND s.info_time <  %(end)s
      AND s.last_fetched_at - s.info_time < interval '15 min'
    WINDOW w AS (PARTITION BY s.sno ORDER BY s.info_time)
),
aligned AS (
    SELECT
        b.*,
        -- 決策 12：往下取整到 10 分鐘
        date_trunc('hour', b.info_time)
            + interval '10 min' * floor(extract(minute from b.info_time) / 10)
            AS obs_slot
    FROM base b
)
SELECT
    a.sno,
    a.info_time,
    a.obs_slot,
    a.available_rent_bikes,
    a.available_return_bikes,
    -- 實際可用容量（見 schema_design 第三節：不可用 quantity，gap 是動態的）
    a.available_rent_bikes + a.available_return_bikes AS capacity,
    a.available_rent_bikes - a.prev_bikes AS delta,
    EXTRACT(EPOCH FROM (a.info_time - a.prev_time)) / 60 AS gap_min,
    (a.available_rent_bikes - a.prev_bikes)
        / (EXTRACT(EPOCH FROM (a.info_time - a.prev_time)) / 60) AS delta_per_min,

    wr.precipitation_10min,
    wr.precipitation_1hr,
    wr.precip_10min_flag,
    wt.air_temperature,
    wt.relative_humidity,

    mw.station_id  AS rain_station,
    mw.distance_m  AS rain_dist_m,
    mt.station_id  AS temp_station,
    mt.distance_m  AS temp_dist_m
FROM aligned a
JOIN station_weather_map mw ON a.sno = mw.sno
JOIN weather_obs wr
     ON wr.station_id = mw.station_id
    AND wr.obs_time   = a.obs_slot
JOIN station_temp_map mt ON a.sno = mt.sno
JOIN weather_obs wt
     ON wt.station_id = mt.station_id
    AND wt.obs_time   = a.obs_slot
WHERE a.prev_time IS NOT NULL
  AND a.act = '1' AND a.prev_act = '1'
  AND a.info_time - a.prev_time BETWEEN interval '1 min' AND interval '15 min'