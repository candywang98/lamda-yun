"""Role and permission policy used by every control-plane entry point."""

from collections.abc import Collection
from enum import StrEnum

from .errors import ForbiddenError


class Permission(StrEnum):
    TENANT_ADMIN = "tenant.admin"
    CONTENT_READ = "content.read"
    CONTENT_WRITE = "content.write"
    PUBLISH_READ = "publish.read"
    PUBLISH_CREATE = "publish.create"
    PUBLISH_APPROVE = "publish.approve"
    DEVICE_READ = "device.read"
    DEVICE_MAINTAIN = "device.maintain"
    APK_MANAGE = "apk.manage"
    AUTOMATION_MANAGE = "automation.manage"
    DEBUG_SESSION_MANAGE = "debug_session.manage"
    OPERATION_APPROVE = "operation.approve"
    AUDIT_READ = "audit.read"


class Role(StrEnum):
    VIEWER = "viewer"
    CONTENT_EDITOR = "content_editor"
    PUBLISHER = "publisher"
    APPROVER = "approver"
    AUTOMATION_DEVELOPER = "automation_developer"
    DEVICE_OPERATOR = "device_operator"
    SECURITY_ADMIN = "security_admin"
    SYSTEM_SERVICE = "system_service"


ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.VIEWER: frozenset(
        {Permission.CONTENT_READ, Permission.PUBLISH_READ, Permission.DEVICE_READ}
    ),
    Role.CONTENT_EDITOR: frozenset({Permission.CONTENT_READ, Permission.CONTENT_WRITE}),
    Role.PUBLISHER: frozenset(
        {Permission.CONTENT_READ, Permission.PUBLISH_READ, Permission.PUBLISH_CREATE}
    ),
    Role.APPROVER: frozenset(
        {
            Permission.PUBLISH_READ,
            Permission.PUBLISH_APPROVE,
            Permission.OPERATION_APPROVE,
            Permission.DEVICE_READ,
        }
    ),
    Role.AUTOMATION_DEVELOPER: frozenset(
        {Permission.AUTOMATION_MANAGE, Permission.DEBUG_SESSION_MANAGE, Permission.DEVICE_READ}
    ),
    Role.DEVICE_OPERATOR: frozenset(
        {
            Permission.DEVICE_READ,
            Permission.DEVICE_MAINTAIN,
            Permission.DEBUG_SESSION_MANAGE,
            Permission.PUBLISH_READ,
        }
    ),
    Role.SECURITY_ADMIN: frozenset(Permission),
    Role.SYSTEM_SERVICE: frozenset(
        {
            Permission.DEVICE_READ,
            Permission.DEVICE_MAINTAIN,
            Permission.PUBLISH_READ,
            Permission.PUBLISH_CREATE,
            Permission.DEBUG_SESSION_MANAGE,
            Permission.AUDIT_READ,
        }
    ),
}


def effective_permissions(roles: Collection[Role]) -> frozenset[Permission]:
    permissions: set[Permission] = set()
    for role in roles:
        permissions.update(ROLE_PERMISSIONS[role])
    return frozenset(permissions)


def require_permissions(roles: Collection[Role], *required: Permission) -> None:
    missing = set(required) - effective_permissions(roles)
    if missing:
        names = ", ".join(sorted(permission.value for permission in missing))
        raise ForbiddenError(f"missing permissions: {names}")
