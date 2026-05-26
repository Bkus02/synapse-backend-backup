-- =====================================================================
-- Synapse — initial schema (idempotent)
-- =====================================================================
-- Bu dosya, mevcut 001..006 incremental migration'larından ÖNCE
-- çalıştırılmalıdır. Boş bir PostgreSQL veritabanında uygulamayı
-- ayağa kaldırmak için gereken tüm ENUM, tablo, indeks ve CHECK
-- kısıtlarını üretir. Tüm ifadeler IF NOT EXISTS / DO $$ blokları
-- ile sarmalanmıştır; tekrar çalıştırılması güvenlidir.
--
-- Çalıştırma:
--     psql -h localhost -U postgres -d postgres -f migrations/000_init_schema.sql
-- veya:
--     python -m app.ops apply-migrations
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1) ENUM tipleri
-- ---------------------------------------------------------------------

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'device_type') THEN
        CREATE TYPE device_type AS ENUM ('Lamp', 'Thermostat', 'Plug', 'Sensor', 'Other');
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'habit_recurrence') THEN
        CREATE TYPE habit_recurrence AS ENUM ('Daily', 'Weekly', 'Monthly');
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'advice_category') THEN
        CREATE TYPE advice_category AS ENUM (
            'Reading', 'Water', 'Exercise', 'Sleep', 'Mindfulness', 'Other'
        );
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'recommendation_status') THEN
        CREATE TYPE recommendation_status AS ENUM (
            'PENDING', 'ACCEPTED', 'REJECTED', 'EXPIRED'
        );
    END IF;
END $$;

-- ---------------------------------------------------------------------
-- 2) Çekirdek tablolar
-- ---------------------------------------------------------------------

-- 2.1 users
CREATE TABLE IF NOT EXISTS public.users (
    id              VARCHAR(8)  PRIMARY KEY,
    full_name       TEXT,
    email           TEXT UNIQUE,
    password_hash   TEXT,
    height          INTEGER,
    weight          INTEGER,
    age             INTEGER,
    location        TEXT,
    avatar_key      TEXT
);

-- User.id formatı: 'P' + 7 alfanumerik (rapor 4.1.2)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'users_id_format_check'
    ) THEN
        ALTER TABLE public.users
            ADD CONSTRAINT users_id_format_check
            CHECK (id ~ '^P[A-Z0-9]{7}$');
    END IF;
END $$;

-- 2.2 environments
CREATE TABLE IF NOT EXISTS public.environments (
    id          VARCHAR(8)  PRIMARY KEY,
    name        TEXT,
    admin_id    VARCHAR(8)  REFERENCES public.users(id) ON DELETE SET NULL,
    location    TEXT,
    icon_key    TEXT
);

-- Environment.id formatı: 'H' + 7 alfanumerik
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'environments_id_format_check'
    ) THEN
        ALTER TABLE public.environments
            ADD CONSTRAINT environments_id_format_check
            CHECK (id ~ '^H[A-Z0-9]{7}$');
    END IF;
END $$;

-- 2.3 devices
CREATE TABLE IF NOT EXISTS public.devices (
    id              SERIAL PRIMARY KEY,
    environment_id  VARCHAR(8)   NOT NULL REFERENCES public.environments(id) ON DELETE CASCADE,
    type            device_type  NOT NULL,
    status          BOOLEAN      NOT NULL DEFAULT FALSE,
    current_value   NUMERIC,
    name            TEXT,
    room            TEXT
);

CREATE INDEX IF NOT EXISTS ix_devices_environment
    ON public.devices (environment_id);

-- 2.4 behavior_logs
CREATE TABLE IF NOT EXISTS public.behavior_logs (
    id          SERIAL PRIMARY KEY,
    user_id     VARCHAR(8)  NOT NULL REFERENCES public.users(id)   ON DELETE CASCADE,
    device_id   INTEGER     NOT NULL REFERENCES public.devices(id) ON DELETE CASCADE,
    action      TEXT        NOT NULL,
    event_time  TIMESTAMPTZ NOT NULL,
    duration_hm INTERVAL,
    parameters  TEXT
);

CREATE INDEX IF NOT EXISTS ix_behavior_logs_user_time
    ON public.behavior_logs (user_id, event_time DESC);
CREATE INDEX IF NOT EXISTS ix_behavior_logs_user_device_time
    ON public.behavior_logs (user_id, device_id, event_time DESC);

-- 2.5 habits
CREATE TABLE IF NOT EXISTS public.habits (
    id                 SERIAL PRIMARY KEY,
    user_id            VARCHAR(8)        NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    name               TEXT              NOT NULL,
    probability_score  NUMERIC(4, 2)     NOT NULL,
    is_active          BOOLEAN           NOT NULL DEFAULT FALSE,
    recurrence_type    habit_recurrence  NOT NULL,
    device_id          INTEGER REFERENCES public.devices(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS ix_habits_user
    ON public.habits (user_id);

-- 2.6 positive_advices
CREATE TABLE IF NOT EXISTS public.positive_advices (
    id           SERIAL PRIMARY KEY,
    title        TEXT NOT NULL,
    description  TEXT,
    category     advice_category NOT NULL DEFAULT 'Other'
);

-- 2.7 user_environments (M-N)
CREATE TABLE IF NOT EXISTS public.user_environments (
    user_id         VARCHAR(8) NOT NULL REFERENCES public.users(id)        ON DELETE CASCADE,
    environment_id  VARCHAR(8) NOT NULL REFERENCES public.environments(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, environment_id)
);

CREATE INDEX IF NOT EXISTS ix_user_environments_env
    ON public.user_environments (environment_id);

-- 2.8 user_streaks
CREATE TABLE IF NOT EXISTS public.user_streaks (
    id                 SERIAL PRIMARY KEY,
    user_id            VARCHAR(8) NOT NULL REFERENCES public.users(id)              ON DELETE CASCADE,
    advice_id          INTEGER    NOT NULL REFERENCES public.positive_advices(id)   ON DELETE CASCADE,
    current_streak     INTEGER    NOT NULL DEFAULT 0,
    max_streak         INTEGER    NOT NULL DEFAULT 0,
    last_completed_on  DATE
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_user_streaks_user_advice
    ON public.user_streaks (user_id, advice_id);

-- ---------------------------------------------------------------------
-- 3) Sonraki migration'larla uyumlu yan tablolar
-- ---------------------------------------------------------------------
-- 001_add_behavior_logs_parameters.sql, 002_create_recommendations.sql,
-- 003_create_habit_matrix.sql, 004_add_recommendation_type_context.sql,
-- 005_environment_membership_ui_fields.sql, 006_add_devices_room.sql
-- bu dosyadan SONRA çalıştırılır. Idempotent oldukları için tekrar
-- çalıştırılmaları güvenlidir.
