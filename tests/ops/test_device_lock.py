from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import stat
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "device_lock.py"


def load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("device_lock_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_cli(
    database: Path,
    args: list[str],
    *,
    env: dict[str, str] | None = None,
    stdin: str = "",
) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    merged.pop("CLOUDCTL_DEVICE_LOCK_TOKEN", None)
    merged.pop("CLOUDCTL_DEVICE_LOCK_DB", None)
    if env:
        merged.update(env)
    return subprocess.run(  # noqa: S603 - the script under test, fixed argv
        [sys.executable, str(SCRIPT), "--database", str(database), *args],
        input=stdin,
        text=True,
        capture_output=True,
        env=merged,
        check=False,
    )


def test_status_missing_database_does_not_create(tmp_path: Path) -> None:
    module = load_module()
    database = tmp_path / "missing.sqlite3"
    before = set(tmp_path.iterdir())
    payload = module.DeviceLockStore(database).status("abc123")
    assert payload["state"] == "FREE"
    assert payload["initialized"] is False
    assert set(tmp_path.iterdir()) == before
    assert not database.exists()

    cli = run_cli(database, ["status", "abc123"])
    assert cli.returncode == 0
    assert json.loads(cli.stdout)["initialized"] is False
    assert not database.exists()
    history = run_cli(database, ["history", "abc123"])
    assert history.returncode == 0
    assert json.loads(history.stdout)["events"] == []
    assert not database.exists()


def _snapshot(directory: Path) -> dict[str, tuple[int, int]]:
    return {
        path.name: (path.stat().st_size, path.stat().st_mtime_ns)
        for path in directory.iterdir()
    }


def test_status_does_not_write_existing_database(tmp_path: Path) -> None:
    module = load_module()
    database = tmp_path / "locks.sqlite3"
    store = module.DeviceLockStore(database)
    now = datetime(2026, 9, 22, 1, 0, tzinfo=UTC)
    acquired = store.acquire(
        "serial-a",
        holder="controller@host",
        purpose="acceptance",
        task_id="DEVICE-LOCK",
        ttl_seconds=60,
        now=now,
    )
    before = _snapshot(tmp_path)
    status = store.status("serial-a", now=now + timedelta(seconds=1))
    history = store.history("serial-a")
    cli_status = run_cli(database, ["status", "serial-a"])
    cli_history = run_cli(database, ["history", "serial-a"])
    assert status["state"] == "HELD"
    assert status["fencing"] == acquired["fencing"]
    assert "owner_token" not in status
    assert "token_hash" not in status
    assert history["events"]
    assert cli_status.returncode == 0
    assert cli_history.returncode == 0
    assert _snapshot(tmp_path) == before


def test_single_acquire_and_monotonic_fencing(tmp_path: Path) -> None:
    module = load_module()
    store = module.DeviceLockStore(tmp_path / "locks.sqlite3")
    now = datetime(2026, 9, 22, 1, 0, tzinfo=UTC)
    first = store.acquire(
        "serial-a", holder="a", purpose="one", task_id=None, ttl_seconds=60, now=now
    )
    store.release("serial-a", token=first["owner_token"], fencing=first["fencing"], now=now)
    second = store.acquire(
        "serial-a", holder="b", purpose="two", task_id=None, ttl_seconds=60, now=now
    )
    assert first["fencing"] == 1
    assert second["fencing"] == 2
    assert first["owner_token"] != second["owner_token"]
    events = store.history("serial-a")["events"]
    assert [event["action"] for event in events] == ["acquire", "release", "acquire"]
    blob = json.dumps(events)
    assert first["owner_token"] not in blob
    assert second["owner_token"] not in blob


def _seed(store: object, module: ModuleType, serial: str = "serial-a") -> dict:
    now = datetime(2026, 9, 22, 1, 0, tzinfo=UTC)
    return store.acquire(  # type: ignore[attr-defined]
        serial,
        holder="before",
        purpose="seed",
        task_id=None,
        ttl_seconds=60,
        now=now,
    )


