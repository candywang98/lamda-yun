from __future__ import annotations

import pytest
from cloudctl_api.operation_schemas import validate_feature_configuration


@pytest.mark.parametrize(
    "key",
    [
        "executionState",
        "executable",
        "operationKey",
        "policy",
        "risk",
        "clientSecret",
        "private-key",
        "shellCommand",
        "scriptName",
        "__proto__",
        "constructor",
        "$where",
    ],
)
def test_dangerous_feature_configuration_keys_are_rejected(key: str) -> None:
    with pytest.raises(ValueError, match="dangerous configuration key"):
        validate_feature_configuration({key: "value"})


def test_feature_configuration_limits_depth_size_nodes_and_strings() -> None:
    nested: dict[str, object] = {}
    cursor = nested
    for index in range(8):
        child: dict[str, object] = {}
        cursor[f"level{index}"] = child
        cursor = child
    with pytest.raises(ValueError, match="nesting depth"):
        validate_feature_configuration(nested)

    with pytest.raises(ValueError, match="64 KiB"):
        validate_feature_configuration({f"section{index}": "x" * 8_000 for index in range(9)})
    with pytest.raises(ValueError, match="8192 characters"):
        validate_feature_configuration({"description": "x" * 8_193})
    with pytest.raises(ValueError, match="item limit"):
        validate_feature_configuration({"columns": list(range(257))})
    with pytest.raises(ValueError, match="node limit"):
        validate_feature_configuration({f"section{index}": list(range(8)) for index in range(256)})


def test_benign_feature_configuration_remains_available() -> None:
    value = {
        "description": "tenant-local form draft",
        "layout": {
            "columns": ["name", "status"],
            "filters": {"archived": False, "minimumScore": 0.75},
        },
    }
    assert validate_feature_configuration(value) == value
