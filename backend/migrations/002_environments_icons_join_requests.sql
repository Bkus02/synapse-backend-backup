-- Ortam ikonu, kullanıcı avatar anahtarı, katılma istekleri tablosu.
-- pgAdmin Query Tool veya: psql -f migrations/002_environments_icons_join_requests.sql

ALTER TABLE environments ADD COLUMN IF NOT EXISTS icon_key TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_key TEXT;

CREATE TABLE IF NOT EXISTS environment_join_requests (
    id SERIAL PRIMARY KEY,
    environment_id VARCHAR(8) NOT NULL REFERENCES environments(id) ON DELETE CASCADE,
    user_id VARCHAR(8) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_env_join_user UNIQUE (environment_id, user_id)
);
