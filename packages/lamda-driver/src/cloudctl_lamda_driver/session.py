from __future__ import annotations

import threading
from pathlib import Path
from types import TracebackType
from typing import Protocol

from .adapter import LamdaSdkBackend
from .driver import LamdaDriver
from .errors import DeviceDriverError, DriverErrorCode, map_exception


class FencingVerifier(Protocol):
    def verify(self, *, device_id: str, lease_id: str, fencing_token: int) -> None: ...


class SessionBackend(Protocol):
    def acquire_lock(self, lease_seconds: int) -> None: ...
    def refresh_lock(self, lease_seconds: int) -> None: ...
    def release_lock(self) -> None: ...
    def close(self) -> None: ...
    def identity(self) -> str: ...


class BackendFactory(Protocol):
    def __call__(self, *, host: str, port: int, certificate_path: Path) -> SessionBackend: ...


class LamdaSession:
    LOCK_SECONDS = 60
    REFRESH_SECONDS = 20

    def __init__(
        self,
        *,
        device_id: str,
        host: str,
        certificate_path: Path,
        lease_id: str,
        fencing_token: int,
        fencing_verifier: FencingVerifier,
        backend_factory: BackendFactory = LamdaSdkBackend.connect,
        port: int = 65000,
    ):
        self._device_id = device_id
        self._host = host
        self._port = port
        self._certificate_path = certificate_path
        self._lease_id = lease_id
        self._fencing_token = fencing_token
        self._fencing_verifier = fencing_verifier
        self._backend_factory = backend_factory
        self._backend: SessionBackend | None = None
        self._stop = threading.Event()
        self._refresh_thread: threading.Thread | None = None
        self._refresh_error: DeviceDriverError | None = None

    def __enter__(self) -> LamdaDriver:
        self._verify_fence()
        if self._port != 65000:
            raise DeviceDriverError(
                DriverErrorCode.CAPABILITY_DENIED,
                "LAMDA service port differs from the approved device profile",
                retryable=False,
            )
        if not self._certificate_path.is_file():
            raise DeviceDriverError(
                DriverErrorCode.CERTIFICATE_REJECTED,
                "device service certificate is unavailable",
                retryable=False,
            )
        try:
            self._backend = self._backend_factory(
                host=self._host, port=self._port, certificate_path=self._certificate_path
            )
            self._backend.acquire_lock(self.LOCK_SECONDS)
            if self._backend.identity() != self._device_id:
                raise DeviceDriverError(
                    DriverErrorCode.IDENTITY_MISMATCH,
                    "connected LAMDA identity does not match the leased device",
                    retryable=False,
                )
        except Exception as exc:
            if self._backend is not None:
                try:
                    self._backend.release_lock()
                except Exception as release_error:
                    self._refresh_error = map_exception(release_error)
            self._close_backend()
            raise map_exception(exc) from exc
        self._refresh_thread = threading.Thread(
            target=self._refresh_loop,
            name=f"lamda-lock:{self._device_id}",
            daemon=True,
        )
        self._refresh_thread.start()
        return LamdaDriver(self._backend, self._operation_guard)

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._stop.set()
        if self._refresh_thread is not None:
            self._refresh_thread.join(timeout=self.REFRESH_SECONDS + 1)
        if self._backend is not None:
            try:
                self._backend.release_lock()
            except Exception as release_error:
                self._refresh_error = map_exception(release_error)
            finally:
                self._close_backend()

    def _operation_guard(self) -> None:
        if self._refresh_error is not None:
            raise self._refresh_error
        self._verify_fence()

    def _verify_fence(self) -> None:
        try:
            self._fencing_verifier.verify(
                device_id=self._device_id,
                lease_id=self._lease_id,
                fencing_token=self._fencing_token,
            )
        except Exception as exc:
            raise DeviceDriverError(
                DriverErrorCode.STALE_FENCE,
                "device lease or fencing token is no longer current",
                retryable=False,
            ) from exc

    def _refresh_loop(self) -> None:
        while not self._stop.wait(self.REFRESH_SECONDS):
            try:
                self._verify_fence()
                backend = self._backend
                if backend is None:
                    raise RuntimeError("LAMDA backend closed before lock refresh")
                backend.refresh_lock(self.LOCK_SECONDS)
            except Exception:
                self._refresh_error = DeviceDriverError(
                    DriverErrorCode.LOCK_LOST,
                    "LAMDA API lock refresh failed",
                    retryable=False,
                )
                self._stop.set()
                return

    def _close_backend(self) -> None:
        if self._backend is not None:
            try:
                self._backend.close()
            finally:
                self._backend = None
