-- T013/T014: PlatformTask business state and structured events on MobileTask
ALTER TABLE mobile_task ADD COLUMN IF NOT EXISTS command_type VARCHAR(80);
ALTER TABLE mobile_task ADD COLUMN IF NOT EXISTS command_payload JSON NOT NULL DEFAULT '{}';
ALTER TABLE mobile_task ADD COLUMN IF NOT EXISTS business_state VARCHAR(32) NOT NULL DEFAULT 'QUEUED';
ALTER TABLE mobile_task ADD COLUMN IF NOT EXISTS control_mode VARCHAR(16) NOT NULL DEFAULT 'AUTO';
ALTER TABLE mobile_task ADD COLUMN IF NOT EXISTS batch_id VARCHAR(36);
ALTER TABLE mobile_task ADD COLUMN IF NOT EXISTS scheduled_for TIMESTAMP WITH TIME ZONE;
ALTER TABLE mobile_task ADD COLUMN IF NOT EXISTS stall_reason VARCHAR(160);
ALTER TABLE mobile_task ADD COLUMN IF NOT EXISTS attempt_id VARCHAR(36);
CREATE INDEX IF NOT EXISTS ix_mobile_task_command_type ON mobile_task (command_type);
CREATE INDEX IF NOT EXISTS ix_mobile_task_business_state ON mobile_task (business_state);
CREATE INDEX IF NOT EXISTS ix_mobile_task_batch_id ON mobile_task (batch_id);

ALTER TABLE mobile_task_event ADD COLUMN IF NOT EXISTS step_id VARCHAR(128);
ALTER TABLE mobile_task_event ADD COLUMN IF NOT EXISTS attempt_id VARCHAR(36);
ALTER TABLE mobile_task_event ADD COLUMN IF NOT EXISTS received_at TIMESTAMP WITH TIME ZONE;
