"""YouBike × 天氣 儀表板

執行方式（需先開 SSH tunnel 連到 EC2 的資料庫）：
    ssh -i <金鑰> -L 5433:localhost:5432 -N ubuntu@<EC2 位址>
    streamlit run src/dashboard.py

本機的 .env 需有 EC2_DB_PASSWORD。
"""

import os
from datetime import datetime, timedelta
from pathlib import Path
import numpy as np
import pandas as pd
import psycopg
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="YouBike × 天氣", layout="wide")

BASE = Path(__file__).parent.parent


# ── 連線 ────────────────────────────────────────────────

@st.cache_resource
def get_conn():
    """cache_resource：整個 session 共用一個連線，不重複建立。"""
    return psycopg.connect(
        f"host={os.getenv('DASH_DB_HOST', 'localhost')} "
        f"port={os.getenv('DASH_DB_PORT', '5433')} "
        f"dbname=youbike user=postgres "
        f"password={os.getenv('EC2_DB_PASSWORD')}"
    )


@st.cache_data(ttl=300)
def run_query(sql, params=None):
    """cache_data：相同查詢 5 分鐘內直接用快取，避免每次互動都打資料庫。
    ttl 設 300 秒是配合 cron 的抓取週期——更頻繁也沒有新資料。"""
    return pd.read_sql(sql, get_conn(), params=params)


# ── 查詢 ────────────────────────────────────────────────

LATEST_SQL = """
-- DISTINCT ON 取每站最新一筆。
-- 先用 info_time 限制範圍，否則要掃全表（數百萬列）。
SELECT DISTINCT ON (s.sno)
    s.sno,
    st.name_zh,
    st.area_zh,
    st.latitude,
    st.longitude,
    s.available_rent_bikes  AS rent,
    s.available_return_bikes AS ret,
    s.available_rent_bikes + s.available_return_bikes AS capacity,
    s.info_time,
    s.act
FROM snapshots s
JOIN stations st USING (sno)
WHERE s.info_time > now() - interval '2 hours'
ORDER BY s.sno, s.info_time DESC
"""

STATION_LIST_SQL = """
SELECT sno, name_zh, area_zh
FROM stations
ORDER BY area_zh, name_zh
"""

HISTORY_SQL = """
SELECT
    s.info_time,
    s.available_rent_bikes AS rent,
    s.available_return_bikes AS ret,
    w.precipitation_10min AS rain
FROM snapshots s
JOIN station_weather_map m ON s.sno = m.sno
LEFT JOIN weather_obs w
       ON w.station_id = m.station_id
      AND w.obs_time = date_trunc('hour', s.info_time)
                     + interval '10 min'
                       * floor(extract(minute from s.info_time) / 10)
WHERE s.sno = %(sno)s
  AND s.info_time >= %(start)s
ORDER BY s.info_time
"""

HEALTH_SQL = """
SELECT
    date_trunc('hour', started_at) AS hour,
    count(*) FILTER (WHERE fetch_id IS NOT NULL) AS youbike_runs,
    count(*) FILTER (WHERE fetch_id IS NULL)     AS weather_runs,
    sum(files_skipped) AS skipped,
    max(duration_ms)   AS max_ms
FROM load_log
WHERE started_at > now() - interval '24 hours'
GROUP BY 1 ORDER BY 1
"""


# ── 版面 ────────────────────────────────────────────────

st.title("YouBike × 天氣")
st.caption(
    "臺北市 YouBike 2.0 全站（約 1,800 站）每 5 分鐘、氣象署 71 個測站每 10 分鐘，"
    "自 2026-08-17 起連續運行於 AWS EC2"
)

tab_now, tab_hist, tab_rain, tab_health = st.tabs(
    ["即時狀態", "歷史趨勢", "降雨效果", "系統健康"]
)


# ── 分頁 1：即時狀態 ────────────────────────────────────

with tab_now:
    latest = run_query(LATEST_SQL)

    if latest.empty:
        st.warning("過去兩小時沒有資料——管線可能中斷了。")
    else:
        as_of = latest["info_time"].max().tz_convert("Asia/Taipei")
        st.caption(f"資料時間：{as_of:%Y-%m-%d %H:%M}（臺北時間）")

        active = latest[latest["act"] == "1"]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("有回報的站點", f"{len(latest):,}")
        c2.metric("可借車輛總數", f"{int(active['rent'].sum()):,}")
        c3.metric("空車位總數", f"{int(active['ret'].sum()):,}")
        c4.metric("停用站點", f"{(latest['act'] == '0').sum()}")

        st.subheader("站點分布")
        st.caption("點的位置為站點座標；下方表格可依行政區篩選")
        st.map(active[["latitude", "longitude"]], size=20)

        st.subheader("站點明細")
        areas = ["全部"] + sorted(active["area_zh"].unique().tolist())
        pick = st.selectbox("行政區", areas, key="area_now")
        view = active if pick == "全部" else active[active["area_zh"] == pick]

        # 可借比例：分母用 rent + ret，不是 quantity——
        # quantity 含故障車柱與充電中的電輔車，會系統性偏大
        view = view.assign(
            可借比例=(view["rent"] / view["capacity"].replace(0, np.nan)).round(2)
        )
        st.dataframe(
            view[["name_zh", "area_zh", "rent", "ret", "capacity", "可借比例"]]
            .rename(columns={
                "name_zh": "站名", "area_zh": "行政區",
                "rent": "可借", "ret": "空位", "capacity": "可用車柱",
            })
            .sort_values("可借比例"),
            use_container_width=True, hide_index=True,
        )


