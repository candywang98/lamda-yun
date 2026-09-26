import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf import struct_pb2 as _struct_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class EdgeToCloud(_message.Message):
    __slots__ = (
        "sequence",
        "hello",
        "heartbeat",
        "command_ack",
        "task_event",
        "evidence_ready",
        "confirmation_required",
        "operator_action",
        "artifact_delivery",
        "relay_frame",
    )
    SEQUENCE_FIELD_NUMBER: _ClassVar[int]
    HELLO_FIELD_NUMBER: _ClassVar[int]
    HEARTBEAT_FIELD_NUMBER: _ClassVar[int]
    COMMAND_ACK_FIELD_NUMBER: _ClassVar[int]
    TASK_EVENT_FIELD_NUMBER: _ClassVar[int]
    EVIDENCE_READY_FIELD_NUMBER: _ClassVar[int]
    CONFIRMATION_REQUIRED_FIELD_NUMBER: _ClassVar[int]
    OPERATOR_ACTION_FIELD_NUMBER: _ClassVar[int]
    ARTIFACT_DELIVERY_FIELD_NUMBER: _ClassVar[int]
    RELAY_FRAME_FIELD_NUMBER: _ClassVar[int]
    sequence: int
    hello: EdgeHello
    heartbeat: Heartbeat
    command_ack: CommandAck
    task_event: TaskEvent
    evidence_ready: EvidenceReady
    confirmation_required: ConfirmationRequired
    operator_action: OperatorAction
    artifact_delivery: ArtifactDeliveryEvent
    relay_frame: DebugRelayFrame
    def __init__(
        self,
        sequence: _Optional[int] = ...,
        hello: _Optional[_Union[EdgeHello, _Mapping[str, object]]] = ...,
        heartbeat: _Optional[_Union[Heartbeat, _Mapping[str, object]]] = ...,
        command_ack: _Optional[_Union[CommandAck, _Mapping[str, object]]] = ...,
        task_event: _Optional[_Union[TaskEvent, _Mapping[str, object]]] = ...,
        evidence_ready: _Optional[_Union[EvidenceReady, _Mapping[str, object]]] = ...,
        confirmation_required: _Optional[_Union[ConfirmationRequired, _Mapping[str, object]]] = ...,
        operator_action: _Optional[_Union[OperatorAction, _Mapping[str, object]]] = ...,
        artifact_delivery: _Optional[_Union[ArtifactDeliveryEvent, _Mapping[str, object]]] = ...,
        relay_frame: _Optional[_Union[DebugRelayFrame, _Mapping[str, object]]] = ...,
    ) -> None: ...

class CloudToEdge(_message.Message):
    __slots__ = (
        "sequence",
        "hello",
        "start",
        "cancel",
        "debug_grant",
        "revocations",
        "confirmation_resolution",
        "debug_revoke",
        "relay_frame",
    )
    SEQUENCE_FIELD_NUMBER: _ClassVar[int]
    HELLO_FIELD_NUMBER: _ClassVar[int]
    START_FIELD_NUMBER: _ClassVar[int]
    CANCEL_FIELD_NUMBER: _ClassVar[int]
    DEBUG_GRANT_FIELD_NUMBER: _ClassVar[int]
    REVOCATIONS_FIELD_NUMBER: _ClassVar[int]
    CONFIRMATION_RESOLUTION_FIELD_NUMBER: _ClassVar[int]
    DEBUG_REVOKE_FIELD_NUMBER: _ClassVar[int]
    RELAY_FRAME_FIELD_NUMBER: _ClassVar[int]
    sequence: int
    hello: CloudHello
    start: StartCommand
    cancel: CancelCommand
    debug_grant: DebugSessionGrant
    revocations: CertificateRevocationUpdate
    confirmation_resolution: ConfirmationResolution
    debug_revoke: DebugSessionRevoke
    relay_frame: DebugRelayFrame
    def __init__(
        self,
        sequence: _Optional[int] = ...,
        hello: _Optional[_Union[CloudHello, _Mapping[str, object]]] = ...,
        start: _Optional[_Union[StartCommand, _Mapping[str, object]]] = ...,
        cancel: _Optional[_Union[CancelCommand, _Mapping[str, object]]] = ...,
        debug_grant: _Optional[_Union[DebugSessionGrant, _Mapping[str, object]]] = ...,
        revocations: _Optional[_Union[CertificateRevocationUpdate, _Mapping[str, object]]] = ...,
        confirmation_resolution: _Optional[
            _Union[ConfirmationResolution, _Mapping[str, object]]
        ] = ...,
        debug_revoke: _Optional[_Union[DebugSessionRevoke, _Mapping[str, object]]] = ...,
        relay_frame: _Optional[_Union[DebugRelayFrame, _Mapping[str, object]]] = ...,
    ) -> None: ...