def test_status_sees_commit_while_writer_stays_open(tmp_path: Path) -> None:
    """A COMMIT must be visible before the writer connection closes.

    immutable=1 on WAL hid this and reported the previous holder.
    """
    module = load_module()
    database = tmp_path / "locks.sqlite3"
    store = module.DeviceLockStore(database)
    now = datetime(2026, 9, 22, 1, 0, tzinfo=UTC)
    _seed(store, module)
    writer = sqlite3.connect(database, timeout=5, isolation_level=None)
    writer.execute("PRAGMA busy_timeout = 5000")
    try:
        assert str(writer.execute("PRAGMA journal_mode").fetchone()[0]).lower() == "delete"
        writer.execute("BEGIN IMMEDIATE")
        writer.execute("UPDATE locks SET holder = 'after' WHERE serial = 'serial-a'")
        writer.execute(
            "INSERT INTO audit(serial, action, actor, fencing, at, detail) "
            "VALUES ('serial-a', 'external', 'probe', 1, '2026-09-22T01:00:00Z', '{}')"
        )
        writer.execute("COMMIT")
        seen = store.status("serial-a", now=now)
        assert seen["holder"] == "after"
        assert seen["state"] == "HELD"
        events = store.history("serial-a")["events"]
        assert events[0]["action"] == "external"
        # Writer has not closed. A second status must still show the commit.
        assert store.status("serial-a", now=now)["holder"] == "after"
    finally:
        writer.close()


def test_uncommitted_writer_is_not_visible(tmp_path: Path) -> None:
    """BEGIN IMMEDIATE is a snapshot, not a read barrier.

    DELETE mode keeps the previous pages until COMMIT. status/history must
    return that committed holder quickly and must not observe `dirty` or an
    audit row that has not been committed. This must not wait for the writer.
    """
    module = load_module()
    database = tmp_path / "locks.sqlite3"
    store = module.DeviceLockStore(database)
    now = datetime(2026, 9, 22, 1, 0, tzinfo=UTC)
    _seed(store, module)
    writer = sqlite3.connect(database, timeout=5, isolation_level=None)
    writer.execute("PRAGMA busy_timeout = 5000")
    writer.execute("BEGIN IMMEDIATE")
    writer.execute("UPDATE locks SET holder = 'dirty' WHERE serial = 'serial-a'")
    writer.execute(
        "INSERT INTO audit(serial, action, actor, fencing, at, detail) "
        "VALUES ('serial-a', 'not-committed', 'probe', 1, '2026-09-22T01:00:00Z', '{}')"
    )
    try:
        assert writer.execute("SELECT holder FROM locks").fetchone()[0] == "dirty"
        started = time.monotonic()
        status = store.status("serial-a", now=now)
        history = store.history("serial-a")
        elapsed = time.monotonic() - started
        assert elapsed < 1.0, elapsed
        assert status["holder"] == "before"
        blob = json.dumps(history)
        assert "dirty" not in blob
        assert "not-committed" not in blob
        writer.execute("ROLLBACK")
        assert store.status("serial-a", now=now)["holder"] == "before"
    finally:
        if writer.in_transaction:
            writer.execute("ROLLBACK")
        writer.close()


def test_exclusive_lock_blocks_reader_until_release(tmp_path: Path) -> None:
    """BEGIN EXCLUSIVE is the lock that actually stops a mode=ro reader."""
    module = load_module()
    database = tmp_path / "locks.sqlite3"
    store = module.DeviceLockStore(database)
    now = datetime(2026, 9, 22, 1, 0, tzinfo=UTC)
    _seed(store, module)
    writer = sqlite3.connect(database, timeout=5, isolation_level=None)
    writer.execute("PRAGMA busy_timeout = 5000")
    writer.execute("BEGIN EXCLUSIVE")
    writer.execute("UPDATE locks SET holder = 'dirty' WHERE serial = 'serial-a'")
    box: dict[str, object] = {}

    def read_status() -> None:
        box["status"] = store.status("serial-a", now=now)

    try:
        worker = threading.Thread(target=read_status)
        worker.start()
        worker.join(0.3)
        assert worker.is_alive()
        assert "status" not in box
        writer.execute("ROLLBACK")
        worker.join(5)
        assert not worker.is_alive()
        assert box["status"]["holder"] == "before"  # type: ignore[index]
    finally:
        if writer.in_transaction:
            writer.execute("ROLLBACK")
        writer.close()


