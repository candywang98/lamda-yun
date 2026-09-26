from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

PACKAGE_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+$")
LOCATOR_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
STEP_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
MAX_STEPS = 100
MAX_TOTAL_TIMEOUT_MS = 900_000
SENSITIVE_KEY_FRAGMENTS = (
    "password",
    "secret",
    "token",
    "credential",
    "private",
    "input",
    "text",
)


def validate_bounded_safe_mapping(
    value: Mapping[str, str | int | float | bool | None],
    *,
    max_entries: int,
    max_string_length: int,
) -> dict[str, str | int | float | bool | None]:
    if len(value) > max_entries:
        raise ValueError(f"mapping is limited to {max_entries} entries")
    for key, item in value.items():
        normalized = key.lower().replace("_", "").replace("-", "")
        if any(fragment in normalized for fragment in SENSITIVE_KEY_FRAGMENTS):
            raise ValueError("sensitive field names are forbidden")
        if len(key) > 64 or (isinstance(item, str) and len(item) > max_string_length):
            raise ValueError("mapping field exceeds size limits")
    return dict(value)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class LocatorStep(StrictModel):
    step_id: str = Field(alias="stepId", min_length=1, max_length=128)
    locator_ref: str = Field(alias="locatorRef", min_length=1, max_length=128)
    timeout_ms: int = Field(default=10_000, alias="timeoutMs", ge=100, le=60_000)

    @field_validator("locator_ref")
    @classmethod
    def locator_is_registry_name(cls, value: str) -> str:
        if not LOCATOR_PATTERN.fullmatch(value):
            raise ValueError("locatorRef must be a signed locator registry name")
        return value

    @field_validator("step_id")
    @classmethod
    def valid_step_id(cls, value: str) -> str:
        if not STEP_ID_PATTERN.fullmatch(value):
            raise ValueError("stepId is invalid")
        return value


class FindStep(LocatorStep):
    action: Literal["ui.find"]


class TapStep(LocatorStep):
    action: Literal["ui.tap"]
    postcondition_ref: str | None = Field(
        default=None, alias="postconditionLocatorRef", min_length=1, max_length=128
    )

    @field_validator("postcondition_ref")
    @classmethod
    def postcondition_is_registry_name(cls, value: str) -> str:
        if not LOCATOR_PATTERN.fullmatch(value):
            raise ValueError("postconditionLocatorRef must be a signed locator registry name")
        return value


class InputStep(LocatorStep):
    action: Literal["ui.input"]
    value: str = Field(max_length=1024)
    replace: Literal[True] = True
    sensitive: bool = False

    @field_validator("value")
    @classmethod
    def bounded_text(cls, value: str) -> str:
        if "\x00" in value:
            raise ValueError("input value cannot contain NUL")
        return value


class TapTextStep(StrictModel):
    step_id: str = Field(alias="stepId", min_length=1, max_length=128)
    action: Literal["ui.tapText"]
    value: str = Field(min_length=1, max_length=64)
    timeout_ms: int = Field(default=10_000, alias="timeoutMs", ge=100, le=60_000)

    @field_validator("step_id")
    @classmethod
    def valid_step_id(cls, value: str) -> str:
        if not STEP_ID_PATTERN.fullmatch(value):
            raise ValueError("stepId is invalid")
        return value


class WaitStep(LocatorStep):
    action: Literal["ui.wait"]
    condition: Literal["EXISTS", "NOT_EXISTS", "ENABLED"]
    poll_ms: int = Field(default=500, alias="pollMs", ge=100, le=2_000)


class ScreenshotStep(StrictModel):
    step_id: str = Field(alias="stepId", min_length=1, max_length=128)
    action: Literal["ui.screenshot"]
    label: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_.:-]+$")
    timeout_ms: int = Field(default=15_000, alias="timeoutMs", ge=100, le=60_000)

    @field_validator("step_id")
    @classmethod
    def valid_step_id(cls, value: str) -> str:
        if not STEP_ID_PATTERN.fullmatch(value):
            raise ValueError("stepId is invalid")
        return value


XIANYU_TAP_LAYOUT_REFS = frozenset(
    {
        "polish_all",
        "more",
        "delist_menu_item",
        "confirm_delist",
        "delete_card",
        "confirm_delete",
    }
)
MAX_CARD_INDEX = 9  # Companion parser bound (AutomationTask.kt ui.tapLayout)


