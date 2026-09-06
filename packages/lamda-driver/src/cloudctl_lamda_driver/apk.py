from __future__ import annotations

import hashlib
import time
from collections.abc import Callable, Mapping, Sequence
from typing import BinaryIO, Protocol

from .errors import DeviceDriverError, DriverErrorCode, map_exception
from .protocols import ApkPart, InstallOptions, InstallResult


class ApkBackend(Protocol):
    def create_install_session(self, options: Mapping[str, object]) -> str: ...
    def write_install_part(
        self,
        session_id: str,
        split_name: str | None,
        source: BinaryIO,
        size: int,
        sha256: str,
    ) -> None: ...
    def commit_install_session(self, session_id: str) -> None: ...
    def install_session_state(self, session_id: str) -> Mapping[str, object]: ...
    def installed_app(self, package_name: str) -> Mapping[str, object]: ...


class ApkSessionInstaller:
    TERMINAL = frozenset({"SUCCEEDED", "FAILED", "CANCELED"})

    def __init__(self, backend: ApkBackend, guard: Callable[[], None]):
        self._backend = backend
        self._guard = guard

    def install(
        self,
        artifacts: Sequence[ApkPart],
        options: InstallOptions,
        *,
        timeout_seconds: float = 180,
    ) -> InstallResult:
        self._guard()
        if not artifacts:
            raise DeviceDriverError(
                DriverErrorCode.APK_POLICY_REJECTED, "APK session has no parts", retryable=False
            )
        for part in artifacts:
            self._verify_part(part)
        session_id = self._backend.create_install_session(
            {
                "package_name": options.package_name,
                "allow_downgrade": options.allow_downgrade,
                "user_confirmation_allowed": options.user_confirmation_allowed,
            }
        )
        for part in artifacts:
            self._guard()
            with part.path.open("rb") as source:
                self._backend.write_install_part(
                    session_id,
                    part.split_name,
                    source,
                    part.size,
                    part.sha256.lower(),
                )

        # Commit has exactly one attempt. An exception after submission requires reconciliation.
        self._guard()
        try:
            self._backend.commit_install_session(session_id)
        except Exception as exc:
            raise DeviceDriverError(
                DriverErrorCode.APK_COMMIT_UNKNOWN,
                "APK commit outcome is unknown and must be reconciled",
                retryable=False,
                reconcile_required=True,
            ) from exc

        deadline = time.monotonic() + timeout_seconds
        state: Mapping[str, object] = {}
        while time.monotonic() < deadline:
            self._guard()
            try:
                state = self._backend.install_session_state(session_id)
            except Exception as exc:
                raise map_exception(exc) from exc
            if str(state.get("state")) in self.TERMINAL:
                break
            time.sleep(0.25)
        if str(state.get("state")) != "SUCCEEDED":
            raise DeviceDriverError(
                DriverErrorCode.APK_INSTALL_FAILED,
                f"APK install session ended in {state.get('state', 'TIMEOUT')}",
                retryable=False,
            )
        installed = self._backend.installed_app(options.package_name)
        if str(installed.get("signer_sha256", "")).lower() != options.signer_sha256.lower():
            raise DeviceDriverError(
                DriverErrorCode.APK_POLICY_REJECTED,
                "installed APK signer does not match the approved artifact",
                retryable=False,
            )
        raw_version_code = installed.get("version_code", -1)
        try:
            installed_version_code = (
                int(raw_version_code)
                if isinstance(raw_version_code, int | str)
                and not isinstance(raw_version_code, bool)
                else -1
            )
        except ValueError:
            installed_version_code = -1
        if installed_version_code != options.version_code:
            raise DeviceDriverError(
                DriverErrorCode.APK_INSTALL_FAILED,
                "installed APK version does not match the rollout",
                retryable=False,
            )
        return InstallResult(
            package_name=options.package_name,
            version_name=str(installed.get("version_name", options.version_name)),
            version_code=options.version_code,
            state="SUCCEEDED",
            session_id=session_id,
        )

    @staticmethod
    def _verify_part(part: ApkPart) -> None:
        if not part.path.is_file() or part.path.stat().st_size != part.size:
            raise DeviceDriverError(
                DriverErrorCode.APK_POLICY_REJECTED,
                "APK part is missing or has an unexpected size",
                retryable=False,
            )
        digest = hashlib.sha256()
        with part.path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
        if digest.hexdigest() != part.sha256.lower():
            raise DeviceDriverError(
                DriverErrorCode.APK_POLICY_REJECTED,
                "APK part SHA256 does not match the approved artifact",
                retryable=False,
            )