def test_corrupt_database_is_store_failure(tmp_path: Path) -> None:
    module = load_module()
    database = tmp_path / "locks.sqlite3"
    store = module.DeviceLockStore(database)
    now = datetime(2026, 9, 22, 1, 0, tzinfo=UTC)
    store.acquire(
        "serial-a", holder="before", purpose="seed", task_id=None, ttl_seconds=60, now=now
    )
    payload = database.read_bytes()
    database.write_bytes(b"not a sqlite database" + payload[20:])
    cli = run_cli(database, ["status", "serial-a"])
    assert cli.returncode == 5
    assert cli.stdout == ""
    assert "not a database" in json.loads(cli.stderr)["error"]
    history = run_cli(database, ["history", "serial-a"])
    assert history.returncode == 5


def test_killed_transaction_rolls_back_committed_lock_stays(tmp_path: Path) -> None:
    module = load_module()
    database = tmp_path / "locks.sqlite3"
    store = module.DeviceLockStore(database)
    now = datetime(2026, 9, 22, 1, 0, tzinfo=UTC)
    held = store.acquire(
        "serial-a", holder="before", purpose="seed", task_id=None, ttl_seconds=60, now=now
    )
    crash = tmp_path / "crash.py"
    crash.write_text(
        "import os, sqlite3, sys\n"
        "con = sqlite3.connect(sys.argv[1], isolation_level=None, timeout=5)\n"
        "con.execute('PRAGMA busy_timeout=2000')\n"
        "con.execute('BEGIN IMMEDIATE')\n"
        "con.execute(\"UPDATE locks SET holder='crashed' WHERE serial='serial-a'\")\n"
        "os._exit(99)\n",
        encoding="utf-8",
    )
    completed = subprocess.run(  # noqa: S603 - fixed interpreter and temp script
        [sys.executable, str(crash), str(database)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 99
    assert (tmp_path / "locks.sqlite3-journal").exists()
    status = store.status("serial-a", now=now)
    assert status["holder"] == "before"
    assert status["fencing"] == held["fencing"]
    assert status["state"] == "HELD"


def test_cold_start_acquire_race_is_stable(tmp_path: Path) -> None:
    """Several processes creating one database must not surface 'database is locked' as exit 5."""
    rounds = 12
    workers_per_round = 8
    for round_index in range(rounds):
        database = tmp_path / f"round-{round_index}" / "locks.sqlite3"
        workers = []
        for index in range(workers_per_round):
            workers.append(
                subprocess.Popen(  # noqa: S603 - the script under test, fixed argv
                    [
                        sys.executable,
                        str(SCRIPT),
                        "--database",
                        str(database),
                        "acquire",
                        "race-serial",
                        "--holder",
                        f"holder-{index}",
                        "--purpose",
                        "cold-start",
                        "--ttl",
                        "60",
                    ],
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
            )
        results = [
            (proc.wait(timeout=60), proc.stdout.read(), proc.stderr.read()) for proc in workers
        ]
        codes = sorted(code for code, _, _ in results)
        stderr_text = "\n".join(stderr for _, _, stderr in results)
        assert "database is locked" not in stderr_text, stderr_text
        assert codes == [0, *([3] * (workers_per_round - 1))], (round_index, codes, stderr_text)


def test_cross_process_acquire_allows_one_winner(tmp_path: Path) -> None:
    database = tmp_path / "locks.sqlite3"
    workers = []
    for index in range(8):
        workers.append(
            subprocess.Popen(  # noqa: S603 - the script under test, fixed argv
                [
                    sys.executable,
                    str(SCRIPT),
                    "--database",
                    str(database),
                    "acquire",
                    "race-serial",
                    "--holder",
                    f"holder-{index}",
                    "--purpose",
                    "race",
                    "--ttl",
                    "60",
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        )
    results = [(proc.wait(timeout=30), proc.stdout.read(), proc.stderr.read()) for proc in workers]
    codes = sorted(code for code, _, _ in results)
    assert codes[0] == 0
    assert codes[1:] == [3] * 7
    winner = next(stdout for code, stdout, _stderr in results if code == 0)
    payload = json.loads(winner)
    assert payload["fencing"] == 1
    assert payload["owner_token"]
    losers = [json.loads(stderr) for code, _stdout, stderr in results if code == 3]
    assert all("owner_token" not in item for item in losers)
    module = load_module()
    status = module.DeviceLockStore(database).status("race-serial")
    assert status["state"] == "HELD"
    assert status["fencing"] == 1


def test_stale_is_not_stolen_and_break_is_exact(tmp_path: Path) -> None:
    module = load_module()
    store = module.DeviceLockStore(tmp_path / "locks.sqlite3")
    now = datetime(2026, 9, 22, 1, 0, tzinfo=UTC)
    held = store.acquire(
        "serial-a", holder="owner", purpose="work", task_id=None, ttl_seconds=60, now=now
    )
    later = now + timedelta(seconds=61)
    with pytest.raises(module.LockError) as rejected:
        store.acquire(
            "serial-a", holder="other", purpose="steal", task_id=None, ttl_seconds=60, now=later
        )
    assert rejected.value.code == 3
    assert store.status("serial-a", now=later)["state"] == "STALE"
    with pytest.raises(module.LockError) as live_break:
        store.break_stale(
            "serial-a",
            observed_fencing=held["fencing"],
            reason="checked the phone",
            actor="controller",
            now=now,
        )
    assert live_break.value.code == 3
    with pytest.raises(module.LockError) as wrong_fence:
        store.break_stale(
            "serial-a",
            observed_fencing=held["fencing"] + 9,
            reason="checked the phone",
            actor="controller",
            now=later,
        )
    assert wrong_fence.value.code == 4
    with pytest.raises(module.LockError):
        store.renew(
            "serial-a",
            token=held["owner_token"],
            fencing=held["fencing"],
            ttl_seconds=60,
            now=later,
        )
    broken = store.break_stale(
        "serial-a",
        observed_fencing=held["fencing"],
        reason="owner process exited and phone is idle",
        actor="controller@desk",
        now=later,
    )
    assert broken["state"] == "FREE"
    again = store.acquire(
        "serial-a", holder="next", purpose="after break", task_id=None, ttl_seconds=60, now=later
    )
    assert again["fencing"] == held["fencing"] + 1
    with pytest.raises(module.LockError) as old_release:
        store.release(
            "serial-a", token=held["owner_token"], fencing=held["fencing"], now=later
        )
    assert old_release.value.code == 4
    assert store.status("serial-a", now=later)["holder"] == "next"


def test_old_token_cannot_release_new_owner(tmp_path: Path) -> None:
    module = load_module()
    store = module.DeviceLockStore(tmp_path / "locks.sqlite3")
    now = datetime(2026, 9, 22, 1, 0, tzinfo=UTC)
    first = store.acquire(
        "serial-a", holder="a", purpose="one", task_id=None, ttl_seconds=60, now=now
    )
    store.release("serial-a", token=first["owner_token"], fencing=first["fencing"], now=now)
    second = store.acquire(
        "serial-a", holder="b", purpose="two", task_id=None, ttl_seconds=60, now=now
    )
    with pytest.raises(module.LockError) as mismatch:
        store.release(
            "serial-a", token=first["owner_token"], fencing=second["fencing"], now=now
        )
    assert mismatch.value.code == 4
    store.release("serial-a", token=second["owner_token"], fencing=second["fencing"], now=now)
    assert store.status("serial-a", now=now)["state"] == "FREE"


def test_common_dir_resolution(tmp_path: Path) -> None:
    module = load_module()
    origin = tmp_path / "origin"
    origin.mkdir()
    subprocess.run(  # noqa: S603 - fixed git setup for a temp repository
        ["git", "init"],  # noqa: S607
        cwd=origin,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(  # noqa: S603 - fixed git setup for a temp repository
        ["git", "config", "user.email", "lock@example.com"],  # noqa: S607
        cwd=origin,
        check=True,
    )
    subprocess.run(  # noqa: S603 - fixed git setup for a temp repository
        ["git", "config", "user.name", "lock"],  # noqa: S607
        cwd=origin,
        check=True,
    )
    (origin / "README").write_text("base\n", encoding="utf-8")
    subprocess.run(  # noqa: S603 - fixed git setup for a temp repository
        ["git", "add", "README"],  # noqa: S607
        cwd=origin,
        check=True,
    )
    subprocess.run(  # noqa: S603 - fixed git setup for a temp repository
        ["git", "commit", "-m", "base"],  # noqa: S607
        cwd=origin,
        check=True,
        capture_output=True,
    )
    first = tmp_path / "wt-a"
    second = tmp_path / "wt-b"
    subprocess.run(  # noqa: S603 - fixed git worktree setup
        ["git", "worktree", "add", str(first), "-b", "lock-a"],  # noqa: S607
        cwd=origin,
        check=True,
    )
    subprocess.run(  # noqa: S603 - fixed git worktree setup
        ["git", "worktree", "add", str(second), "-b", "lock-b"],  # noqa: S607
        cwd=origin,
        check=True,
    )
    from_first = module.resolve_database_path(start=first)
    from_second = module.resolve_database_path(start=second)
    assert from_first == from_second
    assert from_first.name == "cloudctl-device-locks.sqlite3"
    common = subprocess.check_output(  # noqa: S603 - fixed git query
        ["git", "-C", str(first), "rev-parse", "--path-format=absolute", "--git-common-dir"],  # noqa: S607
        text=True,
    ).strip()
    assert from_first.parent == Path(common)


def test_secrets_never_land_in_database_or_public_output(tmp_path: Path) -> None:
    database = tmp_path / "locks.sqlite3"
    acquired = run_cli(
        database,
        ["acquire", "serial-a", "--holder", "owner", "--purpose", "cli", "--ttl", "60"],
    )
    assert acquired.returncode == 0, acquired.stderr
    payload = json.loads(acquired.stdout)
    token = payload["owner_token"]
    fencing = str(payload["fencing"])
    assert token
    stored = database.read_bytes()
    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(database) + suffix)
        if sidecar.exists():
            stored += sidecar.read_bytes()
    assert token.encode("utf-8") not in stored

    status = run_cli(database, ["status", "serial-a"])
    history = run_cli(database, ["history", "serial-a"])
    for completed in (status, history):
        assert completed.returncode == 0
        assert token not in completed.stdout
        assert token not in completed.stderr
        assert "token_hash" not in completed.stdout
        assert "owner_token" not in completed.stdout

    module = load_module()
    raw = module.DeviceLockStore(database).history("serial-a")
    assert token not in json.dumps(raw)

    argv_token = run_cli(
        database,
        ["release", "serial-a", "--fencing", fencing, "--token", token],
    )
    assert argv_token.returncode == 5
    assert token not in argv_token.stderr
    still_held = run_cli(database, ["status", "serial-a"])
    assert json.loads(still_held.stdout)["state"] == "HELD"


def test_darwin_mount_classification() -> None:
    module = load_module()
    mount_text = "\n".join(
        [
            "/dev/disk3s1s1 on / (apfs, sealed, local, read-only, journaled)",
            "/dev/disk3s5 on /System/Volumes/Data (apfs, local, journaled, nobrowse)",
            "//server/share on /Volumes/share (smbfs, nodev, nosuid)",
            "user@host:/home on /mnt/remote (nfs, nodev)",
        ]
    )
    assert module.fstype_from_darwin_mount("disk3s5", mount_text) == "apfs"
    assert module.fstype_from_darwin_mount("disk3s1s1", mount_text) == "apfs"
    assert module.fstype_from_darwin_mount("disk9", mount_text) is None
    assert module.fstype_from_darwin_mount("disk3s5 extra", mount_text) is None
    duplicate = mount_text + "\n/dev/disk3s5 on /Volumes/other (apfs, local)\n"
    assert module.fstype_from_darwin_mount("disk3s5", duplicate) is None

    def verdict(fstype: str) -> str:
        if fstype in module.NETWORK_FSTYPES or fstype.startswith("nfs"):
            return "network"
        if fstype not in module.LOCAL_FSTYPES:
            return "unlisted"
        return "local"

    assert verdict("apfs") == "local"
    assert verdict("ext4") == "local"
    assert verdict("hfs") == "local"
    for networked in (
        "nfs",
        "nfs4",
        "smb",
        "smbfs",
        "cifs",
        "sshfs",
        "fuse.sshfs",
        "afp",
        "afpfs",
        "9p",
        "vboxsf",
    ):
        assert verdict(networked) == "network"
    assert verdict("fuse.something") == "unlisted"
    overlap = module.NETWORK_FSTYPES & module.LOCAL_FSTYPES
    assert overlap == set()


def test_this_workspace_filesystem_is_classified_local() -> None:
    module = load_module()
    fstype = module.classify_fstype(Path(__file__).resolve().parent)
    if sys.platform == "darwin":
        assert fstype == "apfs"
    elif sys.platform.startswith("linux"):
        assert fstype in module.LOCAL_FSTYPES
        assert fstype not in module.NETWORK_FSTYPES
    else:
        assert fstype is None


def test_cli_token_channels_and_no_leak(tmp_path: Path) -> None:
    database = tmp_path / "locks.sqlite3"
    acquired = run_cli(
        database,
        ["acquire", "serial-a", "--holder", "owner", "--purpose", "cli", "--ttl", "60"],
    )
    assert acquired.returncode == 0
    payload = json.loads(acquired.stdout)
    token = payload["owner_token"]
    fencing = str(payload["fencing"])
    status = run_cli(database, ["status", "serial-a"])
    assert token not in status.stdout
    assert "token_hash" not in status.stdout
    history = run_cli(database, ["history", "serial-a"])
    assert token not in history.stdout

    rejected = run_cli(
        database,
        ["release", "serial-a", "--fencing", fencing, "--token", token],
    )
    assert rejected.returncode != 0

    via_env = run_cli(
        database,
        ["renew", "serial-a", "--fencing", fencing, "--ttl", "120"],
        env={"CLOUDCTL_DEVICE_LOCK_TOKEN": token},
    )
    assert via_env.returncode == 0, via_env.stderr
    assert token not in via_env.stdout

    token_file = tmp_path / "token"
    token_file.write_text(token + "\n", encoding="utf-8")
    token_file.chmod(0o644)
    loose = run_cli(
        database,
        ["release", "serial-a", "--fencing", fencing, "--token-file", str(token_file)],
    )
    assert loose.returncode == 5
    token_file.chmod(0o600)
    released = run_cli(
        database,
        ["release", "serial-a", "--fencing", fencing, "--token-file", str(token_file)],
    )
    assert released.returncode == 0, released.stderr
    assert token not in released.stdout

    again = run_cli(
        database,
        ["acquire", "serial-a", "--holder", "next", "--purpose", "after", "--ttl", "60"],
    )
    assert again.returncode == 0, again.stderr
    new_payload = json.loads(again.stdout)
    old_release = run_cli(
        database,
        ["release", "serial-a", "--fencing", str(new_payload["fencing"])],
        env={"CLOUDCTL_DEVICE_LOCK_TOKEN": token},
    )
    assert old_release.returncode == 4
    assert token not in old_release.stdout
    assert token not in old_release.stderr
    assert json.loads(run_cli(database, ["status", "serial-a"]).stdout)["holder"] == "next"

    mode = stat.S_IMODE(database.stat().st_mode)
    assert mode & 0o077 == 0


def test_input_validation(tmp_path: Path) -> None:
    module = load_module()
    store = module.DeviceLockStore(tmp_path / "locks.sqlite3")
    now = datetime(2026, 9, 22, 1, 0, tzinfo=UTC)
    with pytest.raises(module.LockError) as bad_serial:
        store.acquire("serial a", holder="a", purpose="p", task_id=None, ttl_seconds=60, now=now)
    assert bad_serial.value.code == 5
    with pytest.raises(module.LockError):
        store.acquire("ok", holder="a", purpose="p", task_id=None, ttl_seconds=59, now=now)
    with pytest.raises(module.LockError):
        store.acquire("ok", holder=" ", purpose="p", task_id=None, ttl_seconds=60, now=now)
    held = store.acquire(
        "ok", holder="a", purpose="p", task_id=None, ttl_seconds=60, now=now
    )
    with pytest.raises(module.LockError):
        store.break_stale(
            "ok",
            observed_fencing=held["fencing"],
            reason="short",
            actor="controller",
            now=now + timedelta(seconds=120),
        )


def test_unchmodable_parent_still_locks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_module()
    parent = tmp_path / "no-chmod"
    parent.mkdir()
    database = parent / "locks.sqlite3"
    original = Path.chmod

    def refuse_parent(path: Path, mode: int) -> None:
        if Path(path) == parent:
            raise PermissionError("simulated sticky directory")
        original(path, mode)

    monkeypatch.setattr(Path, "chmod", refuse_parent)
    now = datetime(2026, 9, 22, 1, 0, tzinfo=UTC)
    acquired = module.DeviceLockStore(database).acquire(
        "serial-a",
        holder="a",
        purpose="parent chmod refused",
        task_id=None,
        ttl_seconds=60,
        now=now,
    )
    assert acquired["fencing"] == 1
    assert stat.S_IMODE(database.stat().st_mode) & 0o077 == 0


def test_ancestor_symlink_is_not_a_refusal(tmp_path: Path) -> None:
    """macOS /tmp is a symlink. Only the database file and its own parent count."""
    module = load_module()
    linked_root = tmp_path / "linked-root"
    linked_root.symlink_to(tmp_path, target_is_directory=True)
    database = linked_root / "child" / "locks.sqlite3"
    now = datetime(2026, 9, 22, 1, 0, tzinfo=UTC)
    acquired = module.DeviceLockStore(database).acquire(
        "serial-a",
        holder="a",
        purpose="via ancestor symlink",
        task_id=None,
        ttl_seconds=60,
        now=now,
    )
    assert acquired["fencing"] == 1
    parent_link = tmp_path / "parent-link"
    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    parent_link.symlink_to(real_parent, target_is_directory=True)
    with pytest.raises(module.LockError) as refused_parent:
        module.DeviceLockStore(parent_link / "locks.sqlite3").acquire(
            "serial-a",
            holder="a",
            purpose="direct parent symlink",
            task_id=None,
            ttl_seconds=60,
            now=now,
        )
    assert refused_parent.value.code == 5


def test_symlink_database_is_refused(tmp_path: Path) -> None:
    module = load_module()
    real = tmp_path / "real.sqlite3"
    module.DeviceLockStore(real).acquire(
        "serial-a",
        holder="a",
        purpose="seed",
        task_id=None,
        ttl_seconds=60,
        now=datetime(2026, 9, 22, 1, 0, tzinfo=UTC),
    )
    link = tmp_path / "linked.sqlite3"
    link.symlink_to(real)
    with pytest.raises(module.LockError) as refused:
        module.DeviceLockStore(link).status("serial-a")
    assert refused.value.code == 5


def test_other_serial_is_independent(tmp_path: Path) -> None:
    module = load_module()
    store = module.DeviceLockStore(tmp_path / "locks.sqlite3")
    now = datetime(2026, 9, 22, 1, 0, tzinfo=UTC)
    store.acquire("one", holder="a", purpose="p", task_id=None, ttl_seconds=60, now=now)
    other = store.acquire("two", holder="b", purpose="p", task_id=None, ttl_seconds=60, now=now)
    assert other["fencing"] == 1
    assert store.status("one", now=now)["holder"] == "a"
