-- T016: DeviceLease ownerType AUTO/REMOTE shared with Companion claim
ALTER TABLE device_lease ADD COLUMN IF NOT EXISTS owner_type VARCHAR(16) NOT NULL DEFAULT 'AUTO';