class TapLayoutStep(StrictModel):
    """Coordinate-derived xianyu region tap guarded by the frozen 20260915 anchors."""

    step_id: str = Field(alias="stepId", min_length=1, max_length=128)
    action: Literal["ui.tapLayout"]
    layout_action: str = Field(alias="layoutAction", min_length=1, max_length=128)
    tab: Literal["onsale", "draft", "delisted"]
    card_index: int = Field(alias="cardIndex", ge=0, le=MAX_CARD_INDEX)
    timeout_ms: int = Field(default=10_000, alias="timeoutMs", ge=100, le=60_000)

    @field_validator("step_id")
    @classmethod
    def valid_step_id(cls, value: str) -> str:
        if not STEP_ID_PATTERN.fullmatch(value):
            raise ValueError("stepId is invalid")
        return value

    @field_validator("layout_action")
    @classmethod
    def approved_layout(cls, value: str) -> str:
        if value not in XIANYU_TAP_LAYOUT_REFS:
            raise ValueError("layoutAction must be an approved xianyu maintenance layout")
        return value


class AssertBadgeStep(StrictModel):
    """Verify the published-lists tab badge moved by exactly the expected delta."""

    step_id: str = Field(alias="stepId", min_length=1, max_length=128)
    action: Literal["ui.assertBadge"]
    locator_ref: Literal["xianyu_pub_tab_onsale", "xianyu_pub_tab_delisted"] = Field(
        alias="locatorRef"
    )
    expected_delta: int = Field(alias="expectedDelta", ge=-50, le=0)
    timeout_ms: int = Field(default=15_000, alias="timeoutMs", ge=100, le=60_000)

    @field_validator("step_id")
    @classmethod
    def valid_step_id(cls, value: str) -> str:
        if not STEP_ID_PATTERN.fullmatch(value):
            raise ValueError("stepId is invalid")
        return value


class ReadOrdersStep(LocatorStep):
    """Read order rows from the current xianyu order list screen.

    Contract order-sync/20260915.1 §5: exactly one per task, direction SOLD or
    BOUGHT, maxRows 1..10, locatorRef points at the list container locator
    (xianyu_orders_container; the registry entry is unverified/fail-closed on
    the device until the real-device survey flips it).
    """

    action: Literal["ui.readOrders"]
    direction: Literal["SOLD", "BOUGHT"]
    max_rows: int = Field(alias="maxRows", ge=1, le=10)


class SwipeUpStep(LocatorStep):
    """Scroll the orders list container up by one screen (order-sync-slice2 §1).

    Named after the executor's internal swipeUp primitive (the waitFor price
    polling already scrolls that way). The task-level action itself is new in
    slice 2: the current Companion APK safely rejects it as an unknown action
    until the W4-side v2 executor lands, and the backend accepts it only
    inside the frozen xianyu.collect_orders.steps.v2 shape. locatorRef points
    at the list container so the swipe stays inside its bounds (never a
    full-screen swipe).
    """

    action: Literal["ui.swipeUp"]


class TapCardByTitleStep(StrictModel):
    """Open a published-list card by its title text (maintenance v2 title path).

    Contract xianyu-anchors-20260915 §1/§2: the companion searches the visible
    cards below the live tab strip on the requested list, taps the unique
    matching card's bounds center and enters the detail page. Zero or several
    matches fail the step with zero side effects; the draft tab has no
    surveyed cards, so only onsale/delisted are addressable.
    """

    step_id: str = Field(alias="stepId", min_length=1, max_length=128)
    action: Literal["ui.tapCardByTitle"]
    title_contains: str = Field(alias="titleContains", min_length=1, max_length=64)
    tab: Literal["onsale", "delisted"]
    timeout_ms: int = Field(default=10_000, alias="timeoutMs", ge=100, le=60_000)

    @field_validator("step_id")
    @classmethod
    def valid_step_id(cls, value: str) -> str:
        if not STEP_ID_PATTERN.fullmatch(value):
            raise ValueError("stepId is invalid")
        return value


class AppRestartStep(StrictModel):
    """P35: standard-permission soft restart (CLEAR_TASK relaunch, no force-stop)."""

    step_id: str = Field(alias="stepId", min_length=1, max_length=128)
    action: Literal["app.restart"]
    timeout_ms: int = Field(default=30_000, alias="timeoutMs", ge=1_000, le=120_000)

    @field_validator("step_id")
    @classmethod
    def valid_step_id(cls, value: str) -> str:
        if not STEP_ID_PATTERN.fullmatch(value):
            raise ValueError("stepId is invalid")
        return value