class EdgeHello(_message.Message):
    __slots__ = ("edge_id", "software_version", "last_cloud_sequence_acked")
    EDGE_ID_FIELD_NUMBER: _ClassVar[int]
    SOFTWARE_VERSION_FIELD_NUMBER: _ClassVar[int]
    LAST_CLOUD_SEQUENCE_ACKED_FIELD_NUMBER: _ClassVar[int]
    edge_id: str
    software_version: str
    last_cloud_sequence_acked: int
    def __init__(
        self,
        edge_id: _Optional[str] = ...,
        software_version: _Optional[str] = ...,
        last_cloud_sequence_acked: _Optional[int] = ...,
    ) -> None: ...

class CloudHello(_message.Message):
    __slots__ = ("last_edge_sequence_acked",)
    LAST_EDGE_SEQUENCE_ACKED_FIELD_NUMBER: _ClassVar[int]
    last_edge_sequence_acked: int
    def __init__(self, last_edge_sequence_acked: _Optional[int] = ...) -> None: ...

class Heartbeat(_message.Message):
    __slots__ = ("edge_id", "observed_at", "devices")
    EDGE_ID_FIELD_NUMBER: _ClassVar[int]
    OBSERVED_AT_FIELD_NUMBER: _ClassVar[int]
    DEVICES_FIELD_NUMBER: _ClassVar[int]
    edge_id: str
    observed_at: _timestamp_pb2.Timestamp
    devices: _containers.RepeatedCompositeFieldContainer[DeviceHealth]
    def __init__(
        self,
        edge_id: _Optional[str] = ...,
        observed_at: _Optional[
            _Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping[str, object]]
        ] = ...,
        devices: _Optional[_Iterable[_Union[DeviceHealth, _Mapping[str, object]]]] = ...,
    ) -> None: ...

class DeviceHealth(_message.Message):
    __slots__ = (
        "device_id",
        "state",
        "android_version",
        "lamda_version",
        "app_versions",
        "capabilities",
        "battery_percent",
        "charging",
        "network_type",
        "temperature_celsius",
        "free_storage_bytes",
        "companion_version",
        "current_task_run_id",
        "current_task_state",
        "automation_stopped",
    )
    class AppVersionsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...

    DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    STATE_FIELD_NUMBER: _ClassVar[int]
    ANDROID_VERSION_FIELD_NUMBER: _ClassVar[int]
    LAMDA_VERSION_FIELD_NUMBER: _ClassVar[int]
    APP_VERSIONS_FIELD_NUMBER: _ClassVar[int]
    CAPABILITIES_FIELD_NUMBER: _ClassVar[int]
    BATTERY_PERCENT_FIELD_NUMBER: _ClassVar[int]
    CHARGING_FIELD_NUMBER: _ClassVar[int]
    NETWORK_TYPE_FIELD_NUMBER: _ClassVar[int]
    TEMPERATURE_CELSIUS_FIELD_NUMBER: _ClassVar[int]
    FREE_STORAGE_BYTES_FIELD_NUMBER: _ClassVar[int]
    COMPANION_VERSION_FIELD_NUMBER: _ClassVar[int]
    CURRENT_TASK_RUN_ID_FIELD_NUMBER: _ClassVar[int]
    CURRENT_TASK_STATE_FIELD_NUMBER: _ClassVar[int]
    AUTOMATION_STOPPED_FIELD_NUMBER: _ClassVar[int]
    device_id: str
    state: str
    android_version: str
    lamda_version: str
    app_versions: _containers.ScalarMap[str, str]
    capabilities: _struct_pb2.Struct
    battery_percent: int
    charging: bool
    network_type: str
    temperature_celsius: float
    free_storage_bytes: int
    companion_version: str
    current_task_run_id: str
    current_task_state: str
    automation_stopped: bool
    def __init__(
        self,
        device_id: _Optional[str] = ...,
        state: _Optional[str] = ...,
        android_version: _Optional[str] = ...,
        lamda_version: _Optional[str] = ...,
        app_versions: _Optional[_Mapping[str, str]] = ...,
        capabilities: _Optional[_Union[_struct_pb2.Struct, _Mapping[str, object]]] = ...,
        battery_percent: _Optional[int] = ...,
        charging: _Optional[bool] = ...,
        network_type: _Optional[str] = ...,
        temperature_celsius: _Optional[float] = ...,
        free_storage_bytes: _Optional[int] = ...,
        companion_version: _Optional[str] = ...,
        current_task_run_id: _Optional[str] = ...,
        current_task_state: _Optional[str] = ...,
        automation_stopped: _Optional[bool] = ...,
    ) -> None: ...

