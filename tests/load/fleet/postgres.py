"""Test-owned loopback PostgreSQL, with no ambient database URL support."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import tempfile
import uuid
from pathlib import Path
from types import TracebackType


class FleetPostgres:
    def __init__(self) -> None:
        self.root: Path | None = None
        self.port = 0
        self.name = f"fleet_{uuid.uuid4().hex}"
        self.tools: dict[str, str] = {}
        self.environment: dict[str, str] = {}

    @property
    def database_url(self) -> str:
        if self.root is None or not self.port:
            raise RuntimeError("Fleet PostgreSQL has not been started")
        return f"postgresql+asyncpg://fleettest@127.0.0.1:{self.port}/{self.name}"

    def _run(self, tool: str, *arguments: str) -> None:
        try:
            subprocess.run(  # noqa: S603 - discovered local PG tools and owned test paths
                [self.tools[tool], *arguments],
                check=True,
                capture_output=True,
                text=True,
                env=self.environment,
                timeout=30,
            )
        except subprocess.CalledProcessError as error:
            raise RuntimeError(
                f"Fleet PostgreSQL {tool} failed ({error.returncode}): "
                f"{error.stdout}\n{error.stderr}"
            ) from error

    def __enter__(self) -> FleetPostgres:
        for tool in ("initdb", "pg_ctl", "createdb"):
            path = shutil.which(tool)
            if path is None:
                raise RuntimeError(f"Fleet load requires local PostgreSQL binary on PATH: {tool}")
            self.tools[tool] = path
        self.environment = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("PG") and key not in {"DATABASE_URL", "CLOUDCTL_DATABASE_URL"}
        }
        self.environment.update(LC_ALL="C", LANG="C", LANGUAGE="C")
        self.root = Path(tempfile.mkdtemp(prefix="fleet-load-pg-"))
        try:
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                self.port = sock.getsockname()[1]
            data = str(self.root / "data")
            self._run("initdb", "-D", data, "-A", "trust", "-U", "fleettest")
            self._run(
                "pg_ctl",
                "-D",
                data,
                "-l",
                str(self.root / "server.log"),
                "-o",
                f"-h 127.0.0.1 -p {self.port} -c unix_socket_directories=''",
                "-w",
                "-t",
                "20",
                "start",
            )
            self._run(
                "createdb",
                "--no-password",
                "-h",
                "127.0.0.1",
                "-p",
                str(self.port),
                "-U",
                "fleettest",
                self.name,
            )
            return self
        except BaseException:
            self.close()
            raise

    def close(self) -> None:
        if self.root is None or not self.root.exists():
            return
        data = self.root / "data"
        if (data / "postmaster.pid").exists():
            self._run("pg_ctl", "-D", str(data), "-m", "immediate", "-w", "-t", "20", "stop")
        # Never remove a running cluster's data if stopping it failed.
        shutil.rmtree(self.root)

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