class CollectListingsStep(StrictModel):
    """Collect the whole 在卖 tab of 我发布的 (xy-tasks-24, listing-collect).

    One action runs the full loop on the companion: dismiss the entry popups,
    read every visible card's content-desc, push the parsed rows per screen,
    semantic-scroll, and stop at the 「所有宝贝加载完成」 anchor (or the
    maxScreens bound). Read-only: the only gestures are popup dismiss and the
    list's own scroll action — never a card tap.
    """

    step_id: str = Field(alias="stepId", min_length=1, max_length=128)
    action: Literal["ui.collectListings"]
    tab: Literal["onsale"] = "onsale"
    max_screens: int = Field(default=40, alias="maxScreens", ge=1, le=40)
    timeout_ms: int = Field(default=600_000, alias="timeoutMs", ge=1_000, le=900_000)

    @field_validator("step_id")
    @classmethod
    def valid_step_id(cls, value: str) -> str:
        if not STEP_ID_PATTERN.fullmatch(value):
            raise ValueError("stepId is invalid")
        return value


class ReviewOrdersStep(StrictModel):
    """P34 auto-review of pending sold orders (XY-REVIEW-001, xy-review/20260921).

    One action runs the whole loop on the companion: from the 待评价 tab of
    我卖出的, open each order's review editor, pick 好评, fill the fixed
    [comment], capture before/after evidence per order and submit — or stop
    before the submit tap when dryRun (default; the filled editor is
    screenshotted for operator verification instead). The loop ends at
    maxOrders, when no 去评价 entry remains, or at the step window edge.
    """

    step_id: str = Field(alias="stepId", min_length=1, max_length=128)
    action: Literal["xianyu.reviewOrders"]
    max_orders: int = Field(default=10, alias="maxOrders", ge=1, le=50)
    comment: str = Field(min_length=1, max_length=200)
    dry_run: bool = Field(default=True, alias="dryRun")
    timeout_ms: int = Field(default=300_000, alias="timeoutMs", ge=1_000, le=900_000)

    @field_validator("step_id")
    @classmethod
    def valid_step_id(cls, value: str) -> str:
        if not STEP_ID_PATTERN.fullmatch(value):
            raise ValueError("stepId is invalid")
        return value

    @field_validator("comment")
    @classmethod
    def bounded_comment(cls, value: str) -> str:
        if "\x00" in value:
            raise ValueError("comment cannot contain NUL")
        return value


class AssertStep(LocatorStep):
    action: Literal["ui.assert"]
    predicate: Literal["EXISTS", "NOT_EXISTS", "ENABLED"]


class LogStep(StrictModel):
    step_id: str = Field(alias="stepId", min_length=1, max_length=128)
    action: Literal["run.log"]
    level: Literal["DEBUG", "INFO", "WARN", "ERROR"] = "INFO"
    message_code: str = Field(alias="messageCode", pattern=r"^[A-Z][A-Z0-9_.:-]{0,79}$")
    timeout_ms: int = Field(default=1_000, alias="timeoutMs", ge=100, le=60_000)

    @field_validator("step_id")
    @classmethod
    def valid_step_id(cls, value: str) -> str:
        if not STEP_ID_PATTERN.fullmatch(value):
            raise ValueError("stepId is invalid")
        return value


MobileStep = Annotated[
    FindStep
    | TapStep
    | TapTextStep
    | InputStep
    | WaitStep
    | ScreenshotStep
    | TapLayoutStep
    | AssertBadgeStep
    | ReadOrdersStep
    | SwipeUpStep
    | TapCardByTitleStep
    | AppRestartStep
    | CollectListingsStep
    | ReviewOrdersStep
    | AssertStep
    | LogStep,
    Field(discriminator="action"),
]


class MobileEnrollmentCreate(StrictModel):
    device_id: str = Field(alias="deviceId", min_length=1, max_length=36)
    ttl_seconds: int = Field(default=600, alias="ttlSeconds", ge=60, le=3600)


class MobileDeviceCreate(StrictModel):
    logical_name: str = Field(alias="logicalName", min_length=1, max_length=160)
    android_version: str | None = Field(default=None, alias="androidVersion", max_length=32)
    companion_version: str | None = Field(default=None, alias="companionVersion", max_length=128)
    labels: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("labels")
    @classmethod
    def bounded_labels(cls, value: list[str]) -> list[str]:
        if any(not item or len(item) > 80 for item in value):
            raise ValueError("device labels must contain 1 to 80 characters")
        if len(set(value)) != len(value):
            raise ValueError("device labels must be unique")
        return value


class MobileEnrollRequest(StrictModel):
    code: str = Field(min_length=6, max_length=64)
    app_instance_id: str = Field(alias="appInstanceId", min_length=8, max_length=128)
    companion_version: str = Field(alias="companionVersion", min_length=1, max_length=128)


