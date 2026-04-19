-- Optional room / zone label for devices (UI grouping).
ALTER TABLE devices ADD COLUMN IF NOT EXISTS room TEXT;