class StartCommand(_message.Message):
    __slots__ = (
        "command_id",
        "task_run_id",
        "device_id",
        "lease_id",
        "fencing_token",
        "deadline",
        "command_type",
        "payload",
        "artifacts",
    )
    COMMAND_ID_FIELD_NUMBER: _ClassVar[int]
    TASK_RUN_ID_FIELD_NUMBER: _ClassVar[int]
    DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    LEASE_ID_FIELD_NUMBER: _ClassVar[int]
    FENCING_TOKEN_FIELD_NUMBER: _ClassVar[int]
    DEADLINE_FIELD_NUMBER: _ClassVar[int]
    COMMAND_TYPE_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_FIELD_NUMBER: _ClassVar[int]
    ARTIFACTS_FIELD_NUMBER: _ClassVar[int]
    command_id: str
    task_run_id: str
    device_id: str
    lease_id: str
    fencing_token: int
    deadline: _timestamp_pb2.Timestamp
    command_type: str
    payload: _struct_pb2.Struct
    artifacts: _containers.RepeatedCompositeFieldContainer[ArtifactRef]
    def __init__(
        self,
        command_id: _Optional[str] = ...,
        task_run_id: _Optional[str] = ...,
        device_id: _Optional[str] = ...,
        lease_id: _Optional[str] = ...,
        fencing_token: _Optional[int] = ...,
        deadline: _Optional[
            _Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping[str, object]]
        ] = ...,
        command_type: _Optional[str] = ...,
        payload: _Optional[_Union[_struct_pb2.Struct, _Mapping[str, object]]] = ...,
        artifacts: _Optional[_Iterable[_Union[ArtifactRef, _Mapping[str, object]]]] = ...,
    ) -> None: ...

class ArtifactRef(_message.Message):
    __slots__ = (
        "object_key",
        "sha256",
        "size",
        "kind",
        "content_type",
        "file_name",
        "split_name",
        "package_name",
    )
    OBJECT_KEY_FIELD_NUMBER: _ClassVar[int]
    SHA256_FIELD_NUMBER: _ClassVar[int]
    SIZE_FIELD_NUMBER: _ClassVar[int]
    KIND_FIELD_NUMBER: _ClassVar[int]
    CONTENT_TYPE_FIELD_NUMBER: _ClassVar[int]
    FILE_NAME_FIELD_NUMBER: _ClassVar[int]
    SPLIT_NAME_FIELD_NUMBER: _ClassVar[int]
    PACKAGE_NAME_FIELD_NUMBER: _ClassVar[int]
    object_key: str
    sha256: str
    size: int
    kind: str
    content_type: str
    file_name: str
    split_name: str
    package_name: str
    def __init__(
        self,
        object_key: _Optional[str] = ...,
        sha256: _Optional[str] = ...,
        size: _Optional[int] = ...,
        kind: _Optional[str] = ...,
        content_type: _Optional[str] = ...,
        file_name: _Optional[str] = ...,
        split_name: _Optional[str] = ...,
        package_name: _Optional[str] = ...,
    ) -> None: ...

