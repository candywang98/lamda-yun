#!/usr/bin/env python3
"""Atomically write a deterministic checksum index for explicit delivery artifacts."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path


def _is_inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def checksum_lines(directory: Path, output: Path, artifacts: list[Path]) -> list[str]:
    directory = directory.resolve()
    output = output.resolve()
    if not directory.is_dir():
        raise ValueError(f"delivery directory does not exist: {directory}")
    if not _is_inside(output, directory):
        raise ValueError(f"checksum output must stay inside delivery directory: {output}")
    if not artifacts:
        raise ValueError("at least one delivery artifact is required")

    indexed: dict[str, Path] = {}
    for raw_path in artifacts:
        candidate = raw_path if raw_path.is_absolute() else directory / raw_path
        if candidate.is_symlink():
            raise ValueError(f"delivery artifact cannot be a symbolic link: {candidate}")
        path = candidate.resolve()
        if not _is_inside(path, directory):
            raise ValueError(f"delivery artifact must stay inside delivery directory: {raw_path}")
        if path == output:
            raise ValueError("checksum output cannot checksum itself")
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"delivery artifact is not a regular file: {path}")
        relative = path.relative_to(directory).as_posix()
        if relative in indexed:
            raise ValueError(f"duplicate delivery artifact: {relative}")
        indexed[relative] = path

    return [
        f"{hashlib.sha256(indexed[relative].read_bytes()).hexdigest()}  {relative}\n"
        for relative in sorted(indexed)
    ]


def write_checksums(directory: Path, output: Path, artifacts: list[Path]) -> list[str]:
    if output.is_symlink():
        raise ValueError(f"checksum output cannot be a symbolic link: {output}")
    lines = checksum_lines(directory, output, artifacts)
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.next")
    try:
        temporary.write_text("".join(lines), encoding="ascii", newline="\n")
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    return lines


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("SHA256SUMS.txt"))
    parser.add_argument("artifacts", nargs="+", type=Path)
    args = parser.parse_args()

    directory = args.directory.resolve()
    output = args.output if args.output.is_absolute() else directory / args.output
    lines = write_checksums(directory, output, args.artifacts)
    print(f"artifacts={len(lines)}")
    print(f"checksum_index={output.resolve()}")


if __name__ == "__main__":
    main()
