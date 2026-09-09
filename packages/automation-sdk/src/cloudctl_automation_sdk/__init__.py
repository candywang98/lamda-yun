"""Capability-scoped automation package SDK."""

from .lifecycle import AutomationContext, AutomationPackage, LifecycleRunner, ReconcileResult
from .manifest import AutomationManifest, validate_manifest
from .protocols import (
    APP_LIFECYCLE_CAPABILITY,
    EVIDENCE_CAPTURE_CAPABILITY,
    FILE_PUSH_CAPABILITY,
    INPUT_SWIPE_CAPABILITY,
    INPUT_TAP_CAPABILITY,
    INPUT_TEXT_CAPABILITY,
    SCREENSHOT_CAPABILITY,
    UI_DUMP_CAPABILITY,
    UI_SELECTORS_CAPABILITY,
    VIEW_FRAME_CAPABILITY,
    VIEW_LAYOUT_CAPABILITY,
    CapabilityDenied,
    DeviceDriver,
    SwipeDirection,
    require_capability,
    validate_input_text,
    validate_locator_name,
    validate_swipe,
)
from .recipe import RecipePackage, validate_recipe_package
from .registry import (
    RolloutEvidence,
    evaluate_rollout_promotion,
    package_signature_payload,
    verify_package_signature,
)

__all__ = [
    "AutomationContext",
    "AutomationManifest",
    "AutomationPackage",
    "APP_LIFECYCLE_CAPABILITY",
    "CapabilityDenied",
    "DeviceDriver",
    "EVIDENCE_CAPTURE_CAPABILITY",
    "FILE_PUSH_CAPABILITY",
    "INPUT_SWIPE_CAPABILITY",
    "INPUT_TAP_CAPABILITY",
    "INPUT_TEXT_CAPABILITY",
    "LifecycleRunner",
    "ReconcileResult",
    "RolloutEvidence",
    "SCREENSHOT_CAPABILITY",
    "SwipeDirection",
    "UI_DUMP_CAPABILITY",
    "UI_SELECTORS_CAPABILITY",
    "VIEW_FRAME_CAPABILITY",
    "VIEW_LAYOUT_CAPABILITY",
    "require_capability",
    "validate_input_text",
    "validate_locator_name",
    "validate_manifest",
    "validate_recipe_package",
    "RecipePackage",
    "validate_swipe",
    "evaluate_rollout_promotion",
    "package_signature_payload",
    "verify_package_signature",
]
