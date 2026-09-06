"""Application service for safe, catalog-backed asynchronous operations."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from cloudctl_domain import (
    Actor,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    Permission,
    Role,
    ValidationError,
    canonical_hash,
    require_permissions,
)
from cloudctl_domain.rbac import effective_permissions
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.exc import IntegrityError

from .db import (
    Database,
    OperationFeatureConfigDraftRow,
    OperationItemRow,
    OperationTaskRow,
)
from .operation_catalog import (
    BLOCKED_FEATURE_IDS,
    BY_KEY,
    DEFINITIONS,
    FEATURE_BY_ID,
    FEATURE_DEFINITIONS,
    FEATURE_IDS_BY_OPERATION,
    FEATURE_OPERATION_MAP,
    FeatureDefinition,
    OperationDefinition,
)
from .operation_parameters import (
    operation_parameter_schema,
    parameter_validation_detail,
    validate_operation_parameters,
)
from .operation_repository import OperationRepository
from .operation_runtime import OperationExecutorRegistry
from .operation_schemas import (
    OperationFeatureConfigDraftPut,
    OperationItemResultUpdate,
    validate_feature_configuration,
)
from .repository import ControlRepository
from .settings import Settings

TERMINAL_TASK_STATES = frozenset({"SUCCEEDED", "PARTIAL", "FAILED", "CANCELED", "REJECTED"})
TERMINAL_ITEM_STATES = frozenset({"SUCCEEDED", "FAILED", "BLOCKED", "CANCELED"})
UNSAFE_PARAMETER_FRAGMENTS = frozenset(
    {
        "adb",
        "captcha",
        "command",
        "credential",
        "frida",
        "mitm",
        "password",
        "pem",
        "privatekey",
        "proxy",
        "script",
        "secret",
        "shell",
        "token",
    }
)
UNSAFE_PARAMETER_VALUES = frozenset(
    {
        "adb.remote",
        "captcha.bypass",
        "frida",
        "mitm",
        "proxy.mutate",
        "shell.arbitrary",
    }
)
ALLOWED_CONTEXT_FIELDS = frozenset(
    {
        "deviceScope",
        "executionApp",
        "schedule",
        "snapshot",
        "reason",
        "source",
        "mode",
        "sourcePage",
        "sourceRoute",
        "pageParameters",
    }
)
PAGE_PARAMETERS_FIELD = "pageParameters"


def _now() -> datetime:
    return datetime.now(UTC)


class OperationService:
    def __init__(
        self,
        database: Database,
        settings: Settings,
        mobile_task_service: Any | None = None,
    ) -> None:
        self.database = database
        self.executors = OperationExecutorRegistry(settings)
        self.mobile_task_service = mobile_task_service

    def catalog(self, actor: Actor) -> list[dict[str, Any]]:
        permissions = effective_permissions(actor.roles)
        result: list[dict[str, Any]] = []
        for definition in DEFINITIONS:
            authorized = definition.permission in permissions
            executor_available = self.executors.available(definition.key)
            result.append(
                {
                    "key": definition.key,
                    "module": definition.module,
                    "resourceType": definition.resource_type,
                    "batchAllowed": definition.batch_allowed,
                    "requiredPermission": definition.permission.value,
                    "authorized": authorized,
                    "allowed": authorized and executor_available,
                    "executorAvailable": executor_available,
                    "executionState": self.executors.execution_state(definition.key),
                    "allowedParameters": sorted(
                        definition.allowed_parameters | {PAGE_PARAMETERS_FIELD}
                    ),
                    "parameterSchema": operation_parameter_schema(definition.key),
                    "description": definition.description,
                    "risk": definition.risk,
                    "featureIds": list(FEATURE_IDS_BY_OPERATION[definition.key]),
                }
            )
        return result

    def features(self, actor: Actor) -> list[dict[str, Any]]:
        self._require_authenticated_role(actor)
        permissions = effective_permissions(actor.roles)
        result: list[dict[str, Any]] = []
        for feature in FEATURE_DEFINITIONS:
            definition = BY_KEY.get(feature.operation_key) if feature.operation_key else None
            authorized = bool(definition and definition.permission in permissions)
            executor_available = bool(definition and self.executors.available(definition.key))
            execution_state = (
                self.executors.execution_state(definition.key)
                if definition is not None
                else feature.execution_state
            )
            result.append(
                {
                    "featureId": feature.id,
                    "index": feature.index,
                    "module": feature.module,
                    "moduleLabel": feature.module_label,
                    "stage": feature.stage,
                    "title": feature.title,
                    "mode": feature.mode,
                    "operationKey": feature.operation_key,
                    "policy": feature.policy,
                    "executionState": execution_state,
                    "risk": feature.risk,
                    "authorized": authorized,
                    "allowed": authorized and executor_available,
                    "executable": authorized and executor_available,
                    "reason": (
                        "A deployed, policy-restricted executor is available for this operation."
                        if executor_available
                        else feature.reason
                    ),
                }
            )
        return result

    async def get_feature_config_draft(self, actor: Actor, feature_id: str) -> dict[str, Any]:
        self._require_authenticated_role(actor)
        self._feature(feature_id)
        async with self.database.unit_of_work() as session:
            row = await OperationRepository(session, actor).feature_config_draft(feature_id)
            return self._feature_config_draft_view(feature_id, row)

    async def put_feature_config_draft(
        self,
        actor: Actor,
        feature_id: str,
        request: OperationFeatureConfigDraftPut,
    ) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.AUTOMATION_MANAGE)
        feature = self._feature(feature_id)
        feature_execution_state = (
            self.executors.execution_state(feature.operation_key)
            if feature.operation_key is not None
            else feature.execution_state
        )
        try:
            configuration = validate_feature_configuration(request.configuration)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        configuration_sha256 = canonical_hash(configuration)
        now = _now()
        updated_by = str(actor.user_id)

        async with self.database.unit_of_work() as session:
            repository = OperationRepository(session, actor)
            control = ControlRepository(session, actor)
            existing = await repository.feature_config_draft(feature_id)
            if existing is None:
                if request.expected_version != 0:
                    raise ConflictError(
                        "feature config draft version does not match expectedVersion"
                    )
                row = OperationFeatureConfigDraftRow(
                    id=control.new_id(),
                    tenant_id=repository.tenant_id,
                    feature_id=feature_id,
                    configuration_json=configuration,
                    configuration_sha256=configuration_sha256,
                    version=1,
                    updated_by=updated_by,
                    updated_at=now,
                    created_at=now,
                )
                repository.add(row)
                try:
                    await session.flush()
                except IntegrityError as exc:
                    raise ConflictError(
                        "feature config draft version does not match expectedVersion"
                    ) from exc
                before = None
                action = "operation.feature_config_draft.created"
                result = self._feature_config_draft_view(feature_id, row)
            else:
                if request.expected_version != existing.version:
                    raise ConflictError(
                        "feature config draft version does not match expectedVersion"
                    )
                before = {
                    "configurationSha256": existing.configuration_sha256,
                    "version": existing.version,
                }
                updated = await repository.update_feature_config_draft(
                    existing.id,
                    expected_version=request.expected_version,
                    configuration=configuration,
                    configuration_sha256=configuration_sha256,
                    updated_by=updated_by,
                    updated_at=now,
                )
                if not updated:
                    raise ConflictError(
                        "feature config draft version does not match expectedVersion"
                    )
                action = "operation.feature_config_draft.updated"
                result = {
                    "featureId": feature_id,
                    "configuration": configuration,
                    "version": request.expected_version + 1,
                    "exists": True,
                    "createdAt": existing.created_at,
                    "updatedAt": now,
                    "updatedBy": updated_by,
                }

            control.audit(
                action=action,
                resource_type="operation_feature_config_draft",
                resource_id=feature_id,
                before=before,
                after={
                    "configurationSha256": configuration_sha256,
                    "version": result["version"],
                },
                metadata={
                    "featureId": feature_id,
                    "featurePolicy": feature.policy,
                    "featureExecutionState": feature_execution_state,
                },
            )
            return result

    async def create_task(
        self,
        actor: Actor,
        *,
        idempotency_key: str,
        operation_key: str,
        feature_id: str | None,
        resource_ids: list[str],
        parameters: dict[str, Any],
        context: dict[str, Any],
        is_batch: bool,
    ) -> tuple[dict[str, Any], bool]:
        self._validate_feature_mapping(feature_id, operation_key)
        definition = self._definition(actor, operation_key)
        if not self.executors.available(operation_key):
            raise ConflictError(f"operation {operation_key} has no deployed executor")
        if is_batch and not definition.batch_allowed:
            raise ConflictError(f"operation {operation_key} does not allow batch execution")
        if not idempotency_key or len(idempotency_key) > 128:
            raise ValidationError("a valid Idempotency-Key header is required")
        if not resource_ids:
            raise ValidationError("at least one resource ID is required")
        if len(resource_ids) > 500:
            raise ValidationError("operation batches are limited to 500 resources")
        if len(resource_ids) != len(set(resource_ids)):
            raise ValidationError("resource IDs must be unique")
        parameters = self._validate_parameters(definition, feature_id, parameters)
        self._validate_context(context)
        normalized = {
            "operationKey": operation_key,
            "featureId": feature_id,
            "resourceIds": resource_ids,
            "parameters": parameters,
            "context": context,
            "batch": is_batch,
        }
        request_sha256 = canonical_hash(normalized)

        async with self.database.unit_of_work() as session:
            repository = OperationRepository(session, actor)
            control = ControlRepository(session, actor)
            existing = await repository.task_by_idempotency(idempotency_key)
            if existing is not None:
                if existing.request_sha256 != request_sha256:
                    raise ConflictError("Idempotency-Key was already used for a different request")
                items = await repository.items(existing.id)
                return self._task_view(existing, items), False

            task = OperationTaskRow(
                id=control.new_id(),
                tenant_id=repository.tenant_id,
                operation_key=definition.key,
                feature_id=feature_id,
                module=definition.module,
                idempotency_key=idempotency_key,
                request_sha256=request_sha256,
                requested_by=str(actor.user_id),
                status="PENDING_APPROVAL" if definition.risk == "approval" else "QUEUED",
                parameters=parameters,
                context=context,
                total_count=len(resource_ids),
                succeeded_count=0,
                failed_count=0,
                blocked_count=0,
                canceled_count=0,
                cancel_requested=False,
                result_summary={},
                started_at=None,
                completed_at=None,
                approval_decision=None,
                approval_reason=None,
                approved_by=None,
                decided_at=None,
                created_at=_now(),
            )
            repository.add(task)
            items = [
                OperationItemRow(
                    id=control.new_id(),
                    tenant_id=repository.tenant_id,
                    task_id=task.id,
                    resource_id=resource_id,
                    status="QUEUED",
                    error_code=None,
                    detail=None,
                    evidence_refs=[],
                    updated_at=_now(),
                )
                for resource_id in resource_ids
            ]
            for item in items:
                repository.add(item)
            control.audit(
                action="operation.task.created",
                resource_type="operation_task",
                resource_id=task.id,
                after={
                    "operation_key": definition.key,
                    "feature_id": feature_id,
                    "risk": definition.risk,
                    "resource_count": len(resource_ids),
                    "request_sha256": request_sha256,
                },
            )
            control.emit(
                control.event(
                    "operation_task",
                    task.id,
                    "operation.task.created",
                    {
                        "taskId": task.id,
                        "operationKey": definition.key,
                        "featureId": feature_id,
                        "status": task.status,
                        "resourceCount": len(resource_ids),
                    },
                )
            )
            view = self._task_view(task, items)
        if definition.key == "xianyu.listing.publish" and self.mobile_task_service is not None:
            await self._dispatch_xianyu_listing(actor, idempotency_key, resource_ids, parameters)
        return view, True

    async def list_tasks(
        self,
        actor: Actor,
        *,
        module: str | None,
        status: str | None,
        after_id: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        self._require_authenticated_role(actor)
        if status and status not in {
            "QUEUED",
            "PENDING_APPROVAL",
            "RUNNING",
            "SUCCEEDED",
            "PARTIAL",
            "FAILED",
            "CANCELED",
            "REJECTED",
        }:
            raise ValidationError("unknown operation task status")
        permissions = effective_permissions(actor.roles)
        allowed_keys = [
            definition.key for definition in DEFINITIONS if definition.permission in permissions
        ]
        if not allowed_keys:
            return []
        async with self.database.unit_of_work() as session:
            repository = OperationRepository(session, actor)
            rows = await repository.tasks(
                module=module,
                status=status,
                after_id=after_id,
                allowed_operation_keys=allowed_keys,
                limit=limit,
            )
            return [self._task_view(row) for row in rows]

    async def get_task(self, actor: Actor, task_id: str) -> dict[str, Any]:
        self._require_authenticated_role(actor)
        async with self.database.unit_of_work() as session:
            repository = OperationRepository(session, actor)
            task = await repository.task(task_id)
            self._definition(actor, task.operation_key)
            return self._task_view(task, await repository.items(task.id))

    async def record_item_result(
        self,
        actor: Actor,
        task_id: str,
        resource_id: str,
        update: OperationItemResultUpdate,
    ) -> dict[str, Any]:
        if Role.SYSTEM_SERVICE not in actor.roles:
            raise ForbiddenError("only an authorized service may record operation results")
        async with self.database.unit_of_work() as session:
            repository = OperationRepository(session, actor)
            control = ControlRepository(session, actor)
            task = await repository.task(task_id, for_update=True)
            item = await repository.item(task.id, resource_id, for_update=True)
            if item.status in TERMINAL_ITEM_STATES:
                if self._same_result(item, update):
                    return self._task_view(task, await repository.items(task.id))
                raise ConflictError("operation item already has an immutable terminal result")
            if task.status == "PENDING_APPROVAL":
                raise ConflictError("operation task must be approved before execution")
            if task.status in TERMINAL_TASK_STATES:
                raise ConflictError(f"operation task is already {task.status}")
            if task.started_at is None:
                task.started_at = _now()
            task.status = "RUNNING"
            item.status = update.status
            item.error_code = update.error_code
            item.detail = update.detail
            item.evidence_refs = list(update.evidence_refs)
            item.updated_at = _now()
            items = await repository.items(task.id, for_update=True)
            self._recalculate(task, items)
            control.audit(
                action="operation.item.result_recorded",
                resource_type="operation_task",
                resource_id=task.id,
                after={
                    "resource_id": resource_id,
                    "status": update.status,
                    "error_code": update.error_code,
                    "evidence_count": len(update.evidence_refs),
                },
                result=update.status,
            )
            control.emit(
                control.event(
                    "operation_task",
                    task.id,
                    "operation.task.updated",
                    {"taskId": task.id, "status": task.status, "resourceId": resource_id},
                )
            )
            return self._task_view(task, items)

    async def cancel_task(self, actor: Actor, task_id: str, reason: str) -> dict[str, Any]:
        async with self.database.unit_of_work() as session:
            repository = OperationRepository(session, actor)
            control = ControlRepository(session, actor)
            task = await repository.task(task_id, for_update=True)
            if task.requested_by != str(actor.user_id) and Role.SECURITY_ADMIN not in actor.roles:
                raise ForbiddenError("only the requester or SecurityAdmin may cancel this task")
            definition = self._definition(actor, task.operation_key)
            require_permissions(actor.roles, definition.permission)
            if task.status in TERMINAL_TASK_STATES:
                raise ConflictError(f"operation task is already {task.status}")
            items = await repository.items(task.id, for_update=True)
            task.cancel_requested = True
            for item in items:
                if item.status in {"QUEUED", "RUNNING"}:
                    item.status = "CANCELED"
                    item.detail = "canceled before completion"
                    item.updated_at = _now()
            task.status = "CANCELED"
            task.completed_at = _now()
            self._recalculate(task, items, preserve_status=True)
            control.audit(
                action="operation.task.canceled",
                resource_type="operation_task",
                resource_id=task.id,
                after={"status": task.status, "cancel_requested": True},
                metadata={"reason": reason},
            )
            control.emit(
                control.event(
                    "operation_task",
                    task.id,
                    "operation.task.canceled",
                    {"taskId": task.id},
                )
            )
            return self._task_view(task, items)

    async def decide_task(
        self,
        actor: Actor,
        task_id: str,
        *,
        approved: bool,
        reason: str,
    ) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.OPERATION_APPROVE)
        if not actor.mfa:
            raise ForbiddenError("MFA is required for operation approval")
        async with self.database.unit_of_work() as session:
            repository = OperationRepository(session, actor)
            control = ControlRepository(session, actor)
            task = await repository.task(task_id, for_update=True)
            definition = BY_KEY.get(task.operation_key)
            if definition is None or definition.risk != "approval":
                raise ConflictError("operation task does not require approval")
            if task.status != "PENDING_APPROVAL":
                raise ConflictError(f"operation task is already {task.status}")
            if task.requested_by == str(actor.user_id):
                raise ForbiddenError("creator and approver must be different users")
            items = await repository.items(task.id, for_update=True)
            now = _now()
            task.approval_decision = "APPROVED" if approved else "REJECTED"
            task.approval_reason = reason
            task.approved_by = str(actor.user_id)
            task.decided_at = now
            if approved:
                task.status = "QUEUED"
            else:
                task.status = "REJECTED"
                task.completed_at = now
                for item in items:
                    item.status = "BLOCKED"
                    item.error_code = "APPROVAL_REJECTED"
                    item.detail = reason
                    item.updated_at = now
                self._recalculate(task, items, preserve_status=True)
            action = "operation.task.approved" if approved else "operation.task.rejected"
            control.audit(
                action=action,
                resource_type="operation_task",
                resource_id=task.id,
                after={"status": task.status, "decision": task.approval_decision},
                metadata={"reason": reason},
                result="APPROVED" if approved else "REJECTED",
            )
            control.emit(
                control.event(
                    "operation_task",
                    task.id,
                    action,
                    {"taskId": task.id, "status": task.status},
                )
            )
            return self._task_view(task, items)

    async def audit_result(self, actor: Actor, task_id: str) -> dict[str, Any]:
        self._require_authenticated_role(actor)
        async with self.database.unit_of_work() as session:
            repository = OperationRepository(session, actor)
            task = await repository.task(task_id)
            self._definition(actor, task.operation_key)
            items = await repository.items(task.id)
            events = await repository.audit_events(task.id)
            return {
                "task": self._task_view(task, items),
                "auditEvents": [
                    {
                        "id": event.id,
                        "actorType": event.actor_type,
                        "actorId": event.actor_id,
                        "action": event.action,
                        "resourceType": event.resource_type,
                        "resourceId": event.resource_id,
                        "requestId": event.request_id,
                        "workflowId": event.workflow_id,
                        "deviceId": event.device_id,
                        "edgeId": event.edge_id,
                        "result": event.result,
                        "beforeHash": event.before_hash,
                        "afterHash": event.after_hash,
                        "metadata": event.metadata_json,
                        "occurredAt": event.occurred_at,
                    }
                    for event in events
                ],
            }

    @staticmethod
    def _require_authenticated_role(actor: Actor) -> None:
        if not actor.roles:
            raise ForbiddenError("an assigned tenant role is required")

    @staticmethod
    def _feature(feature_id: str) -> FeatureDefinition:
        feature = FEATURE_BY_ID.get(feature_id)
        if feature is None:
            raise NotFoundError("operation feature was not found")
        return feature

    @staticmethod
    def _feature_config_draft_view(
        feature_id: str,
        row: OperationFeatureConfigDraftRow | None,
    ) -> dict[str, Any]:
        if row is None:
            return {
                "featureId": feature_id,
                "configuration": {},
                "version": 0,
                "exists": False,
                "createdAt": None,
                "updatedAt": None,
                "updatedBy": None,
            }
        return {
            "featureId": feature_id,
            "configuration": row.configuration_json,
            "version": row.version,
            "exists": True,
            "createdAt": row.created_at,
            "updatedAt": row.updated_at,
            "updatedBy": row.updated_by,
        }

    async def _dispatch_xianyu_listing(
        self,
        actor: Actor,
        idempotency_key: str,
        resource_ids: list[str],
        parameters: dict[str, Any],
    ) -> None:
        from .mobile_schemas import MobileTaskCreate
        from .xianyu_publish import build_text_publish_task, listing_copy_from_parameters

        assert self.mobile_task_service is not None
        try:
            description, price = listing_copy_from_parameters(parameters)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        for index, device_id in enumerate(resource_ids):
            body = MobileTaskCreate.model_validate(
                build_text_publish_task(device_id, description=description, price=price)
            )
            await self.mobile_task_service.create_task(
                actor,
                f"{idempotency_key}:mobile:{index}",
                body,
            )

    @staticmethod
    def _definition(actor: Actor, operation_key: str) -> OperationDefinition:
        definition = BY_KEY.get(operation_key)
        if definition is None:
            raise ValidationError("operation is not in the approved catalog")
        require_permissions(actor.roles, definition.permission)
        return definition

    @staticmethod
    def _validate_parameters(
        definition: OperationDefinition,
        feature_id: str | None,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        unknown = set(parameters) - (definition.allowed_parameters | {PAGE_PARAMETERS_FIELD})
        if unknown:
            raise ValidationError(
                f"unsupported parameters for {definition.key}: {', '.join(sorted(unknown))}"
            )
        try:
            encoded = json.dumps(parameters, allow_nan=False, separators=(",", ":"))
        except (TypeError, ValueError) as exc:
            raise ValidationError("operation parameters must be finite JSON values") from exc
        if len(encoded.encode()) > 16_384:
            raise ValidationError("operation parameters exceed 16 KiB")
        page_parameters = parameters.get(PAGE_PARAMETERS_FIELD)
        if page_parameters is not None:
            if not isinstance(page_parameters, dict):
                raise ValidationError("pageParameters must be an object")
            try:
                validate_feature_configuration(page_parameters)
            except ValueError as exc:
                raise ValidationError(str(exc)) from exc

        def inspect(value: Any, key: str = "") -> None:
            normalized_key = key.lower().replace("_", "").replace("-", "")
            if any(fragment in normalized_key for fragment in UNSAFE_PARAMETER_FRAGMENTS):
                raise ValidationError(f"unsafe operation parameter is prohibited: {key}")
            if isinstance(value, dict):
                for child_key, child_value in value.items():
                    inspect(child_value, str(child_key))
            elif isinstance(value, list):
                for child_value in value:
                    inspect(child_value, key)
            elif isinstance(value, str) and value.lower() in UNSAFE_PARAMETER_VALUES:
                raise ValidationError("unsafe operation capability is prohibited")

        inspect(parameters)
        try:
            return validate_operation_parameters(definition.key, feature_id, parameters)
        except PydanticValidationError as exc:
            raise ValidationError(parameter_validation_detail(exc)) from exc
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

    @staticmethod
    def _validate_context(context: dict[str, Any]) -> None:
        unknown = set(context) - ALLOWED_CONTEXT_FIELDS
        if unknown:
            raise ValidationError(f"unsupported operation context: {', '.join(sorted(unknown))}")
        encoded = json.dumps(context, allow_nan=False, separators=(",", ":"))
        if len(encoded.encode()) > 8192:
            raise ValidationError("operation context exceeds 8 KiB")
        OperationService._inspect_safe_json(context)

    @staticmethod
    def _validate_feature_mapping(feature_id: str | None, operation_key: str) -> None:
        if feature_id is None:
            return
        if feature_id in BLOCKED_FEATURE_IDS:
            raise ForbiddenError("feature is blocked by production policy")
        if feature_id not in FEATURE_OPERATION_MAP:
            raise ValidationError("unknown featureId")
        mapped = FEATURE_OPERATION_MAP[feature_id]
        if mapped is None:
            raise ForbiddenError("feature has no approved backend operation mapping")
        if mapped != operation_key:
            raise ValidationError("featureId does not map to operationKey")

    @staticmethod
    def _inspect_safe_json(value: Any, key: str = "") -> None:
        normalized_key = key.lower().replace("_", "").replace("-", "")
        if any(fragment in normalized_key for fragment in UNSAFE_PARAMETER_FRAGMENTS):
            raise ValidationError(f"unsafe operation field is prohibited: {key}")
        if isinstance(value, dict):
            for child_key, child_value in value.items():
                OperationService._inspect_safe_json(child_value, str(child_key))
        elif isinstance(value, list):
            for child_value in value:
                OperationService._inspect_safe_json(child_value, key)
        elif isinstance(value, str) and value.lower() in UNSAFE_PARAMETER_VALUES:
            raise ValidationError("unsafe operation capability is prohibited")

    @staticmethod
    def _same_result(item: OperationItemRow, update: OperationItemResultUpdate) -> bool:
        return (
            item.status == update.status
            and item.error_code == update.error_code
            and item.detail == update.detail
            and item.evidence_refs == update.evidence_refs
        )

    @staticmethod
    def _recalculate(
        task: OperationTaskRow,
        items: list[OperationItemRow],
        *,
        preserve_status: bool = False,
    ) -> None:
        counts = {state: 0 for state in TERMINAL_ITEM_STATES | {"QUEUED", "RUNNING"}}
        for item in items:
            counts[item.status] = counts.get(item.status, 0) + 1
        task.succeeded_count = counts["SUCCEEDED"]
        task.failed_count = counts["FAILED"]
        task.blocked_count = counts["BLOCKED"]
        task.canceled_count = counts["CANCELED"]
        task.result_summary = {
            "succeeded": task.succeeded_count,
            "failed": task.failed_count,
            "blocked": task.blocked_count,
            "canceled": task.canceled_count,
            "pending": counts["QUEUED"],
            "running": counts["RUNNING"],
        }
        if preserve_status:
            return
        if counts["QUEUED"] or counts["RUNNING"]:
            task.status = "RUNNING"
            return
        task.completed_at = _now()
        if task.succeeded_count == task.total_count:
            task.status = "SUCCEEDED"
        elif task.succeeded_count == 0:
            task.status = "FAILED"
        else:
            task.status = "PARTIAL"

    def _task_view(
        self, task: OperationTaskRow, items: list[OperationItemRow] | None = None
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": task.id,
            "tenantId": task.tenant_id,
            "operationKey": task.operation_key,
            "featureId": task.feature_id,
            "module": task.module,
            "requestSha256": task.request_sha256,
            "requestedBy": task.requested_by,
            "status": task.status,
            "parameters": task.parameters,
            "context": task.context,
            "risk": BY_KEY[task.operation_key].risk,
            "executionState": self.executors.execution_state(task.operation_key),
            "executorAvailable": self.executors.available(task.operation_key),
            "totalCount": task.total_count,
            "succeededCount": task.succeeded_count,
            "failedCount": task.failed_count,
            "blockedCount": task.blocked_count,
            "canceledCount": task.canceled_count,
            "cancelRequested": task.cancel_requested,
            "resultSummary": task.result_summary,
            "createdAt": task.created_at,
            "startedAt": task.started_at,
            "completedAt": task.completed_at,
            "approvalDecision": task.approval_decision,
            "approvalReason": task.approval_reason,
            "approvedBy": task.approved_by,
            "decidedAt": task.decided_at,
        }
        if items is not None:
            result["items"] = [
                {
                    "id": item.id,
                    "resourceId": item.resource_id,
                    "status": item.status,
                    "errorCode": item.error_code,
                    "detail": item.detail,
                    "evidenceRefs": item.evidence_refs,
                    "updatedAt": item.updated_at,
                }
                for item in items
            ]
        return result
