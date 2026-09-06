from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "write-delivery-checksums.py"


def load_checksum_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("write_delivery_checksums", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_checksum_index_is_sorted_deterministic_and_explicit(tmp_path: Path) -> None:
    module = load_checksum_module()
    delivery = tmp_path / "delivery"
    delivery.mkdir()
    alpha = delivery / "alpha.txt"
    nested = delivery / "nested" / "zeta.zip"
    nested.parent.mkdir()
    alpha.write_text("alpha\n", encoding="utf-8")
    nested.write_bytes(b"zeta\n")
    ignored = delivery / "android-sdk.zip"
    ignored.write_bytes(b"must not enter final checksums\n")
    output = delivery / "SHA256SUMS.txt"

    first = module.write_checksums(delivery, output, [nested, alpha])
    second = module.write_checksums(
        delivery,
        output,
        [Path("nested/zeta.zip"), Path("alpha.txt")],
    )

    assert second == first
    assert output.read_text(encoding="ascii") == "".join(first)
    assert first == [
        f"{hashlib.sha256(alpha.read_bytes()).hexdigest()}  alpha.txt\n",
        f"{hashlib.sha256(nested.read_bytes()).hexdigest()}  nested/zeta.zip\n",
    ]
    assert "android-sdk.zip" not in output.read_text(encoding="ascii")


@pytest.mark.parametrize("name", ["missing.txt", "SHA256SUMS.txt"])
def test_checksum_index_rejects_missing_files_and_itself(tmp_path: Path, name: str) -> None:
    module = load_checksum_module()
    delivery = tmp_path / "delivery"
    delivery.mkdir()
    output = delivery / "SHA256SUMS.txt"
    if name == output.name:
        output.write_text("old\n", encoding="ascii")

    with pytest.raises(ValueError, match="regular file|cannot checksum itself"):
        module.write_checksums(delivery, output, [Path(name)])


def test_checksum_index_rejects_duplicates_and_outside_paths(tmp_path: Path) -> None:
    module = load_checksum_module()
    delivery = tmp_path / "delivery"
    delivery.mkdir()
    artifact = delivery / "source.zip"
    artifact.write_bytes(b"source\n")
    output = delivery / "SHA256SUMS.txt"

    with pytest.raises(ValueError, match="duplicate delivery artifact"):
        module.write_checksums(delivery, output, [artifact, Path("source.zip")])
    with pytest.raises(ValueError, match="must stay inside delivery directory"):
        module.write_checksums(delivery, output, [tmp_path / "outside.zip"])


def test_checksum_index_rejects_symbolic_links(tmp_path: Path) -> None:
    module = load_checksum_module()
    delivery = tmp_path / "delivery"
    delivery.mkdir()
    artifact = delivery / "source.zip"
    artifact.write_bytes(b"source\n")
    link = delivery / "source-link.zip"
    try:
        link.symlink_to(artifact)
    except OSError:
        pytest.skip("symbolic links are unavailable")

    with pytest.raises(ValueError, match="cannot be a symbolic link"):
        module.write_checksums(delivery, delivery / "SHA256SUMS.txt", [link])