class MobileTaskCreate(StrictModel):
    device_id: str = Field(alias="deviceId", min_length=1, max_length=36)
    target_package: str = Field(alias="targetPackage", min_length=3, max_length=255)
    total_timeout_ms: int = Field(alias="totalTimeoutMs", ge=1_000, le=MAX_TOTAL_TIMEOUT_MS)
    steps: list[MobileStep] = Field(min_length=1, max_length=MAX_STEPS)
    media_delivery: MobileMediaDelivery | None = Field(default=None, alias="mediaDelivery")
    account_id: str | None = Field(default=None, alias="accountId", min_length=1, max_length=36)
    expected_binding_version: int | None = Field(default=None, alias="expectedBindingVersion", ge=1)

    @field_validator("target_package")
    @classmethod
    def valid_package(cls, value: str) -> str:
        if not PACKAGE_PATTERN.fullmatch(value):
            raise ValueError("targetPackage is invalid")
        return value

    @model_validator(mode="after")
    def timeout_covers_bounded_steps(self) -> MobileTaskCreate:
        step_ids = [step.step_id for step in self.steps]
        if len(set(step_ids)) != len(step_ids):
            raise ValueError("stepId values must be unique")
        total = sum(step.timeout_ms for step in self.steps)
        if total > self.total_timeout_ms:
            raise ValueError("sum of step timeouts exceeds totalTimeoutMs")
        return self


class MobileMediaDelivery(StrictModel):
    delivery_id: str = Field(
        alias="deliveryId",
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
    )
    asset_ids: list[str] = Field(alias="assetIds", min_length=1, max_length=50)

    @field_validator("asset_ids")
    @classmethod
    def bounded_unique_assets(cls, value: list[str]) -> list[str]:
        pattern = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"
        if any(not item or len(item) > 128 or not re.fullmatch(pattern, item) for item in value):
            raise ValueError("assetIds contain an invalid ID")
        if len(set(value)) != len(value):
            raise ValueError("assetIds must be unique")
        return value


class MobileMediaManifestRequest(StrictModel):
    delivery_id: str = Field(
        alias="deliveryId",
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
    )
    asset_ids: list[str] = Field(alias="assetIds", min_length=1, max_length=50)

    @field_validator("asset_ids")
    @classmethod
    def unique_asset_ids(cls, value: list[str]) -> list[str]:
        if any(not item or len(item) > 128 for item in value):
            raise ValueError("assetIds must contain bounded non-empty IDs")
        if len(set(value)) != len(value):
            raise ValueError("assetIds must be unique")
        return value


class MobilePublishListingRequest(StrictModel):
    description: str = Field(min_length=1, max_length=1024)
    price: str = Field(min_length=1, max_length=32, pattern=r"^[0-9]+(\.[0-9]{1,2})?$")
    # Gallery tile 0 is the camera shutter: at most 49 images are selectable.
    media_asset_ids: list[str] | None = Field(
        default=None, alias="mediaAssetIds", min_length=1, max_length=49
    )
    delivery_id: str | None = Field(default=None, alias="deliveryId", min_length=1, max_length=64)
    auto_publish: bool = Field(
        default=False,
        alias="autoPublish",
        description="Open-only default: a human operator confirms submission.",
    )


class MobileClaimRequest(StrictModel):
    lease_seconds: int = Field(default=60, alias="leaseSeconds", ge=10, le=300)


class MobileTaskRelease(StrictModel):
    lease_id: str = Field(alias="leaseId", min_length=1, max_length=36)
    reason: Literal["ACCESSIBILITY_NOT_ENABLED", "ACCESSIBILITY_NOT_ACTIVE"]


_NETWORK_ALIASES = {
    "WIFI": "WIFI",
    "WI-FI": "WIFI",
    "CELLULAR": "CELLULAR",
    "CELL": "CELLULAR",
    "UNKNOWN": "UNKNOWN",
    "OFFLINE": "UNKNOWN",
    "ETHERNET": "WIFI",
    "CONNECTED": "UNKNOWN",
}


