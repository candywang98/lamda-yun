-- Add device control epoch and active companion binding (T007)
ALTER TABLE device ADD COLUMN IF NOT EXISTS control_epoch INTEGER NOT NULL DEFAULT 0;
ALTER TABLE device ADD COLUMN IF NOT EXISTS active_binding_id VARCHAR(36);
ALTER TABLE account_device_binding ADD COLUMN IF NOT EXISTS binding_version INTEGER NOT NULL DEFAULT 1;
