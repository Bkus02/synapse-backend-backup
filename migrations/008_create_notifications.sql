-- =====================================================================
-- 008 — notifications + advice_schedules
-- =====================================================================
-- Persistent in-app notification feed used by the bell modal:
--
--   kind            'morning_greeting' | 'advice_reminder'
--                   | 'device_routine' | 'sequence_trigger'
--                   | 'streak_milestone'  (extensible TEXT)
--
--   status          'pending'   → scheduled, not yet fired
--                   'fired'     → visible in the feed
--                   'confirmed' → user tapped the action button
--                   'dismissed' → user dismissed
--                   'expired'   → end of day reached, no action
--
--   requires_action TRUE  → modal renders Confirm/Dismiss buttons
--                   FALSE → display-only (e.g., morning greeting)
--
--   payload JSONB carries kind-specific extras:
--     • advice_reminder  : { advice_key, advice_title, duration_minutes }
--     • device_routine   : { device_id, device_name, action, schedule_id }
--     • sequence_trigger : { source_log_id, trigger_device, target_device,
--                            action, confidence }
--     • streak_milestone : { current_streak, milestone }
-- =====================================================================

CREATE TABLE IF NOT EXISTS public.notifications (
    id               BIGSERIAL PRIMARY KEY,
    user_id          VARCHAR(8)  NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    kind             TEXT        NOT NULL,
    title            TEXT        NOT NULL,
    body             TEXT        NOT NULL,
    scheduled_for    TIMESTAMPTZ NOT NULL,
    fired_at         TIMESTAMPTZ,
    status           TEXT        NOT NULL DEFAULT 'pending',
    requires_action  BOOLEAN     NOT NULL DEFAULT FALSE,
    payload          JSONB       NOT NULL DEFAULT '{}'::jsonb,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_notifications_user_status
    ON public.notifications (user_id, status, scheduled_for DESC);
CREATE INDEX IF NOT EXISTS ix_notifications_scheduled
    ON public.notifications (scheduled_for)
    WHERE status = 'pending';


-- ---------------------------------------------------------------------
-- Advice schedules: the user picks a start time + duration from the main
-- page; we record the plan here AND insert a pending `advice_reminder`
-- notification that fires at `scheduled_for`. On confirm we log the
-- positive_advice completion and recompute the daily streak.
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.advice_schedules (
    id               BIGSERIAL PRIMARY KEY,
    user_id          VARCHAR(8)   NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    advice_key       TEXT         NOT NULL,
    advice_title     TEXT         NOT NULL,
    scheduled_for    TIMESTAMPTZ  NOT NULL,
    duration_minutes INTEGER      NOT NULL DEFAULT 0,
    status           TEXT         NOT NULL DEFAULT 'pending',
    notification_id  BIGINT       REFERENCES public.notifications(id) ON DELETE SET NULL,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_advice_schedules_user_time
    ON public.advice_schedules (user_id, scheduled_for DESC);
