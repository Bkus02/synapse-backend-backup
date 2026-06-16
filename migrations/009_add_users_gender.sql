-- Cinsiyet (Erkek/Kadin) — cold-start ve oneri kohortu icin.

ALTER TABLE public.users
    ADD COLUMN IF NOT EXISTS gender TEXT;