class CancelCommand(_message.Message):
    __slots__ = ("command_id", "reason")
    COMMAND_ID_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    command_id: str
    reason: str
    def __init__(self, command_id: _Optional[str] = ..., reason: _Optional[str] = ...) -> None: ...

class CommandAck(_message.Message):
    __slots__ = ("command_id", "state", "error_code", "detail")
    COMMAND_ID_FIELD_NUMBER: _ClassVar[int]
    STATE_FIELD_NUMBER: _ClassVar[int]
    ERROR_CODE_FIELD_NUMBER: _ClassVar[int]
    DETAIL_FIELD_NUMBER: _ClassVar[int]
    command_id: str
    state: str
    error_code: str
    detail: str
    def __init__(
        self,
        command_id: _Optional[str] = ...,
        state: _Optional[str] = ...,
        error_code: _Optional[str] = ...,
        detail: _Optional[str] = ...,
    ) -> None: ...

class TaskEvent(_message.Message):
    __slots__ = ("command_id", "task_run_id", "step", "state", "occurred_at", "attributes")
    COMMAND_ID_FIELD_NUMBER: _ClassVar[int]
    TASK_RUN_ID_FIELD_NUMBER: _ClassVar[int]
    STEP_FIELD_NUMBER: _ClassVar[int]
    STATE_FIELD_NUMBER: _ClassVar[int]
    OCCURRED_AT_FIELD_NUMBER: _ClassVar[int]
    ATTRIBUTES_FIELD_NUMBER: _ClassVar[int]
    command_id: str
    task_run_id: str
    step: str
    state: str
    occurred_at: _timestamp_pb2.Timestamp
    attributes: _struct_pb2.Struct
    def __init__(
        self,
        command_id: _Optional[str] = ...,
        task_run_id: _Optional[str] = ...,
        step: _Optional[str] = ...,
        state: _Optional[str] = ...,
        occurred_at: _Optional[
            _Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping[str, object]]
        ] = ...,
        attributes: _Optional[_Union[_struct_pb2.Struct, _Mapping[str, object]]] = ...,
    ) -> None: ...

class EvidenceReady(_message.Message):
    __slots__ = ("command_id", "evidence_id", "kind", "sha256", "size")
    COMMAND_ID_FIELD_NUMBER: _ClassVar[int]
    EVIDENCE_ID_FIELD_NUMBER: _ClassVar[int]
    KIND_FIELD_NUMBER: _ClassVar[int]
    SHA256_FIELD_NUMBER: _ClassVar[int]
    SIZE_FIELD_NUMBER: _ClassVar[int]
    command_id: str
    evidence_id: str
    kind: str
    sha256: str
    size: int
    def __init__(
        self,
        command_id: _Optional[str] = ...,
        evidence_id: _Optional[str] = ...,
        kind: _Optional[str] = ...,
        sha256: _Optional[str] = ...,
        size: _Optional[int] = ...,
    ) -> None: ...

class ConfirmationRequired(_message.Message):
    __slots__ = (
        "confirmation_id",
        "command_id",
        "task_run_id",
        "device_id",
        "title",
        "detail",
        "risk_level",
        "expires_at",
    )
    CONFIRMATION_ID_FIELD_NUMBER: _ClassVar[int]
    COMMAND_ID_FIELD_NUMBER: _ClassVar[int]
    TASK_RUN_ID_FIELD_NUMBER: _ClassVar[int]
    DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    TITLE_FIELD_NUMBER: _ClassVar[int]
    DETAIL_FIELD_NUMBER: _ClassVar[int]
    RISK_LEVEL_FIELD_NUMBER: _ClassVar[int]
    EXPIRES_AT_FIELD_NUMBER: _ClassVar[int]
    confirmation_id: str
    command_id: str
    task_run_id: str
    device_id: str
    title: str
    detail: str
    risk_level: str
    expires_at: _timestamp_pb2.Timestamp
    def __init__(
        self,
        confirmation_id: _Optional[str] = ...,
        command_id: _Optional[str] = ...,
        task_run_id: _Optional[str] = ...,
        device_id: _Optional[str] = ...,
        title: _Optional[str] = ...,
        detail: _Optional[str] = ...,
        risk_level: _Optional[str] = ...,
        expires_at: _Optional[
            _Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping[str, object]]
        ] = ...,
    ) -> None: ...

