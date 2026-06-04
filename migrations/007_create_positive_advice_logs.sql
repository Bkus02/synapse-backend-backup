-- =====================================================================
-- 007 — positive_advice_logs + user_daily_streaks
-- =====================================================================
-- Pozitif tavsiye tamamlanma kayıtları ve günlük streak takibi.
-- "Streak": kullanıcı bir günde >=2 farklı advice tamamladıysa o gün
-- "qualifying" sayılır. Ardışık qualifying günler current_streak'i artırır.
-- =====================================================================

CREATE TABLE IF NOT EXISTS public.positive_advice_logs (
    id              SERIAL PRIMARY KEY,
    user_id         VARCHAR(8)   NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    advice_key      TEXT         NOT NULL,
    advice_title    TEXT         NOT NULL,
    category        advice_category NOT NULL DEFAULT 'Other',
    completed_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    duration_minutes INTEGER     NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS ix_pal_user_time
    ON public.positive_advice_logs (user_id, completed_at DESC);
CREATE INDEX IF NOT EXISTS ix_pal_user_key_time
    ON public.positive_advice_logs (user_id, advice_key, completed_at DESC);


CREATE TABLE IF NOT EXISTS public.user_daily_streaks (
    user_id              VARCHAR(8) PRIMARY KEY REFERENCES public.users(id) ON DELETE CASCADE,
    current_streak       INTEGER    NOT NULL DEFAULT 0,
    max_streak           INTEGER    NOT NULL DEFAULT 0,
    last_qualifying_date DATE,
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
