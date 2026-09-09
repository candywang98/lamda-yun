CREATE TABLE IF NOT EXISTS task_schedule (
    id VARCHAR(36) PRIMARY KEY,
    tenant_id VARCHAR(36) NOT NULL,
    timezone VARCHAR(80) NOT NULL,
    kind VARCHAR(16) NOT NULL,
    once_at TIMESTAMP WITH TIME ZONE,
    rrule VARCHAR(255),
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    template_revision INTEGER NOT NULL DEFAULT 1,
    miss_policy VARCHAR(32) NOT NULL DEFAULT 'QUEUE_ONE',
    start_deadline_minutes INTEGER NOT NULL DEFAULT 30,
    account_id VARCHAR(36) NOT NULL,
    binding_version INTEGER NOT NULL,
    device_ids JSON NOT NULL,
    command_type VARCHAR(80) NOT NULL,
    parameters JSON NOT NULL DEFAULT '{}',
    created_by VARCHAR(36) NOT NULL,
    paused_reason VARCHAR(160),
    last_error TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_task_schedule_tenant_id ON task_schedule (tenant_id);
CREATE INDEX IF NOT EXISTS ix_task_schedule_account_id ON task_schedule (account_id);

CREATE TABLE IF NOT EXISTS task_schedule_fire (
    id VARCHAR(36) PRIMARY KEY,
    tenant_id VARCHAR(36) NOT NULL,
    schedule_id VARCHAR(36) NOT NULL REFERENCES task_schedule(id),
    device_id VARCHAR(36) NOT NULL,
    scheduled_for TIMESTAMP WITH TIME ZONE NOT NULL,
    scheduled_for_local VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL,
    task_id VARCHAR(36),
    detail TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT uq_task_schedule_fire UNIQUE (schedule_id, scheduled_for, device_id)
);
CREATE INDEX IF NOT EXISTS ix_task_schedule_fire_tenant_id ON task_schedule_fire (tenant_id);
CREATE INDEX IF NOT EXISTS ix_task_schedule_fire_schedule_id ON task_schedule_fire (schedule_id);
