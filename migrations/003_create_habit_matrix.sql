CREATE TABLE IF NOT EXISTS habit_matrix (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(8) NOT NULL REFERENCES users(id),
    trigger_event TEXT NOT NULL,
    target_event TEXT NOT NULL,
    context TEXT NOT NULL,
    probability NUMERIC(6,5) NOT NULL,
    last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_habit_matrix_user_trigger_target_context
    ON habit_matrix (user_id, trigger_event, target_event, context);

CREATE INDEX IF NOT EXISTS ix_habit_matrix_user_trigger_context
    ON habit_matrix (user_id, trigger_event, context);
