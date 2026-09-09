-- T010/T011: freeze account ownership on tasks and unique live platform binding
ALTER TABLE account_device_binding ADD COLUMN IF NOT EXISTS platform VARCHAR(160) NOT NULL DEFAULT '';

UPDATE account_device_binding b
SET platform = a.platform
FROM platform_account a
WHERE b.account_id = a.id
  AND (b.platform IS NULL OR b.platform = '');

CREATE UNIQUE INDEX IF NOT EXISTS uq_account_device_binding_device_platform_bound
    ON account_device_binding (device_id, platform)
    WHERE status = 'BOUND';

ALTER TABLE mobile_task ADD COLUMN IF NOT EXISTS account_id VARCHAR(36);
ALTER TABLE mobile_task ADD COLUMN IF NOT EXISTS binding_version INTEGER;
ALTER TABLE mobile_task ADD COLUMN IF NOT EXISTS device_id_at_execution VARCHAR(36);
CREATE INDEX IF NOT EXISTS ix_mobile_task_account_id ON mobile_task (account_id);

ALTER TABLE publish_target ADD COLUMN IF NOT EXISTS binding_version INTEGER;
ALTER TABLE publish_target ADD COLUMN IF NOT EXISTS device_id_at_execution VARCHAR(36);
