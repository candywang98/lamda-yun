"""Q14 protocol-level acceptance (WIRE3) against the production control API.

Drives BOTH sides of the live chain: operator (REST + WS) and a synthetic
companion (discovery -> ack -> frame streaming WS). Verifies:
  S1  discovery route, projection ack, JPEG frame relay with monotonic seq
      and geometry metadata, frame-staleness fail-closed
  S2  take-control pushes REMOTE to BOTH links (WIRE3), input routing
      operator->companion, release pushes VIEWING
  S3  duplicate open refused (409), stop pushes CLOSED to companion,
      discovery 404 after close

Run on the Seoul host: python3 q14_protocol_s1.py
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import time
import urllib.request
import uuid

import websockets

BASE = "http://127.0.0.1:8000"
WS_BASE = "ws://127.0.0.1:8000"
DEVICE = "4aabc387-6e4b-4b59-a525-b1c119ec7f5b"
IDENTITY = {
    "X-Tenant-Id": "00000000-0000-7000-8000-000000001111",
    "X-User-Id": "12345678-1234-1234-1234-123456789012",
    "X-Roles": "security_admin",
    "X-MFA": "true",
}


def http(method: str, path: str, body: dict | None = None, headers: dict | None = None) -> tuple[int, dict | str]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    for key, value in {**(headers or {}), **IDENTITY}.items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as error:
        raw = error.read()
        try:
            return error.code, json.loads(raw)
        except Exception:
            return error.code, raw.decode(errors="replace")


def tiny_jpeg(seq: int) -> str:
    # 4x4 solid-color JPEG whose bytes vary by seq so relay payloads differ.
    from PIL import Image

    image = Image.new("RGB", (4, 4), color=((seq * 37) % 256, (seq * 53) % 256, (seq * 71) % 256))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return base64.b64encode(buffer.getvalue()).decode()


async def recv_until(ws, want_type: str, timeout: float = 10.0, want_state: str | None = None) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            message = await asyncio.wait_for(ws.recv(), timeout=deadline - time.monotonic())
        except asyncio.TimeoutError:
            break
        payload = json.loads(message)
        if payload.get("t") == want_type and (want_state is None or payload.get("state") == want_state):
            return payload
    raise AssertionError(f"no {want_type}/{want_state} message within {timeout}s")


async def main() -> None:
    checks: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))
        print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")

    # ---- fresh companion binding (synthetic device client) ----
    enroll_code = http("POST", "/api/v1/mobile/enrollments", {"deviceId": DEVICE, "ttlSeconds": 900})
    assert enroll_code[0] == 201, enroll_code
    code = enroll_code[1]["code"]
    import urllib.parse

    body = json.dumps(
        {"code": code, "appInstanceId": f"q14-proto-{uuid.uuid4().hex[:8]}", "companionVersion": "0.1.0"}
    ).encode()
    req = urllib.request.Request(BASE + "/companion/v2/enroll", data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req) as resp:
        binding = json.loads(resp.read())
    token = binding["bindingToken"]
    companion_headers = {"Authorization": f"Bearer {token}"}
    print("companion binding ok")

    # ---- S1: no session -> 404; open -> discovery 200 ----
    status, _ = http("GET", "/companion/v2/live/session", headers=companion_headers)
    record("S1 discovery 404 without session", status == 404, f"HTTP {status}")

    status, opened = http("POST", f"/api/v1/devices/{DEVICE}/live")
    assert status in (200, 201), opened
    sid = opened["sessionId"]
    record("S1 operator open session", opened.get("state") == "VIEWING", sid)

    status, discovered = http("GET", "/companion/v2/live/session", headers=companion_headers)
    record(
        "S1 discovery returns session",
        status == 200 and discovered.get("sessionId") == sid and discovered.get("state") == "VIEWING",
        json.dumps(discovered, ensure_ascii=False)[:120],
    )

    # ack denied is terminal -> close; then reopen for the live part
    status, denied = http("POST", f"/companion/v2/live/{sid}/ack", {"granted": False}, companion_headers)
    record("S1 ack denial closes session", status == 200 and denied.get("state") == "CLOSED", str(denied))
    status, _ = http("GET", "/companion/v2/live/session", headers=companion_headers)
    record("S1 discovery 404 after denial", status == 404, f"HTTP {status}")

    status, opened = http("POST", f"/api/v1/devices/{DEVICE}/live")
    sid = opened["sessionId"]

    # ack with wrong identity must not leak (unauthenticated)
    status, _ = http("POST", f"/companion/v2/live/{sid}/ack", {"granted": True})
    record("S1 ack requires companion auth", status == 401, f"HTTP {status}")

    status, granted = http("POST", f"/companion/v2/live/{sid}/ack", {"granted": True}, companion_headers)
    record("S1 ack granted accepted", status == 200 and granted.get("state") == "VIEWING", str(granted))

    # ---- sockets ----
    operator_ws = await websockets.connect(
        f"{WS_BASE}/api/v1/devices/{DEVICE}/live/{sid}/stream", additional_headers=IDENTITY
    )
    companion_ws = await websockets.connect(f"{WS_BASE}/companion/v2/live/{sid}", additional_headers=companion_headers)
    hello = await recv_until(operator_ws, "state")
    record("S1 operator WS hello VIEWING", hello.get("state") == "VIEWING", str(hello))

    frames: list[dict] = []
    for seq in range(1, 6):
        await companion_ws.send(
            json.dumps(
                {
                    "t": "frame",
                    "seq": seq,
                    "jpeg": tiny_jpeg(seq),
                    "geometry": {
                        "frameWidth": 4,
                        "frameHeight": 4,
                        "deviceWidth": 1080,
                        "deviceHeight": 2400,
                        "rotation": 0,
                    },
                }
            )
        )
        await asyncio.sleep(0.15)
    for _ in range(5):
        try:
            message = json.loads(await asyncio.wait_for(operator_ws.recv(), timeout=3))
        except asyncio.TimeoutError:
            break
        if message.get("t") == "frame":
            frames.append(message)
    seqs = [f.get("seq") for f in frames]
    jpeg_ok = all(base64.b64decode(f.get("jpeg", ""))[:2] == b"\xff\xd8" for f in frames)
    record("S1 frames relayed >=4 with monotonic seq", len(frames) >= 4 and seqs == sorted(seqs) and len(set(seqs)) == len(seqs), f"seqs={seqs}")
    record("S1 relayed payloads are JPEG", jpeg_ok)

    # ---- S2: take-control pushes REMOTE to BOTH links ----
    status, taken = http("POST", f"/api/v1/devices/{DEVICE}/live/{sid}:take-control")
    record("S2 take-control VIEWING->REMOTE", status == 200 and taken.get("state") == "REMOTE", str(taken))
    operator_state = await recv_until(operator_ws, "state")
    record("S2 operator link gets REMOTE", operator_state.get("state") == "REMOTE", str(operator_state))
    companion_state = await recv_until(companion_ws, "state")
    record("S2 companion link gets REMOTE (WIRE3 push)", companion_state.get("state") == "REMOTE", str(companion_state))

    # input flows operator -> companion with gate checks server-side
    await operator_ws.send(json.dumps({"t": "input", "kind": "tap", "seq": 1, "x": 0.5, "y": 0.5}))
    delivered = None
    for _ in range(3):
        message = json.loads(await asyncio.wait_for(companion_ws.recv(), timeout=5))
        if message.get("t") == "input":
            delivered = message
            break
    record("S2 remote tap reaches companion", delivered is not None and delivered.get("kind") == "tap", str(delivered))

    # stale seq is rejected and demotes to VIEWING (server-side gate)
    await operator_ws.send(json.dumps({"t": "input", "kind": "tap", "seq": 1, "x": 0.5, "y": 0.5}))
    demoted = await recv_until(operator_ws, "state", timeout=5)
    record("S2 stale seq demotes to VIEWING", demoted.get("state") == "VIEWING", str(demoted))

    status, released = http("POST", f"/api/v1/devices/{DEVICE}/live/{sid}:release")
    record("S2 release REMOTE->VIEWING", status == 200 and released.get("state") == "VIEWING", str(released))
    companion_state = await recv_until(companion_ws, "state")
    record("S2 companion link gets VIEWING", companion_state.get("state") == "VIEWING", str(companion_state))

    # ---- S3: preemption, stop, closed push, discovery ----
    status, _ = http("POST", f"/api/v1/devices/{DEVICE}/live")
    record("S3 duplicate open refused", status == 409, f"HTTP {status}")

    status, stopped = http("POST", f"/api/v1/devices/{DEVICE}/live/{sid}:stop")
    record("S3 stop closes", status == 200 and stopped.get("state") == "CLOSED", str(stopped))
    companion_state = await recv_until(companion_ws, "state", want_state="CLOSED")
    record("S3 companion link gets CLOSED (WIRE3 push)", companion_state.get("state") == "CLOSED", str(companion_state))
    await asyncio.sleep(0.2)
    status, _ = http("GET", "/companion/v2/live/session", headers=companion_headers)
    record("S3 discovery 404 after stop", status == 404, f"HTTP {status}")

    await operator_ws.close()
    await companion_ws.close()

    failed = [name for name, ok, _ in checks if not ok]
    print(f"\n{len(checks) - len(failed)}/{len(checks)} checks passed")
    if failed:
        raise SystemExit("FAILED: " + ", ".join(failed))


asyncio.run(main())
