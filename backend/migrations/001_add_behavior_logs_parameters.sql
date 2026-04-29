-- behavior_logs: rapor (Logical View) BehaviorLog.parameters alanı
-- pgAdmin Query Tool veya: psql -U postgres -d postgres -f migrations/001_add_behavior_logs_parameters.sql

ALTER TABLE IF EXISTS public.behavior_logs
    ADD COLUMN IF NOT EXISTS parameters text;

COMMENT ON COLUMN public.behavior_logs.parameters IS
    'Ek bağlam metni (örn. Parlaklık: %70, mod: Cinema). Rapor BehaviorLog.parameters.';
