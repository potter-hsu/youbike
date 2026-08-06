-- YouBike × 天氣 資料管線
-- Schema 設計理由見 docs/schema_design.md

-- ============================================
-- 1. stations：站點慢變屬性
-- ============================================
CREATE TABLE stations (
    sno           text PRIMARY KEY,
    name_zh       text NOT NULL,
    name_en       text,
    area_zh       text NOT NULL,
    area_en       text,
    address_zh    text,
    address_en    text,
    latitude      double precision NOT NULL,
    longitude     double precision NOT NULL,
    quantity      integer NOT NULL,
    first_seen_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at  timestamptz NOT NULL DEFAULT now()
);

-- ============================================
-- 2. snapshots：時序觀測值
-- ============================================
CREATE TABLE snapshots (
    sno                    text        NOT NULL REFERENCES stations(sno),
    info_time              timestamptz NOT NULL,
    available_rent_bikes   integer     NOT NULL,
    available_return_bikes integer     NOT NULL,
    act                    text        NOT NULL,
    first_fetched_at       timestamptz NOT NULL DEFAULT now(),
    last_fetched_at        timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (sno, info_time)
);

-- 查詢 B：某時刻的全市橫斷面
-- 主鍵 (sno, info_time) 以 sno 為第一排序鍵，單獨給 info_time 條件時用不到
CREATE INDEX idx_snapshots_info_time ON snapshots (info_time);

-- ============================================
-- 3. fetch_log：系統行為紀錄
-- ============================================
CREATE TABLE fetch_log (
    fetch_id          bigserial PRIMARY KEY,
    started_at        timestamptz NOT NULL DEFAULT now(),
    duration_ms       integer,
    status_code       integer,
    etag              text,
    update_time       timestamptz,
    stations_received integer,
    rows_inserted     integer,
    rows_updated      integer,
    error_message     text
);