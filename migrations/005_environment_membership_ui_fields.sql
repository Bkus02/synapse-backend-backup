-- Environment icon, user avatar, and environment join request support.

ALTER TABLE public.environments
    ADD COLUMN IF NOT EXISTS icon_key TEXT;

ALTER TABLE public.users
    ADD COLUMN IF NOT EXISTS avatar_key TEXT;

CREATE TABLE IF NOT EXISTS public.environment_join_requests (
    id SERIAL PRIMARY KEY,
    environment_id VARCHAR(8) NOT NULL REFERENCES public.environments(id) ON DELETE CASCADE,
    user_id VARCHAR(8) NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_env_join_user UNIQUE (environment_id, user_id)
);