class OperatorAction(_message.Message):
    __slots__ = ("action_id", "device_id", "command_id", "confirmation_id", "action", "occurred_at")
    ACTION_ID_FIELD_NUMBER: _ClassVar[int]
    DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    COMMAND_ID_FIELD_NUMBER: _ClassVar[int]
    CONFIRMATION_ID_FIELD_NUMBER: _ClassVar[int]
    ACTION_FIELD_NUMBER: _ClassVar[int]
    OCCURRED_AT_FIELD_NUMBER: _ClassVar[int]
    action_id: str
    device_id: str
    command_id: str
    confirmation_id: str
    action: str
    occurred_at: _timestamp_pb2.Timestamp
    def __init__(
        self,
        action_id: _Optional[str] = ...,
        device_id: _Optional[str] = ...,
        command_id: _Optional[str] = ...,
        confirmation_id: _Optional[str] = ...,
        action: _Optional[str] = ...,
        occurred_at: _Optional[
            _Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping[str, object]]
        ] = ...,
    ) -> None: ...

class ArtifactDeliveryEvent(_message.Message):
    __slots__ = (
        "command_id",
        "task_run_id",
        "device_id",
        "artifact",
        "state",
        "bytes_received",
        "error_code",
        "occurred_at",
    )
    COMMAND_ID_FIELD_NUMBER: _ClassVar[int]
    TASK_RUN_ID_FIELD_NUMBER: _ClassVar[int]
    DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    ARTIFACT_FIELD_NUMBER: _ClassVar[int]
    STATE_FIELD_NUMBER: _ClassVar[int]
    BYTES_RECEIVED_FIELD_NUMBER: _ClassVar[int]
    ERROR_CODE_FIELD_NUMBER: _ClassVar[int]
    OCCURRED_AT_FIELD_NUMBER: _ClassVar[int]
    command_id: str
    task_run_id: str
    device_id: str
    artifact: ArtifactRef
    state: str
    bytes_received: int
    error_code: str
    occurred_at: _timestamp_pb2.Timestamp
    def __init__(
        self,
        command_id: _Optional[str] = ...,
        task_run_id: _Optional[str] = ...,
        device_id: _Optional[str] = ...,
        artifact: _Optional[_Union[ArtifactRef, _Mapping[str, object]]] = ...,
        state: _Optional[str] = ...,
        bytes_received: _Optional[int] = ...,
        error_code: _Optional[str] = ...,
        occurred_at: _Optional[
            _Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping[str, object]]
        ] = ...,
    ) -> None: ...

class DebugSessionGrant(_message.Message):
    __slots__ = (
        "session_id",
        "device_id",
        "expires_at",
        "capabilities",
        "lease_id",
        "fencing_token",
        "relay_token",
    )
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    EXPIRES_AT_FIELD_NUMBER: _ClassVar[int]
    CAPABILITIES_FIELD_NUMBER: _ClassVar[int]
    LEASE_ID_FIELD_NUMBER: _ClassVar[int]
    FENCING_TOKEN_FIELD_NUMBER: _ClassVar[int]
    RELAY_TOKEN_FIELD_NUMBER: _ClassVar[int]
    session_id: str
    device_id: str
    expires_at: _timestamp_pb2.Timestamp
    capabilities: _containers.RepeatedScalarFieldContainer[str]
    lease_id: str
    fencing_token: int
    relay_token: str
    def __init__(
        self,
        session_id: _Optional[str] = ...,
        device_id: _Optional[str] = ...,
        expires_at: _Optional[
            _Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping[str, object]]
        ] = ...,
        capabilities: _Optional[_Iterable[str]] = ...,
        lease_id: _Optional[str] = ...,
        fencing_token: _Optional[int] = ...,
        relay_token: _Optional[str] = ...,
    ) -> None: ...

