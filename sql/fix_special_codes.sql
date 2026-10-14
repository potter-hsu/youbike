-- 一次性修正：2026-10-14 前以字串比對特殊碼，小數格式的代碼被當成觀測值存入
--
-- 2026-10-14 盤點：wind_direction = 990（風向不定）1,885 列、relative_humidity = -99 2 列
-- 其餘要素與降雨無此情形。分析未使用風向與濕度，故不影響既有結果。
--
-- 須在部署修正後的 load_weather.py 之後執行，否則最近 100 檔重跑時會再寫回。

BEGIN;

UPDATE weather_obs SET wind_direction    = NULL WHERE wind_direction    IN (990, -990, -99);
UPDATE weather_obs SET relative_humidity = NULL WHERE relative_humidity IN (-99);
UPDATE weather_obs SET air_temperature   = NULL WHERE air_temperature   IN (-99);
UPDATE weather_obs SET wind_speed        = NULL WHERE wind_speed        IN (-99);

COMMIT;
