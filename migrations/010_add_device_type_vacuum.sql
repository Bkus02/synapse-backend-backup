-- =====================================================================
-- 010 — device_type ENUM'una 'Vacuum' (robot supurge) ekle
-- =====================================================================
-- Robot supurge cihazlari icin yeni tip. Kullanim saati onerisi
-- demografik peer-matching ile uretilir (device_recommendation_service).

ALTER TYPE device_type ADD VALUE IF NOT EXISTS 'Vacuum';
