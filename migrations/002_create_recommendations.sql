DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'recommendation_status') THEN
        CREATE TYPE recommendation_status AS ENUM ('PENDING', 'ACCEPTED', 'REJECTED', 'EXPIRED');
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS recommendations (
    id VARCHAR(11) PRIMARY KEY,
    user_id VARCHAR(8) NOT NULL REFERENCES users(id),
    trigger_device TEXT NOT NULL,
    target_device TEXT NOT NULL,
    action TEXT NOT NULL,
    confidence NUMERIC(5,4) NOT NULL,
    status recommendation_status NOT NULL DEFAULT 'PENDING',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_recommendations_user_status_created
    ON recommendations (user_id, status, created_at DESC);
