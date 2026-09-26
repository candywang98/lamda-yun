from __future__ import annotations

import asyncio
import base64
import json
import re
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from xml.etree import ElementTree

from cloudctl_edge_protocol import edge_control_pb2 as pb

LAB_DEVICE_SERIAL = "b0644fb5"
_MAX_CAPTURE_BYTES = 180 * 1024
_MAX_LAYOUT_NODES = 2048
_BOUNDS = re.compile(r"^\[(\d+),(\d+)\]\[(\d+),(\d+)\]$")


class AdbDebugError(ValueError):
    pass


ProcessRunner = Callable[[Sequence[str]], Awaitable[bytes]]


class RestrictedAdbDebugDriver:
    """Lab-only ADB adapter with fixed serial and closed command templates."""

    def __init__(
        self,
        adb_path: Path,
        *,
        device_id: str,
        runner: ProcessRunner | None = None,
    ) -> None:
        if not adb_path.is_absolute():
            raise AdbDebugError("ADB path must be absolute")
        if not device_id.strip():
            raise AdbDebugError("lab ADB device ID must be explicit")
        self._adb_path = adb_path
        self._device_id = device_id
        self._runner = runner or self._run

    async def handle(self, frame: pb.DebugRelayFrame) -> pb.DebugRelayFrame:
        if frame.device_id != self._device_id:
            raise AdbDebugError("debug frame is not bound to the configured lab device")
        try:
            payload = json.loads(frame.payload.decode("utf-8")) if frame.payload else {}
        except (UnicodeDecodeError, ValueError) as exc:
            raise AdbDebugError("debug payload must be a JSON object") from exc
        if not isinstance(payload, dict):
            raise AdbDebugError("debug payload must be a JSON object")

        if frame.capability == "input.tap" and frame.kind == "tap":
            if set(payload) != {"x", "y"}:
                raise AdbDebugError("tap accepts only integer x and y")
            x, y = payload["x"], payload["y"]
            if (
                isinstance(x, bool)
                or isinstance(y, bool)
                or not isinstance(x, int)
                or not isinstance(y, int)
            ):
                raise AdbDebugError("tap coordinates must be integers")
            if not 0 <= x <= 10000 or not 0 <= y <= 10000:
                raise AdbDebugError("tap coordinates are outside the allowed range")
            await self._runner(self._argv("shell", "input", "tap", str(x), str(y)))
            response: dict[str, object] = {"state": "SUCCEEDED"}
            response_kind = "debug.ack"
            response_capability = "debug.ack"
        elif frame.capability == "view.frame" and frame.kind == "frame":
            if payload:
                raise AdbDebugError("screenshot does not accept caller parameters")
            content = await self._runner(self._argv("exec-out", "screencap", "-p"))
            self._validate_capture(content)
            response = {
                "encoding": "base64",
                "mediaType": "image/png",
                "data": base64.b64encode(content).decode("ascii"),
            }
            response_kind = frame.kind
            response_capability = frame.capability
        elif frame.capability == "view.layout" and frame.kind == "layout":
            if payload:
                raise AdbDebugError("UI tree does not accept caller parameters")
            content = await self._runner(self._argv("exec-out", "uiautomator", "dump", "/dev/tty"))
            self._validate_capture(content)
            response = {"nodes": self._parse_layout(content)}
            response_kind = frame.kind
            response_capability = frame.capability
        else:
            raise AdbDebugError("debug operation is not allowlisted by the lab ADB driver")

        return pb.DebugRelayFrame(
            session_id=frame.session_id,
            device_id=frame.device_id,
            request_id=frame.request_id,
            kind=response_kind,
            capability=response_capability,
            payload=json.dumps(response, separators=(",", ":")).encode("utf-8"),
        )

    def _argv(self, *arguments: str) -> tuple[str, ...]:
        return (str(self._adb_path), "-s", LAB_DEVICE_SERIAL, *arguments)

    @staticmethod
    def _validate_capture(content: bytes) -> None:
        if not content:
            raise AdbDebugError("ADB capture returned no data")
        if len(content) > _MAX_CAPTURE_BYTES:
            raise AdbDebugError("ADB capture exceeds the relay response limit")

    @staticmethod
    def _parse_layout(content: bytes) -> list[dict[str, object]]:
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise AdbDebugError("ADB UI tree is not valid UTF-8") from exc
        start = text.find("<?xml")
        if start < 0:
            start = text.find("<hierarchy")
        if start < 0:
            raise AdbDebugError("ADB UI tree does not contain XML")
        end = text.find("</hierarchy>", start)
        if end < 0:
            raise AdbDebugError("ADB UI tree XML is incomplete")
        xml = text[start : end + len("</hierarchy>")]
        if "<!DOCTYPE" in xml.upper() or "<!ENTITY" in xml.upper():
            raise AdbDebugError("ADB UI tree contains prohibited XML declarations")
        try:
            # Android uiautomator emits a small, local document. Input is byte-bounded
            # above and declarations/entities are rejected before this non-network parser.
            root = ElementTree.fromstring(xml)  # noqa: S314
        except ElementTree.ParseError as exc:
            raise AdbDebugError("ADB UI tree XML is invalid") from exc

        nodes: list[dict[str, object]] = []

        def visit(element: ElementTree.Element, depth: int) -> None:
            if len(nodes) >= _MAX_LAYOUT_NODES:
                raise AdbDebugError("ADB UI tree exceeds the node limit")
            child_depth = depth
            if element.tag == "node":
                bounds = element.attrib.get("bounds", "")
                match = _BOUNDS.fullmatch(bounds)
                if match is None:
                    raise AdbDebugError("ADB UI tree contains invalid bounds")
                index = len(nodes)
                node: dict[str, object] = {
                    "id": element.attrib.get("resource-id") or f"node-{index}",
                    "className": element.attrib.get("class", "android.view.View"),
                    "bounds": bounds,
                    "depth": depth,
                    "clickable": element.attrib.get("clickable") == "true",
                    "centerX": (int(match[1]) + int(match[3])) // 2,
                    "centerY": (int(match[2]) + int(match[4])) // 2,
                }
                for source, target in (
                    ("resource-id", "resourceId"),
                    ("text", "text"),
                    ("content-desc", "description"),
                ):
                    value = element.attrib.get(source)
                    if value:
                        node[target] = value[:500]
                nodes.append(node)
                child_depth = depth + 1
            for child in element:
                visit(child, child_depth)

        visit(root, 0)
        return nodes

    @staticmethod
    async def _run(argv: Sequence[str]) -> bytes:
        process = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            detail = stderr.decode("utf-8", errors="replace").strip()[:300]
            raise AdbDebugError(f"fixed ADB operation failed: {detail or 'unknown error'}")
        return stdout
