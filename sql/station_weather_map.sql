-- YouBike 站點 → 最近氣象測站 對應表
--
-- 設計依據見 docs/schema_design.md 決策 11：
--   臺北市 71 個雨量站中約 16 站海拔 > 300m（陽明山系、貓空），
--   而 YouBike 站點幾乎全在平地市區。
--   若以純水平距離配對，部分站會被配到海拔相差數百公尺的測站
--   （2026-08-19 實測：鞍部 838m 當日雨量 14.0mm，臺北站 6m 僅 1.0mm，差 14 倍）。
--   故先篩選 altitude < 150m，再做最近距離配對。
--
-- ⚠️ 本表可重複執行（含 DROP）。
--    這是刻意的例外——本表為「計算結果」而非原始觀測資料，
--    重算成本為零，且應在測站或 YouBike 站點清單變動後定期重跑。
--    snapshots / weather_obs 等原始資料表絕不可如此處理。

DROP TABLE IF EXISTS station_weather_map;

CREATE TABLE station_weather_map AS
WITH usable AS (
    -- 決策 11：僅保留低海拔測站
    SELECT station_id, latitude, longitude
    FROM weather_stations
    WHERE county_name = '臺北市'
      AND altitude < 150
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
    CROSS JOIN usable u          -- 1795 × 50 = 89,750 組配對
)
SELECT sno, station_id, round(distance_m::numeric, 1) AS distance_m
FROM pairs
WHERE rn = 1;

ALTER TABLE station_weather_map ADD PRIMARY KEY (sno);

-- 2026-08-25 執行結果：
--   1795 站全數配對成功
--   距離 min 17.3m / avg 873m / max 2139m
--   最大負載測站 C0AH70 服務 134 站
--
-- ⚠️ 建模注意：同一測站底下的 YouBike 站共用相同天氣值，
--    誤差項不獨立 → 標準誤需以 station_id 為層級做 cluster。
--    處理變數的有效變異來自 50 個測站，而非 1795 個站點。