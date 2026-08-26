-- YouBike 站點 → 最近「有溫度觀測」的測站 對應表
--
-- 為何與 station_weather_map 分開（決策 13）：
--   降雨與溫度的空間尺度不同。
--   降雨為對流性，變異大，需要 71 個雨量站的密度；
--   溫度在都會平地間差異小（主要受海拔影響，而這些站海拔相近）。
--
--   若兩者共用同一張對應表，多數 YouBike 站會被配到「只有雨量筒」的測站
--   （71 站中僅 9 站具完整氣象儀器），導致溫度大量缺失。
--   2026-08-26 實測：1000 筆樣本的 air_temperature 缺失率 100%。
--
-- 2026-08-26 執行時，符合條件的測站為 6 個：
--   466920 臺北 6.3m   / C2AA10 中八仙 16m  / A0A010 臺灣大學 17m
--   CAAH60 大安森林 18m / CAA090 國三甲005K 60m / CAA040 國三S016K 71m
--   分布涵蓋中正、北投、大安、文山、南港，東西南北皆有覆蓋。
--
-- ⚠️ 本表可重複執行（含 DROP），理由同 station_weather_map。
--    但候選集合來自動態子查詢，若日後有測站開始／停止回報溫度，
--    重跑結果可能不同。上列 6 站為當時的基準。
DROP TABLE IF EXISTS station_temp_map;

CREATE TABLE station_temp_map AS
WITH usable AS (
    SELECT station_id, latitude, longitude
    FROM weather_stations
    WHERE county_name = '臺北市'
      AND altitude < 150
      AND station_id IN (
          SELECT DISTINCT station_id FROM weather_obs
          WHERE air_temperature IS NOT NULL
      )
),
pairs AS (
    SELECT
        s.sno,
        u.station_id,
        -- Haversine 距離（公尺），6371000 為地球平均半徑
        6371000 * 2 * asin(sqrt(
            power(sin(radians(u.latitude - s.latitude) / 2), 2)
            + cos(radians(s.latitude)) * cos(radians(u.latitude))
            * power(sin(radians(u.longitude - s.longitude) / 2), 2)
        )) AS distance_m,
        -- 公式需重寫一次：ORDER BY 無法引用同層 SELECT 的別名
        row_number() OVER (
            PARTITION BY s.sno
            ORDER BY 6371000 * 2 * asin(sqrt(
                power(sin(radians(u.latitude - s.latitude) / 2), 2)
                + cos(radians(s.latitude)) * cos(radians(u.latitude))
                * power(sin(radians(u.longitude - s.longitude) / 2), 2)
            ))
        ) AS rn
    FROM stations s
    CROSS JOIN usable u
)
SELECT sno, station_id, round(distance_m::numeric, 1) AS distance_m
FROM pairs
WHERE rn = 1;

ALTER TABLE station_temp_map ADD PRIMARY KEY (sno);