class CertificateRevocationUpdate(_message.Message):
    __slots__ = ("revoked_fingerprints",)
    REVOKED_FINGERPRINTS_FIELD_NUMBER: _ClassVar[int]
    revoked_fingerprints: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, revoked_fingerprints: _Optional[_Iterable[str]] = ...) -> None: ...

class ConfirmationResolution(_message.Message):
    __slots__ = ("confirmation_id", "command_id", "approved", "actor_id", "decided_at")
    CONFIRMATION_ID_FIELD_NUMBER: _ClassVar[int]
    COMMAND_ID_FIELD_NUMBER: _ClassVar[int]
    APPROVED_FIELD_NUMBER: _ClassVar[int]
    ACTOR_ID_FIELD_NUMBER: _ClassVar[int]
    DECIDED_AT_FIELD_NUMBER: _ClassVar[int]
    confirmation_id: str
    command_id: str
    approved: bool
    actor_id: str
    decided_at: _timestamp_pb2.Timestamp
    def __init__(
        self,
        confirmation_id: _Optional[str] = ...,
        command_id: _Optional[str] = ...,
        approved: _Optional[bool] = ...,
        actor_id: _Optional[str] = ...,
        decided_at: _Optional[
            _Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping[str, object]]
        ] = ...,
    ) -> None: ...

class DebugSessionRevoke(_message.Message):
    __slots__ = ("session_id", "device_id", "reason")
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    session_id: str
    device_id: str
    reason: str
    def __init__(
        self,
        session_id: _Optional[str] = ...,
        device_id: _Optional[str] = ...,
        reason: _Optional[str] = ...,
    ) -> None: ...

class DebugEventRequest(_message.Message):
    __slots__ = ("event_id", "tenant_id", "aggregate_id", "event_type", "occurred_at", "payload")
    EVENT_ID_FIELD_NUMBER: _ClassVar[int]
    TENANT_ID_FIELD_NUMBER: _ClassVar[int]
    AGGREGATE_ID_FIELD_NUMBER: _ClassVar[int]
    EVENT_TYPE_FIELD_NUMBER: _ClassVar[int]
    OCCURRED_AT_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_FIELD_NUMBER: _ClassVar[int]
    event_id: str
    tenant_id: str
    aggregate_id: str
    event_type: str
    occurred_at: _timestamp_pb2.Timestamp
    payload: _struct_pb2.Struct
    def __init__(
        self,
        event_id: _Optional[str] = ...,
        tenant_id: _Optional[str] = ...,
        aggregate_id: _Optional[str] = ...,
        event_type: _Optional[str] = ...,
        occurred_at: _Optional[
            _Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping[str, object]]
        ] = ...,
        payload: _Optional[_Union[_struct_pb2.Struct, _Mapping[str, object]]] = ...,
    ) -> None: ...

class DebugEventResponse(_message.Message):
    __slots__ = ("accepted", "detail")
    ACCEPTED_FIELD_NUMBER: _ClassVar[int]
    DETAIL_FIELD_NUMBER: _ClassVar[int]
    accepted: bool
    detail: str
    def __init__(self, accepted: _Optional[bool] = ..., detail: _Optional[str] = ...) -> None: ...

class DebugRelayFrame(_message.Message):
    __slots__ = ("session_id", "request_id", "capability", "kind", "payload", "end", "device_id")
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    CAPABILITY_FIELD_NUMBER: _ClassVar[int]
    KIND_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_FIELD_NUMBER: _ClassVar[int]
    END_FIELD_NUMBER: _ClassVar[int]
    DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    session_id: str
    request_id: str
    capability: str
    kind: str
    payload: bytes
    end: bool
    device_id: str
    def __init__(
        self,
        session_id: _Optional[str] = ...,
        request_id: _Optional[str] = ...,
        capability: _Optional[str] = ...,
        kind: _Optional[str] = ...,
        payload: _Optional[bytes] = ...,
        end: _Optional[bool] = ...,
        device_id: _Optional[str] = ...,
    ) -> None: ...