class MobileDeviceHealth(StrictModel):
    battery_percent: int | None = Field(default=None, alias="batteryPercent", ge=0, le=100)
    charging: bool | None = None
    network: Literal["WIFI", "CELLULAR", "UNKNOWN"] | None = Field(default=None)

    @field_validator("network", mode="before")
    @classmethod
    def normalize_network(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        return _NETWORK_ALIASES.get(value.strip().upper().replace(" ", ""), value)

    temperature_celsius: float | None = Field(default=None, alias="temperatureCelsius")
    free_storage_bytes: int | None = Field(default=None, alias="freeStorageBytes", ge=0)
    manufacturer: str | None = Field(default=None, max_length=80)
    model: str | None = Field(default=None, max_length=80)
    sdk_int: int | None = Field(default=None, alias="sdkInt", ge=1, le=100)
    rom_summary: str | None = Field(default=None, alias="romSummary", max_length=160)
    media_projection: Literal["GRANTED", "DENIED", "UNKNOWN"] | None = Field(
        default=None, alias="mediaProjection"
    )
    input_method: str | None = Field(default=None, alias="inputMethod", max_length=80)
    gesture_available: bool | None = Field(default=None, alias="gestureAvailable")


class MobileDeviceHeartbeat(StrictModel):
    companion_version: str = Field(alias="companionVersion", min_length=1, max_length=128)
    android_version: str | None = Field(default=None, alias="androidVersion", max_length=32)
    accessibility_enabled: bool = Field(alias="accessibilityEnabled")
    runner_state: Literal["IDLE", "RUNNING", "STOPPED"] = Field(alias="runnerState")
    battery_optimization_ignored: bool | None = Field(
        default=None, alias="batteryOptimizationIgnored"
    )
    health: MobileDeviceHealth | None = None


class MobileHeartbeat(StrictModel):
    lease_id: str = Field(alias="leaseId", min_length=1, max_length=36)
    current_step: int | None = Field(default=None, alias="currentStep", ge=0, le=MAX_STEPS - 1)
    lease_seconds: int = Field(default=60, alias="leaseSeconds", ge=10, le=300)


class MobileTaskEvent(StrictModel):
    lease_id: str = Field(alias="leaseId", min_length=1, max_length=36)
    sequence: int = Field(ge=1)
    event_type: Literal[
        "STEP_STARTED",
        "STEP_SUCCEEDED",
        "STEP_FAILED",
        "EVIDENCE",
        "LOG",
        "PAUSE_REQUESTED",
        "PAUSED_WAITING_USER",
        "RESUME_CHECK",
        "RECONCILING",
    ] = Field(alias="eventType")
    step_index: int | None = Field(default=None, alias="stepIndex", ge=0, le=MAX_STEPS - 1)
    step_id: str | None = Field(default=None, alias="stepId", max_length=128)
    attempt_id: str | None = Field(default=None, alias="attemptId", max_length=36)
    payload: dict[str, str | int | float | bool | None] = Field(default_factory=dict)

    @field_validator("payload")
    @classmethod
    def bounded_payload(
        cls, value: dict[str, str | int | float | bool | None]
    ) -> dict[str, str | int | float | bool | None]:
        return validate_bounded_safe_mapping(value, max_entries=30, max_string_length=1000)


RESULT_TYPES = {
    "xianyu.publish_listing.v1": "XianyuPublishListingResult",
    "xianyu.collect_orders.v1": "XianyuCollectOrdersResult",
    "xiaohongshu.publish_note.v1": "XiaohongshuPublishNoteResult",
    "device.probe_capabilities.v1": "DeviceProbeResult",
}


class MobileTaskCompletion(StrictModel):
    lease_id: str = Field(alias="leaseId", min_length=1, max_length=36)
    result: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    result_type: str | None = Field(default=None, alias="resultType", max_length=80)
    schema_version: int | None = Field(default=None, alias="schemaVersion", ge=1)

    @field_validator("result")
    @classmethod
    def bounded_result(
        cls, value: dict[str, str | int | float | bool | None]
    ) -> dict[str, str | int | float | bool | None]:
        return validate_bounded_safe_mapping(value, max_entries=30, max_string_length=1000)


class MobileTaskFailure(StrictModel):
    lease_id: str = Field(alias="leaseId", min_length=1, max_length=36)
    error_code: str = Field(alias="errorCode", pattern=r"^[A-Z][A-Z0-9_]{0,79}$")
    detail: str = Field(min_length=1, max_length=2000)


class DevicePreviewSessionCreate(StrictModel):
    ttl_seconds: int = Field(default=120, alias="ttlSeconds", ge=30, le=300)
    capture_interval_ms: int = Field(default=2_000, alias="captureIntervalMs", ge=1_000, le=10_000)


class DevicePreviewUpload(StrictModel):
    session_id: str = Field(alias="sessionId", min_length=36, max_length=36)
    content_type: Literal["image/jpeg"] = Field(alias="contentType")
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    width: int = Field(ge=1, le=4096)
    height: int = Field(ge=1, le=4096)
    image_base64: str = Field(alias="imageBase64", min_length=8, max_length=600_000)