# ── 分頁 2：歷史趨勢 ────────────────────────────────────

with tab_hist:
    stations = run_query(STATION_LIST_SQL)
    stations["label"] = stations["area_zh"] + " — " + stations["name_zh"]

    c1, c2 = st.columns([3, 1])
    label = c1.selectbox("站點", stations["label"], key="station_hist")
    days = c2.selectbox("期間", [1, 3, 7], index=0, key="days_hist")

    sno = stations.loc[stations["label"] == label, "sno"].iloc[0]
    start = datetime.now().astimezone() - timedelta(days=days)

    hist = run_query(HISTORY_SQL, {"sno": sno, "start": start})

    if hist.empty:
        st.info("這個站在選定期間內沒有資料。")
    else:
        hist = hist.set_index(
            hist["info_time"].dt.tz_convert("Asia/Taipei")
        )
        st.subheader("可借車輛數")
        st.line_chart(hist[["rent"]].rename(columns={"rent": "可借車輛"}))

        st.subheader("同期降雨（對應最近雨量站，10 分鐘累積）")
        if hist["rain"].notna().any():
            st.bar_chart(hist[["rain"]].rename(columns={"rain": "mm / 10min"}))
        else:
            st.caption("選定期間內該站對應的測站沒有降雨紀錄。")

        st.caption(
            f"觀測筆數 {len(hist):,}　|　"
            f"⚠️ 8/31 起資料源改為每次回應都更新 infoTime，"
            f"故此後的觀測密度與先前不可直接比較"
        )


# ── 分頁 3：降雨效果 ────────────────────────────────────

with tab_rain:
    st.subheader("降雨對站點活動量的效果")
    st.caption(
        "雙向固定效應（站點 × 10 分鐘時段），樣本期間 2026-09-01 – 10-13，652 萬筆。"
        "活動量 = 每 10 分鐘內可借車輛變動的絕對值總和。"
    )

    # 估計結果為離線分析所得（notebooks/rain_sep_oct.ipynb），
    # 此處為靜態展示——重算需數分鐘，不適合放在互動介面
    result = pd.DataFrame({
        "降雨（每 10 分鐘）": ["0.5–1 mm", "1–3 mm", "> 3 mm"],
        "係數": [-0.21, -0.30, -0.35],
        "相對無雨": ["−13%", "−19%", "−22%"],
        "p 值（日期 cluster）": ["< 0.001", "< 0.001", "< 0.001"],
    })
    st.dataframe(result, use_container_width=True, hide_index=True)

    st.image(str(BASE / "docs/images/event_study.png"),
             caption="降雨開始前後的活動量變化（414 個事件）")

    st.markdown("""
**小雨就有效果，降雨開始後 10–20 分鐘最強，約 −25%。**

8/20–8/28 的初版分析曾得到「門檻型、飄雨無影響」，但以時段 cluster 時不顯著；
改用平衡面板與活動量重估後，該結論未被複製。

**已知限制**

- 效果來自局部降雨；全市同時下雨的時段被時段固定效應吸收
- 安慰劑（兩小時後的雨）小幅未通過，可能是預期行為或量不到的毛毛雨
- 5 分鐘內同時有借有還時仍會抵消，估計值為下界
""")


# ── 分頁 4：系統健康 ────────────────────────────────────

with tab_health:
    st.subheader("過去 24 小時的管線執行狀況")
    st.caption(
        "正常為每小時 YouBike 12 次、天氣 6 次。"
        "**某小時缺行代表程式沒有執行**——那比錯誤欄位有值更嚴重。"
    )

    health = run_query(HEALTH_SQL)

    if health.empty:
        st.error("過去 24 小時沒有任何執行紀錄。")
    else:
        health["hour"] = health["hour"].dt.tz_convert("Asia/Taipei")

        # 頭尾兩筆會因查詢窗口切在小時中間而不滿，排除後再判斷
        mid = health.iloc[1:-1]
        ok = (mid["youbike_runs"] == 12).all() and (mid["weather_runs"] == 6).all()
        skipped = int(health["skipped"].fillna(0).sum())

        c1, c2, c3 = st.columns(3)
        c1.metric("執行完整性", "正常" if ok else "有缺口")
        c2.metric("跳過的檔案", skipped)
        c3.metric("最長耗時", f"{int(health['max_ms'].max()) / 1000:.1f} s")

        st.dataframe(
            health.assign(
                hour=health["hour"].dt.strftime("%m/%d %H:00"),
                max_ms=(health["max_ms"] / 1000).round(1),
            ).rename(columns={
                "hour": "時間", "youbike_runs": "YouBike",
                "weather_runs": "天氣", "skipped": "跳過",
                "max_ms": "最長耗時 (s)",
            }),
            use_container_width=True, hide_index=True,
        )

        st.caption(
            "耗時逼近排程週期（YouBike 300 s、天氣 600 s）時，"
            "須縮小 load 的處理範圍或改變自癒策略。"
        )