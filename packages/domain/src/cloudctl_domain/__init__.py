"""Framework-independent CloudCtl domain types and rules."""

from .errors import (
    AuthenticationError,
    ConflictError,
    DomainError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from .events import DomainEvent, canonical_hash, new_uuid7
from .models import (
    Actor,
    Approval,
    CommitIntent,
    DeviceLease,
    PublishSnapshot,
    PublishTargetResult,
)
from .rbac import Permission, Role, require_permissions
from .states import PublishState, assert_publish_transition

__all__ = [
    "Actor",
    "Approval",
    "AuthenticationError",
    "CommitIntent",
    "ConflictError",
    "DeviceLease",
    "DomainError",
    "DomainEvent",
    "ForbiddenError",
    "NotFoundError",
    "Permission",
    "PublishSnapshot",
    "PublishState",
    "PublishTargetResult",
    "Role",
    "ValidationError",
    "assert_publish_transition",
    "canonical_hash",
    "new_uuid7",
    "require_permissions",
]
