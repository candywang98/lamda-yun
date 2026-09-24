#!/usr/bin/env python3
"""Local DEVICE:<serial> acceptance lock, separate from production device_lease.

The SQLite database lives in the Git common directory so every worktree of this
repository shares one lock table. It is not PostgreSQL ``device_lease`` and does
not prove a production lease is free. Creating this tool cannot prove that no
other session already holds a device; an empty database is a bootstrap state,
not a verified idle device.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import stat
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

EXIT_OK = 0
EXIT_CONFLICT = 3
EXIT_OWNERSHIP = 4
EXIT_USAGE = 5

MIN_TTL_SECONDS = 60
MAX_TTL_SECONDS = 8 * 60 * 60
DEFAULT_TTL_SECONDS = 30 * 60
SCHEMA_VERSION = 1
BUSY_TIMEOUT_MS = 15_000
# Bounded retries only for the cold-create window, where two processes can both
# observe "no database" and one then hits "database is locked" outside
# busy_timeout. A database that already exists does not use this loop: a real
# lock error there is a store failure (exit 5), not a device conflict.
INIT_LOCK_ATTEMPTS = 8
TOKEN_ENV = "CLOUDCTL_DEVICE_LOCK_TOKEN"  # noqa: S105 - env var name, not a secret
DB_ENV = "CLOUDCTL_DEVICE_LOCK_DB"
SERIAL_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._:-")
SECRET_KEYS = frozenset(
    {"owner_token", "owner_token_sha256", "token", "token_hash", "secret"}
)
# fstype tokens that must never hold the lock file. Matched against the
# classified type (Darwin mount type or Linux `stat -f -c %T` / `findmnt`).
NETWORK_FSTYPES = frozenset(
    {
        "nfs",
        "nfs4",
        "smb",
        "smbfs",
        "cifs",
        "sshfs",
        "fuse.sshfs",
        "afp",
        "afpfs",
        "fuse.afp",
        "9p",
        "fuse.9p",
        "fuse.rclone",
        "webdav",
        "vboxsf",
    }
)
# Types we will accept when classification succeeds. Anything else that we
# successfully classified is refused (fail closed), including unknown FUSE.
LOCAL_FSTYPES = frozenset(
    {
        "apfs",
        "hfs",
        "ext2",
        "ext3",
        "ext4",
        "xfs",
        "btrfs",
        "zfs",
        "f2fs",
        "bcachefs",
        "tmpfs",
        "devtmpfs",
        "ramfs",
        "overlay",
        "fuse.overlayfs",
    }
)


class LockError(Exception):
    """Expected lock outcome. ``code`` is the process exit status."""

    def __init__(self, message: str, code: int = EXIT_CONFLICT, **details: Any) -> None:
        super().__init__(message)
        self.code = code
        self.details = details


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def hashes_equal(stored: str, presented: str) -> bool:
    if len(stored) != len(presented):
        return False
    return hmac.compare_digest(stored, presented)


def public_view(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key not in SECRET_KEYS}


def validate_serial(serial: str) -> str:
    if not isinstance(serial, str) or not serial or len(serial) > 128:
        raise LockError("serial must be 1..128 characters", EXIT_USAGE)
    if any(character not in SERIAL_CHARS for character in serial):
        raise LockError("serial contains unsupported characters", EXIT_USAGE)
    if serial in {".", ".."} or ".." in serial.split(":"):
        raise LockError("serial must be an exact device serial, not a path", EXIT_USAGE)
    return serial


def validate_identity(value: str, field: str) -> str:
    text = value.strip()
    if not text or len(text) > 200:
        raise LockError(f"{field} must be 1..200 non-blank characters", EXIT_USAGE)
    if any(ord(character) < 32 for character in text):
        raise LockError(f"{field} must not contain control characters", EXIT_USAGE)
    return text


def validate_reason(value: str) -> str:
    text = validate_identity(value, "reason")
    if len(text) < 8:
        raise LockError("reason must be at least 8 characters", EXIT_USAGE)
    return text


def validate_ttl(seconds: int) -> int:
    if not isinstance(seconds, int) or isinstance(seconds, bool):
        raise LockError("ttl must be an integer number of seconds", EXIT_USAGE)
    if seconds < MIN_TTL_SECONDS or seconds > MAX_TTL_SECONDS:
        raise LockError(
            f"ttl must be {MIN_TTL_SECONDS}..{MAX_TTL_SECONDS} seconds",
            EXIT_USAGE,
        )
    return seconds


def validate_fencing(token: int) -> int:
    if not isinstance(token, int) or isinstance(token, bool) or token < 1:
        raise LockError("fencing token must be a positive integer", EXIT_USAGE)
    return token


def _git_common_dir(start: Path) -> Path:
    try:
        completed = subprocess.run(  # noqa: S603 - fixed git argv, not a shell
            ["git", "-C", str(start), "rev-parse", "--path-format=absolute", "--git-common-dir"],  # noqa: S607
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise LockError(f"git common-dir lookup failed: {exc}", EXIT_USAGE) from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "git rev-parse failed").strip()
        raise LockError(f"git common-dir lookup failed: {detail}", EXIT_USAGE)
    common = Path(completed.stdout.strip())
    if not common.is_absolute():
        raise LockError("git common-dir was not absolute", EXIT_USAGE)
    return common


def resolve_database_path(explicit: Path | None = None, *, start: Path | None = None) -> Path:
    """Return the shared lock path without creating it."""
    if explicit is not None:
        return explicit.expanduser()
    override = os.environ.get(DB_ENV)
    if override:
        return Path(override).expanduser()
    anchor = start or Path(__file__).resolve().parent
    return _git_common_dir(anchor) / "cloudctl-device-locks.sqlite3"


def _refuse_symlink(path: Path) -> None:
    if path.is_symlink():
        raise LockError(f"refusing symlink: {path}", EXIT_USAGE)


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.lstat().st_mode)


def _tighten_file(path: Path) -> None:
    _refuse_symlink(path)
    if not path.is_file():
        raise LockError(f"lock database is not a regular file: {path}", EXIT_USAGE)
    current = _mode(path)
    if current & 0o077:
        path.chmod(0o600)


def _prepare_parent(parent: Path) -> None:
    parent.mkdir(parents=True, exist_ok=True)
    # Refuse a symlink at the database's own parent (the directory we chmod).
    # Do not walk ancestors: macOS /tmp is a symlink to /private/tmp, and
    # treating that as hostile rejects every temp and some legitimate paths.
    if parent.is_symlink():
        raise LockError(f"refusing symlink database directory: {parent}", EXIT_USAGE)
    if not parent.is_dir():
        raise LockError(f"database parent is not a directory: {parent}", EXIT_USAGE)
    # Best effort. A sticky system directory such as /private/tmp cannot be
    # chmod'd by the user; that must not block a test database there. The
    # database file itself is still forced to 0600.
    try:
        parent.chmod(_mode(parent) & ~0o022 | 0o700)
    except OSError:
        return


def _run_fixed(argv: list[str]) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(  # noqa: S603 - fixed classification argv, not a shell
            argv,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def fstype_from_darwin_mount(device_name: str, mount_text: str) -> str | None:
    """Pick the type for ``/dev/<device>`` only when exactly one mount matches."""
    if not device_name or any(character.isspace() for character in device_name):
        return None
    if "/" in device_name or device_name in {".", ".."}:
        return None
    prefix = f"/dev/{device_name} on "
    matches: list[str] = []
    for line in mount_text.splitlines():
        if not line.startswith(prefix):
            continue
        open_paren = line.rfind("(")
        close_paren = line.rfind(")")
        if open_paren < 0 or close_paren < open_paren:
            return None
        fstype = line[open_paren + 1 : close_paren].split(",", 1)[0].strip().lower()
        if not fstype:
            return None
        matches.append(fstype)
    if len(matches) != 1:
        return None
    return matches[0]


def _darwin_fstype(probe: Path) -> str | None:
    """Return the mount type from `mount`, or None when it cannot be proven.

    macOS `df -T` filters by type and prints nothing, so it is not a classifier.
    `stat` has no fstype field. Device id plus the mount table is the check.
    """
    device = _run_fixed(["stat", "-f", "%Sd", str(probe)])
    if device is None or device.returncode != 0:
        return None
    mounted = _run_fixed(["mount"])
    if mounted is None or mounted.returncode != 0:
        return None
    return fstype_from_darwin_mount(device.stdout.strip(), mounted.stdout)


def _linux_fstype(probe: Path) -> str | None:
    """Return the Linux fstype, or None when every classifier fails."""
    stat_type = _run_fixed(["stat", "-f", "-c", "%T", str(probe)])
    if stat_type is not None and stat_type.returncode == 0:
        fstype = stat_type.stdout.strip().lower()
        if fstype and fstype != "unknown" and not any(ch.isspace() for ch in fstype):
            return fstype
    findmnt = _run_fixed(["findmnt", "-n", "-o", "FSTYPE", "-T", str(probe)])
    if findmnt is not None and findmnt.returncode == 0:
        fstype = findmnt.stdout.strip().splitlines()
        if len(fstype) == 1 and fstype[0] and not any(ch.isspace() for ch in fstype[0]):
            return fstype[0].lower()
    # GNU df: `df -T` prints a Type column. BSD df -T is a filter and is not used.
    listed = _run_fixed(["df", "-P", "-T", str(probe)])
    if listed is None or listed.returncode != 0:
        return None
    rows = [line.split() for line in listed.stdout.splitlines() if line.strip()]
    if len(rows) != 2 or len(rows[1]) < 2:
        return None
    header = [cell.lower() for cell in rows[0]]
    if "type" not in header:
        return None
    fstype = rows[1][header.index("type")].lower()
    if not fstype or any(character.isspace() for character in fstype):
        return None
    return fstype


def classify_fstype(path: Path) -> str | None:
    """Classify ``path``. ``None`` means the platform could not prove a type."""
    probe = path if path.exists() else path.parent
    if sys.platform == "darwin":
        return _darwin_fstype(probe)
    if sys.platform.startswith("linux"):
        return _linux_fstype(probe)
    return None


def _assert_local_file(path: Path) -> None:
    """Reject non-local or unclassified database locations.

    Fail closed: a path that cannot be classified, or whose type is not on the
    local allow-list, is refused. macOS APFS/HFS and common Linux local types
    pass. NFS/SMB/CIFS/SSHFS/AFP and other networked types are refused by name
    even if a future allow-list edit overlaps them.
    """
    _refuse_symlink(path)
    probe = path if path.exists() else path.parent
    _refuse_symlink(probe)
    fstype = classify_fstype(probe)
    if fstype is None:
        raise LockError(
            "refusing lock database because its filesystem type could not be classified",
            EXIT_USAGE,
        )
    if fstype in NETWORK_FSTYPES or fstype.startswith("nfs"):
        raise LockError(
            f"refusing networked filesystem {fstype} for the lock database",
            EXIT_USAGE,
        )
    if fstype not in LOCAL_FSTYPES:
        raise LockError(
            f"refusing filesystem {fstype} for the lock database",
            EXIT_USAGE,
        )


class DeviceLockStore:
    def __init__(self, database: Path) -> None:
        self.database = database

    def _connect(self, *, write: bool) -> sqlite3.Connection:
        if write:
            _prepare_parent(self.database.parent)
            _assert_local_file(self.database.parent)
        elif not self.database.exists():
            raise LockError("lock database does not exist", EXIT_USAGE)
        if self.database.exists() or self.database.is_symlink():
            _refuse_symlink(self.database)
            _assert_local_file(self.database)
        if write and self.database.exists():
            _tighten_file(self.database)
        if write:
            return self._connect_writer()
        return self._connect_reader()

    def _connect_reader(self) -> sqlite3.Connection:
        # mode=ro plus query_only. Do not add immutable=1: that flag ignores a
        # WAL that another connection has committed but not checkpointed, so
        # status would report a stale holder or FREE. DELETE journal mode has
        # no WAL; a committed row is in the main file before the writer closes.
        uri = f"{self.database.resolve().as_uri()}?mode=ro"
        connection = sqlite3.connect(
            uri,
            uri=True,
            timeout=BUSY_TIMEOUT_MS / 1000,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
        connection.execute("PRAGMA query_only = ON")
        return connection

    def _connect_writer(self) -> sqlite3.Connection:
        # Retry only while the file is still absent. Once it exists, lock errors
        # propagate as sqlite3.Error and main() exits 5.
        for attempt in range(INIT_LOCK_ATTEMPTS):
            existed = self.database.exists()
            connection = sqlite3.connect(
                self.database,
                timeout=BUSY_TIMEOUT_MS / 1000,
                isolation_level=None,
            )
            connection.row_factory = sqlite3.Row
            try:
                connection.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
                self._ensure_delete_journal(connection)
                connection.execute("PRAGMA synchronous = FULL")
                _tighten_file(self.database)
                self._refuse_journal_symlink()
                self._ensure_schema(connection)
                return connection
            except sqlite3.OperationalError as exc:
                self._rollback_quietly(connection)
                connection.close()
                if existed or not self._is_lock_contention(exc):
                    raise
                if attempt + 1 >= INIT_LOCK_ATTEMPTS:
                    raise
                time.sleep(min(0.02 * (attempt + 1), 0.1))
            except Exception:
                self._rollback_quietly(connection)
                connection.close()
                raise
        raise AssertionError("init retry loop exited without returning or raising")

    @staticmethod
    def _rollback_quietly(connection: sqlite3.Connection) -> None:
        try:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
        except sqlite3.Error:
            return

    @staticmethod
    def _is_lock_contention(exc: sqlite3.OperationalError) -> bool:
        message = str(exc).lower()
        return "locked" in message or "busy" in message

    def _ensure_delete_journal(self, connection: sqlite3.Connection) -> None:
        """Force the rollback journal. WAL is not used.

        ``immutable=1`` readers skip an uncheckpointed WAL, which reports a
        committed holder as the previous one. DELETE mode writes the commit
        into the main database before the writer returns, so a ``mode=ro``
        reader sees it while that writer is still connected.
        """
        current = connection.execute("PRAGMA journal_mode").fetchone()
        if current is not None and str(current[0]).lower() == "delete":
            return
        switched = connection.execute("PRAGMA journal_mode = DELETE").fetchone()
        if switched is None or str(switched[0]).lower() != "delete":
            raise sqlite3.OperationalError(
                "journal_mode stayed "
                f"{None if switched is None else switched[0]}; refusing WAL"
            )

    def _refuse_journal_symlink(self) -> None:
        journal = Path(str(self.database) + "-journal")
        if journal.is_symlink():
            raise LockError(f"refusing symlink: {journal}", EXIT_USAGE)

    def _ensure_schema(self, connection: sqlite3.Connection) -> None:
        # executescript() commits first, so DDL stays on this IMMEDIATE transaction.
        connection.execute("BEGIN IMMEDIATE")
        try:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_meta ("
                "key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS locks ("
                "serial TEXT PRIMARY KEY, holder TEXT NOT NULL, purpose TEXT NOT NULL, "
                "task_id TEXT, token_hash TEXT NOT NULL, fencing INTEGER NOT NULL, "
                "acquired_at TEXT NOT NULL, renewed_at TEXT NOT NULL, expires_at TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS fencing_counter ("
                "serial TEXT PRIMARY KEY, next_fencing INTEGER NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS audit ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, serial TEXT NOT NULL, "
                "action TEXT NOT NULL, actor TEXT NOT NULL, fencing INTEGER, "
                "at TEXT NOT NULL, detail TEXT NOT NULL)"
            )
            row = connection.execute(
                "SELECT value FROM schema_meta WHERE key = 'version'"
            ).fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO schema_meta(key, value) VALUES ('version', ?)",
                    (str(SCHEMA_VERSION),),
                )
            elif int(row["value"]) != SCHEMA_VERSION:
                raise LockError(
                    f"unsupported lock schema version {row['value']}",
                    EXIT_USAGE,
                )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise

    def _row(self, connection: sqlite3.Connection, serial: str) -> sqlite3.Row | None:
        return connection.execute(
            "SELECT serial, holder, purpose, task_id, token_hash, fencing, "
            "acquired_at, renewed_at, expires_at FROM locks WHERE serial = ?",
            (serial,),
        ).fetchone()

    def _describe(self, row: sqlite3.Row | None, now: datetime) -> dict[str, Any]:
        if row is None:
            return {"state": "FREE"}
        expires = parse_iso(str(row["expires_at"]))
        state = "HELD" if expires > now else "STALE"
        return {
            "state": state,
            "serial": row["serial"],
            "holder": row["holder"],
            "purpose": row["purpose"],
            "task_id": row["task_id"],
            "fencing": row["fencing"],
            "acquired_at": row["acquired_at"],
            "renewed_at": row["renewed_at"],
            "expires_at": row["expires_at"],
        }

    def _audit(
        self,
        connection: sqlite3.Connection,
        *,
        serial: str,
        action: str,
        actor: str,
        fencing: int | None,
        at: datetime,
        detail: dict[str, Any],
    ) -> None:
        safe = public_view(detail)
        connection.execute(
            "INSERT INTO audit(serial, action, actor, fencing, at, detail) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                serial,
                action,
                actor,
                fencing,
                iso(at),
                json.dumps(safe, sort_keys=True, ensure_ascii=False),
            ),
        )

    def _allocate_fencing(self, connection: sqlite3.Connection, serial: str) -> int:
        row = connection.execute(
            "SELECT next_fencing FROM fencing_counter WHERE serial = ?",
            (serial,),
        ).fetchone()
        if row is None:
            connection.execute(
                "INSERT INTO fencing_counter(serial, next_fencing) VALUES (?, 2)",
                (serial,),
            )
            return 1
        fencing = int(row["next_fencing"])
        connection.execute(
            "UPDATE fencing_counter SET next_fencing = ? WHERE serial = ?",
            (fencing + 1, serial),
        )
        return fencing

    def status(self, serial: str | None = None, *, now: datetime | None = None) -> dict[str, Any]:
        moment = now or utc_now()
        if serial is not None:
            serial = validate_serial(serial)
        if not self.database.exists():
            if serial is None:
                return {"database": str(self.database), "initialized": False, "locks": []}
            return {
                "database": str(self.database),
                "initialized": False,
                "serial": serial,
                "state": "FREE",
            }
        connection = self._connect(write=False)
        try:
            if serial is None:
                rows = connection.execute(
                    "SELECT serial, holder, purpose, task_id, token_hash, fencing, "
                    "acquired_at, renewed_at, expires_at FROM locks ORDER BY serial"
                ).fetchall()
                return {
                    "database": str(self.database),
                    "initialized": True,
                    "locks": [self._describe(row, moment) for row in rows],
                }
            row = self._row(connection, serial)
            described = self._describe(row, moment)
            described["database"] = str(self.database)
            described["initialized"] = True
            described["serial"] = serial
            return described
        finally:
            connection.close()

    def history(self, serial: str | None = None, *, limit: int = 50) -> dict[str, Any]:
        if serial is not None:
            serial = validate_serial(serial)
        if limit < 1 or limit > 500:
            raise LockError("history limit must be 1..500", EXIT_USAGE)
        if not self.database.exists():
            return {"database": str(self.database), "initialized": False, "events": []}
        connection = self._connect(write=False)
        try:
            if serial is None:
                rows = connection.execute(
                    "SELECT id, serial, action, actor, fencing, at, detail FROM audit "
                    "ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT id, serial, action, actor, fencing, at, detail FROM audit "
                    "WHERE serial = ? ORDER BY id DESC LIMIT ?",
                    (serial, limit),
                ).fetchall()
            events = []
            for row in rows:
                detail = json.loads(str(row["detail"]))
                events.append(
                    {
                        "id": row["id"],
                        "serial": row["serial"],
                        "action": row["action"],
                        "actor": row["actor"],
                        "fencing": row["fencing"],
                        "at": row["at"],
                        "detail": public_view(detail),
                    }
                )
            return {"database": str(self.database), "initialized": True, "events": events}
        finally:
            connection.close()

    def acquire(
        self,
        serial: str,
        *,
        holder: str,
        purpose: str,
        task_id: str | None,
        ttl_seconds: int,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        serial = validate_serial(serial)
        holder = validate_identity(holder, "holder")
        purpose = validate_identity(purpose, "purpose")
        if task_id is not None:
            task_id = validate_identity(task_id, "task_id")
        ttl_seconds = validate_ttl(ttl_seconds)
        moment = now or utc_now()
        token = secrets.token_urlsafe(32)
        digest = token_hash(token)
        connection = self._connect(write=True)
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = self._row(connection, serial)
            current = self._describe(row, moment)
            if row is not None:
                self._audit(
                    connection,
                    serial=serial,
                    action="acquire_rejected",
                    actor=holder,
                    fencing=int(row["fencing"]),
                    at=moment,
                    detail={"state": current["state"], "holder": row["holder"]},
                )
                connection.execute("COMMIT")
                raise LockError(
                    "device is not free; stale locks are not taken over automatically",
                    EXIT_CONFLICT,
                    state=current["state"],
                    holder=row["holder"],
                    fencing=row["fencing"],
                    expires_at=row["expires_at"],
                )
            fencing = self._allocate_fencing(connection, serial)
            expires = iso(moment + timedelta(seconds=ttl_seconds))
            connection.execute(
                "INSERT INTO locks(serial, holder, purpose, task_id, token_hash, fencing, "
                "acquired_at, renewed_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    serial,
                    holder,
                    purpose,
                    task_id,
                    digest,
                    fencing,
                    iso(moment),
                    iso(moment),
                    expires,
                ),
            )
            self._audit(
                connection,
                serial=serial,
                action="acquire",
                actor=holder,
                fencing=fencing,
                at=moment,
                detail={"purpose": purpose, "task_id": task_id, "expires_at": expires},
            )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()
        return {
            "state": "HELD",
            "serial": serial,
            "holder": holder,
            "purpose": purpose,
            "task_id": task_id,
            "fencing": fencing,
            "acquired_at": iso(moment),
            "expires_at": expires,
            "ttl_seconds": ttl_seconds,
            "owner_token": token,
        }

    def _require_owner(
        self,
        row: sqlite3.Row | None,
        *,
        token: str,
        fencing: int,
        now: datetime,
    ) -> sqlite3.Row:
        if row is None:
            raise LockError("no active lock", EXIT_CONFLICT, state="FREE")
        if int(row["fencing"]) != fencing:
            raise LockError(
                "fencing token does not match the current owner",
                EXIT_OWNERSHIP,
                fencing=row["fencing"],
                state=self._describe(row, now)["state"],
            )
        if not hashes_equal(str(row["token_hash"]), token_hash(token)):
            raise LockError(
                "owner token does not match",
                EXIT_OWNERSHIP,
                fencing=row["fencing"],
            )
        return row

    def renew(
        self,
        serial: str,
        *,
        token: str,
        fencing: int,
        ttl_seconds: int,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        serial = validate_serial(serial)
        fencing = validate_fencing(fencing)
        ttl_seconds = validate_ttl(ttl_seconds)
        if not token:
            raise LockError("owner token is required", EXIT_USAGE)
        moment = now or utc_now()
        connection = self._connect(write=True)
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = self._require_owner(
                self._row(connection, serial), token=token, fencing=fencing, now=moment
            )
            current = self._describe(row, moment)
            if current["state"] != "HELD":
                raise LockError(
                    "stale lock cannot be renewed; break it explicitly after verification",
                    EXIT_CONFLICT,
                    state="STALE",
                    fencing=row["fencing"],
                    expires_at=row["expires_at"],
                )
            expires = iso(moment + timedelta(seconds=ttl_seconds))
            connection.execute(
                "UPDATE locks SET renewed_at = ?, expires_at = ? WHERE serial = ? AND fencing = ?",
                (iso(moment), expires, serial, fencing),
            )
            self._audit(
                connection,
                serial=serial,
                action="renew",
                actor=str(row["holder"]),
                fencing=fencing,
                at=moment,
                detail={"expires_at": expires, "ttl_seconds": ttl_seconds},
            )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()
        return {
            "state": "HELD",
            "serial": serial,
            "holder": row["holder"],
            "fencing": fencing,
            "renewed_at": iso(moment),
            "expires_at": expires,
        }

    def release(
        self,
        serial: str,
        *,
        token: str,
        fencing: int,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        serial = validate_serial(serial)
        fencing = validate_fencing(fencing)
        if not token:
            raise LockError("owner token is required", EXIT_USAGE)
        moment = now or utc_now()
        connection = self._connect(write=True)
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = self._require_owner(
                self._row(connection, serial), token=token, fencing=fencing, now=moment
            )
            previous = self._describe(row, moment)["state"]
            deleted = connection.execute(
                "DELETE FROM locks WHERE serial = ? AND fencing = ? AND token_hash = ?",
                (serial, fencing, row["token_hash"]),
            )
            if deleted.rowcount != 1:
                raise LockError("lock changed during release", EXIT_OWNERSHIP)
            self._audit(
                connection,
                serial=serial,
                action="release",
                actor=str(row["holder"]),
                fencing=fencing,
                at=moment,
                detail={"previous_state": previous},
            )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()
        return {"state": "FREE", "serial": serial, "released_fencing": fencing, "at": iso(moment)}

    def break_stale(
        self,
        serial: str,
        *,
        observed_fencing: int,
        reason: str,
        actor: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        serial = validate_serial(serial)
        observed_fencing = validate_fencing(observed_fencing)
        reason = validate_reason(reason)
        actor = validate_identity(actor, "actor")
        moment = now or utc_now()
        connection = self._connect(write=True)
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = self._row(connection, serial)
            if row is None:
                raise LockError("no lock to break", EXIT_CONFLICT, state="FREE")
            current = self._describe(row, moment)
            if int(row["fencing"]) != observed_fencing:
                raise LockError(
                    "observed fencing token does not match; refusing break",
                    EXIT_OWNERSHIP,
                    fencing=row["fencing"],
                    state=current["state"],
                )
            if current["state"] != "STALE":
                raise LockError(
                    "refusing to break a live lock",
                    EXIT_CONFLICT,
                    state="HELD",
                    holder=row["holder"],
                    fencing=row["fencing"],
                    expires_at=row["expires_at"],
                )
            deleted = connection.execute(
                "DELETE FROM locks WHERE serial = ? AND fencing = ?",
                (serial, observed_fencing),
            )
            if deleted.rowcount != 1:
                raise LockError("lock changed during break", EXIT_OWNERSHIP)
            self._audit(
                connection,
                serial=serial,
                action="break_stale",
                actor=actor,
                fencing=observed_fencing,
                at=moment,
                detail={
                    "reason": reason,
                    "previous_holder": row["holder"],
                    "purpose": row["purpose"],
                    "expired_at": row["expires_at"],
                },
            )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()
        return {
            "state": "FREE",
            "serial": serial,
            "broken_fencing": observed_fencing,
            "actor": actor,
            "at": iso(moment),
        }


def _read_restricted_file(path: Path) -> str:
    _refuse_symlink(path)
    if not path.is_file():
        raise LockError("token file is not a regular file", EXIT_USAGE)
    mode = _mode(path)
    if mode & 0o077:
        raise LockError("token file must not be group- or world-accessible", EXIT_USAGE)
    token = path.read_text(encoding="utf-8").strip()
    if not token or "\n" in token or "\x00" in token:
        raise LockError("token file must contain one secret line", EXIT_USAGE)
    return token


def resolve_owner_token(args: argparse.Namespace) -> str:
    """Load the owner token without putting it on the process argv.

    Precedence is env, then a mode-0600 file, then a single stdin line when
    ``--token-stdin`` is set. ``--token`` is rejected so shell history and
    ``ps`` never become the supported path.
    """
    supplied = [
        bool(os.environ.get(TOKEN_ENV)),
        bool(getattr(args, "token_file", None)),
        bool(getattr(args, "token_stdin", False)),
    ]
    if sum(supplied) != 1:
        raise LockError(
            f"provide the owner token via {TOKEN_ENV}, --token-file, or --token-stdin "
            "(exactly one; --token is not accepted)",
            EXIT_USAGE,
        )
    if os.environ.get(TOKEN_ENV):
        token = os.environ[TOKEN_ENV].strip()
    elif getattr(args, "token_file", None):
        token = _read_restricted_file(Path(args.token_file))
    else:
        token = sys.stdin.readline().strip()
    if not token or any(ord(character) < 32 for character in token):
        raise LockError("owner token is empty or contains control characters", EXIT_USAGE)
    return token


def _emit(payload: dict[str, Any], *, stream: Any = None) -> None:
    text = json.dumps(public_view(payload) if stream is sys.stderr else payload, sort_keys=True)
    print(text, file=stream or sys.stdout)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="device_lock",
        description=(
            "Local DEVICE:<serial> acceptance lock. Not production device_lease. "
            "Does not execute device commands."
        ),
    )
    parser.add_argument(
        "--database",
        type=Path,
        help=f"SQLite path. Default: ${DB_ENV} or <git-common-dir>/cloudctl-device-locks.sqlite3",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    status = sub.add_parser("status", help="read lock state; does not create the database")
    status.add_argument("serial", nargs="?")

    acquire = sub.add_parser("acquire", help="atomically acquire a FREE serial")
    acquire.add_argument("serial")
    acquire.add_argument("--holder", required=True)
    acquire.add_argument("--purpose", required=True)
    acquire.add_argument("--task-id")
    acquire.add_argument("--ttl", type=int, default=DEFAULT_TTL_SECONDS)

    renew = sub.add_parser("renew", help="extend a HELD lock with the owner token")
    renew.add_argument("serial")
    renew.add_argument("--fencing", type=int, required=True)
    renew.add_argument("--ttl", type=int, default=DEFAULT_TTL_SECONDS)
    _add_token_flags(renew)

    release = sub.add_parser("release", help="release with matching token and fencing")
    release.add_argument("serial")
    release.add_argument("--fencing", type=int, required=True)
    _add_token_flags(release)

    break_stale = sub.add_parser(
        "break-stale",
        help="explicitly clear one STALE lock after the controller re-checks it",
    )
    break_stale.add_argument("serial")
    break_stale.add_argument("--observed-fencing", type=int, required=True)
    break_stale.add_argument("--reason", required=True)
    break_stale.add_argument("--actor", required=True)

    history = sub.add_parser("history", help="read audit events; does not create the database")
    history.add_argument("serial", nargs="?")
    history.add_argument("--limit", type=int, default=50)
    return parser


def _add_token_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--token-file",
        help="mode 0600 file containing only the owner token",
    )
    parser.add_argument(
        "--token-stdin",
        action="store_true",
        help="read one owner-token line from stdin",
    )
    # Same subparser as the token-file flags. On the parent parser, argparse
    # prefix-matches `--token` to `--token-file` and exits 2.
    parser.add_argument("--token", action=_RejectArgvToken, help=argparse.SUPPRESS)


class _RejectArgvToken(argparse.Action):
    """Reject ``--token`` before argparse can prefix-match it to another flag."""

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: Any,
        option_string: str | None = None,
    ) -> None:
        raise LockError(
            "--token is not accepted; use "
            "CLOUDCTL_DEVICE_LOCK_TOKEN, --token-file, or --token-stdin",
            EXIT_USAGE,
        )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        database = resolve_database_path(args.database)
        store = DeviceLockStore(database)
        if args.command == "status":
            payload = store.status(args.serial)
        elif args.command == "history":
            payload = store.history(args.serial, limit=args.limit)
        elif args.command == "acquire":
            payload = store.acquire(
                args.serial,
                holder=args.holder,
                purpose=args.purpose,
                task_id=args.task_id,
                ttl_seconds=args.ttl,
            )
        elif args.command == "renew":
            payload = store.renew(
                args.serial,
                token=resolve_owner_token(args),
                fencing=args.fencing,
                ttl_seconds=args.ttl,
            )
        elif args.command == "release":
            payload = store.release(
                args.serial,
                token=resolve_owner_token(args),
                fencing=args.fencing,
            )
        elif args.command == "break-stale":
            payload = store.break_stale(
                args.serial,
                observed_fencing=args.observed_fencing,
                reason=args.reason,
                actor=args.actor,
            )
        else:
            parser.error(f"unknown command {args.command}")
            return EXIT_USAGE
    except LockError as exc:
        error_payload: dict[str, Any] = {"error": str(exc), **exc.details}
        _emit(error_payload, stream=sys.stderr)
        return exc.code
    except (sqlite3.Error, OSError) as exc:
        _emit({"error": f"lock store failure: {exc}"}, stream=sys.stderr)
        return EXIT_USAGE
    _emit(payload)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
