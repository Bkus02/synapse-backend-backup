-- Optional room / zone label for devices.

ALTER TABLE public.devices
    ADD COLUMN IF NOT EXISTS room TEXT;
