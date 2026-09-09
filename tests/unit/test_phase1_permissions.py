from cloudctl_domain import Permission, Role, require_permissions
from cloudctl_domain.errors import ForbiddenError
import pytest


def test_phase1_permissions_cover_device_control_and_recipe_publish() -> None:
    require_permissions([Role.DEVICE_OPERATOR], Permission.DEVICE_CONTROL, Permission.TASK_CREATE)
    require_permissions([Role.AUTOMATION_DEVELOPER], Permission.RECIPE_PUBLISH)
    require_permissions([Role.CONTENT_EDITOR], Permission.DATA_DELETE)
    with pytest.raises(ForbiddenError):
        require_permissions([Role.VIEWER], Permission.DEVICE_CONTROL)
    with pytest.raises(ForbiddenError):
        require_permissions([Role.PUBLISHER], Permission.RECIPE_PUBLISH)
