from __future__ import annotations

import pytest
from cloudctl_automation_sdk import (
    APP_LIFECYCLE_CAPABILITY,
    EVIDENCE_CAPTURE_CAPABILITY,
    FILE_PUSH_CAPABILITY,
    INPUT_TAP_CAPABILITY,
    SCREENSHOT_CAPABILITY,
    UI_DUMP_CAPABILITY,
    UI_SELECTORS_CAPABILITY,
    VIEW_FRAME_CAPABILITY,
    VIEW_LAYOUT_CAPABILITY,
    CapabilityDenied,
    SwipeDirection,
    require_capability,
    validate_input_text,
    validate_locator_name,
    validate_swipe,
)


def test_input_helpers_accept_only_explicit_bounded_values() -> None:
    require_capability(frozenset({INPUT_TAP_CAPABILITY}), INPUT_TAP_CAPABILITY)
    assert validate_locator_name("publish.primary") == "publish.primary"
    assert validate_input_text("approved content") == "approved content"
    assert validate_swipe(SwipeDirection.UP, 32) == (SwipeDirection.UP, 32)


def test_capability_constants_match_manifest_and_debug_contracts() -> None:
    assert {
        UI_SELECTORS_CAPABILITY,
        APP_LIFECYCLE_CAPABILITY,
        FILE_PUSH_CAPABILITY,
        SCREENSHOT_CAPABILITY,
        UI_DUMP_CAPABILITY,
    } == {"ui.selectors", "app.lifecycle", "file.push", "screenshot", "ui.dump"}
    assert {
        VIEW_FRAME_CAPABILITY,
        VIEW_LAYOUT_CAPABILITY,
        INPUT_TAP_CAPABILITY,
        EVIDENCE_CAPTURE_CAPABILITY,
    } == {"view.frame", "view.layout", "input.tap", "evidence.capture"}


def test_input_helpers_reject_missing_capability_and_bypass_shapes() -> None:
    with pytest.raises(CapabilityDenied, match="input.tap"):
        require_capability(frozenset(), INPUT_TAP_CAPABILITY)
    with pytest.raises(ValueError, match="signed registry"):
        validate_locator_name("../../arbitrary-coordinate-script")
    with pytest.raises(ValueError, match="NUL"):
        validate_input_text("unsafe\x00payload")
    with pytest.raises(ValueError, match="direction"):
        validate_swipe("DIAGONAL", 32)
    with pytest.raises(ValueError, match="between"):
        validate_swipe(SwipeDirection.DOWN, 201)
