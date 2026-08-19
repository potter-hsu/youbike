CREATE TABLE weather_stations (
    station_id      text PRIMARY KEY,
    station_name    text NOT NULL,
    county_name     text NOT NULL,
    town_name       text NOT NULL,
    altitude        double precision NOT NULL,
    latitude        double precision NOT NULL,
    longitude       double precision NOT NULL,
    first_seen_at   timestamptz NOT NULL DEFAULT now(),
    last_seen_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE weather_obs (
    station_id             text        NOT NULL REFERENCES weather_stations(station_id),
    obs_time               timestamptz NOT NULL,
    precipitation_10min    real,
    precip_10min_flag      text,
    precipitation_1hr      real,
    precip_1hr_flag        text,
    weather                text,
    visibility             text,
    sunshine_duration      real,
    wind_direction         real,
    wind_speed             real,
    air_temperature        real,
    relative_humidity      real,
    uv_index               real,
    first_fetched_at       timestamptz NOT NULL,
    last_fetched_at        timestamptz NOT NULL,
    loaded_at              timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (station_id, obs_time)
);