-- =====================================================================
-- 011 — behavior_logs.device_id FK: ON DELETE CASCADE
-- =====================================================================
-- Eski kurulumlarda CASCADE olmayan constraint cihaz silmeyi engelliyordu.

ALTER TABLE public.behavior_logs
    DROP CONSTRAINT IF EXISTS behavior_logs_device_fk;

ALTER TABLE public.behavior_logs
    ADD CONSTRAINT behavior_logs_device_fk
    FOREIGN KEY (device_id) REFERENCES public.devices(id) ON DELETE CASCADE;
