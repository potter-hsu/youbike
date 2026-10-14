-- 站點 × 10 分鐘的活動量（2026-08-31 之後的資料使用）
--
-- 8/31 起資料源每次回應都給當下的 infoTime，每站每 5 分鐘一列、每時段兩列。
-- 這使「沒有任何借還的時段」也有觀測——先前只有數值更新時才有列，
-- 降雨讓活動歸零的時刻不在樣本中（見 notebooks/causal_analysis.ipynb 第 4 節）。
--
-- 用法：一次查一天，避免 window function 一次掃整張表
--   pd.read_sql(sql, conn, params={'start': '2026-09-01 00:00+08', 'end': '2026-09-02 00:00+08'})
--
-- ── 欄位 ─────────────────────────────────────────────
--   activity   相鄰兩筆可借車輛差的絕對值總和：借與還不會互相抵消（相較於淨變化）
--              但 5 分鐘內同時有借有還仍會抵消 → 下界
--   net        淨變化，與 8/20–8/28 分析的 delta 同義
--   n_changed  數值有變動的筆數；整天為 0 為失聯判定的依據（見 schema_design 第三節）
--
-- ── 時段對齊 ─────────────────────────────────────────
--   slot = info_time 往下取整到 10 分鐘，涵蓋 [slot, slot + 10min)。
--   該時段的降雨為 obs_time = slot + 10min 的 Past10Min（同一區間），於分析端 join

WITH s AS (
    SELECT
        sno,
        info_time,
        act,
        available_rent_bikes
            - LAG(available_rent_bikes) OVER w AS d,
        LAG(act) OVER w AS prev_act,
        info_time - LAG(info_time) OVER w AS gap
    FROM snapshots
    -- 往前多取 10 分鐘，使當日第一筆也有前一筆可比
    WHERE info_time >= %(start)s::timestamptz - interval '10 min'
      AND info_time <  %(end)s::timestamptz
    WINDOW w AS (PARTITION BY sno ORDER BY info_time)
)
SELECT
    sno,
    date_bin('10 minutes', info_time, timestamptz '2026-01-01 00:00+08') AS slot,
    count(*)                               AS n,
    sum(abs(d))                            AS activity,
    sum(d)                                 AS net,
    count(*) FILTER (WHERE d <> 0)         AS n_changed
FROM s
WHERE info_time >= %(start)s::timestamptz
  AND d IS NOT NULL
  -- 決策 4：跨越 act 轉換的差值非騎乘行為
  AND act = '1' AND prev_act = '1'
  -- 跨越抓取缺口的差值會把多個時段的變化算進同一時段
  AND gap <= interval '7 min'
GROUP BY 1, 2
