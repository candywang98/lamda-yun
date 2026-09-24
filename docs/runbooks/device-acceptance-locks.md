# Device acceptance locks

`scripts/device_lock.py` is a **local development-acceptance lock** for one
exact Android serial. It is not production PostgreSQL `device_lease`.

| Store | What it proves | What it does not prove |
| --- | --- | --- |
| This SQLite file | At most one recorded local holder of `DEVICE:<serial>` among processes that use this file | That production has no lease, that ADB is idle, or that a human is not using the phone |
| PostgreSQL `device_lease` | The production fencing lease for an enrolled device | That a laptop acceptance session is not installing or driving the same phone |

Neither store can clear the other. Before any real-device write, the operator
must check **both** this lock and the production lease, plus the physical
device. This tool never runs ADB, shell, or device commands.

## Bootstrap is not proof of idle

The tool cannot rewind history. The first time it creates the SQLite file,
`FREE` only means **this database has no row**. It does not mean other
sessions, older scripts, or a person at the device are idle. An empty or
missing database is a bootstrap state. The controller must still verify:

- no production `device_lease` row is active for that device;
- no other acceptance window, installer, or scrcpy/LAMDA session is attached;
- the person who can see the phone confirms it is free.

Record that external check in the acceptance notes. Do not treat a fresh
`status: FREE` as that check.

## Pool locks are not covered

The database locks **one exact serial** (`DEVICE:<serial>`), nothing else.
It does not know USB versus Wi-Fi identity aliases, and it does not know a
pool such as "any free phone" or "the OnePlus pool".

Pool exclusion is **not provable here** and is a hard stop:

- do not acquire a pool id, a glob, or a second alias of the same phone;
- do not assume locking `DEVICE:abc` blocks `DEVICE:adb-abc-5555`;
- if the operation needs "the only device in a pool", a human must name the
  exact serial and confirm no other serial in that pool is in use. This tool
  cannot do that confirmation.

## Where the database lives

Default path: `<git common-dir>/cloudctl-device-locks.sqlite3`.

`git rev-parse --git-common-dir` is shared by every worktree of this clone, so
two worktrees contend for the same rows. Override with `--database` or
`CLOUDCTL_DEVICE_LOCK_DB` only for tests or a deliberately separate lock
domain. Do not point this at PostgreSQL, a repo path that will be committed,
or a network filesystem.

Filesystem check is **fail closed**. The tool refuses a symlink at the
database file or at its immediate parent directory. Ancestor symlinks such as
macOS `/tmp` → `/private/tmp` are followed and then classified; they are not
themselves a refusal.
It classifies the parent (Darwin: `stat` device id matched to one `mount`
line; Linux: `stat -f -c %T`, then `findmnt`, then GNU `df -P -T`). macOS
`df -T` is a type filter and is not used. Known networked types are refused:
`nfs`/`nfs4`, `smb`/`smbfs`/`cifs`, `sshfs`/`fuse.sshfs`, `afp`/`afpfs`,
`9p`, `webdav`, `vboxsf`, and similar. Only a proven local type is accepted
(`apfs`, `hfs`, `ext2/3/4`, `xfs`, `btrfs`, `zfs`, `f2fs`, `tmpfs`,
`overlay`, and the other names in `LOCAL_FSTYPES`). If classification fails,
or the type is anything else, the command exits `5` and does not create or
open the database. A normal local APFS volume is accepted.

The database file is mode `0600`. Group/world bits on an existing database are
tightened before a write. The parent directory's mode is tightened only when
the process is allowed to `chmod` it; a sticky system directory that refuses
`chmod` does not block the lock.

Journal mode is SQLite's default **DELETE** rollback journal, not WAL.
`synchronous=FULL`. A commit is in the main database file before the writer
returns, including while that writer connection stays open. `status` and
`history` therefore see the latest commit without waiting for the writer to
close.

An open uncommitted `BEGIN IMMEDIATE` is not a read barrier. DELETE mode keeps
the previous pages in the main file until commit, so `status` and `history`
return that last commit promptly. They must not return the in-progress holder
or an audit row that has not been committed, and they must not sit on
`busy_timeout` waiting for this transaction. `BEGIN EXCLUSIVE` is different: it
takes the lock a `mode=ro` reader needs, so the read waits and, if the lock is
still held when `busy_timeout` (15s) expires, exits `5`. A database SQLite
cannot read (truncated header, permission error, `database is locked` on an
existing file) is the same store failure, exit `5`, not device conflict `3`.
After the writer rolls back, status still shows the last commit. After it
commits, status shows the new row even if the writer process has not exited.

WAL is refused. `PRAGMA journal_mode=WAL` plus a reader opened with
`immutable=1` ignores a commit that is still only in the WAL, so status can
report the previous holder or `FREE` after the writer has already committed.
That lie is worse than a lock wait. If a database was created by an older
build in WAL mode, the next writer switches it to DELETE (checkpointing
first) and then continues. A symlink at `<database>-journal` is refused.

A crash may leave a `-journal` file. The next writer or reader rolls the
interrupted transaction back; a committed lock is not deleted or stolen. The
journal file is removed when SQLite finishes recovery or the next transaction.
Do not delete it by hand while a writer might still be alive.

## Commands

```bash
python scripts/device_lock.py status
python scripts/device_lock.py status <serial>
python scripts/device_lock.py history <serial>
python scripts/device_lock.py acquire <serial> \
  --holder '<controller identity>' \
  --purpose '<why this acceptance run>' \
  --task-id '<task>' \
  --ttl 1800
python scripts/device_lock.py renew <serial> --fencing <n> --ttl 1800 --token-stdin
python scripts/device_lock.py release <serial> --fencing <n> --token-stdin
python scripts/device_lock.py break-stale <serial> \
  --observed-fencing <n> \
  --actor '<controller identity>' \
  --reason '<what was checked before breaking>'
```

`status` and `history` are read-only. If the database file does not exist
they report `initialized: false` and do **not** create it. Expiry does not
flip a row to free and does not take the lock.

TTL is 60..28800 seconds, default 1800. A stale row stays occupied until
`break-stale` or a matching owner `release`.

## Owner token

`acquire` prints `owner_token` once on stdout. The database stores only
SHA-256. `status`, `history`, and error payloads do not include the token or
the hash.

Do not pass `--token`. The process rejects that shape so the secret is not
put on `argv` (shell history, `ps`). Supply exactly one of:

- environment `CLOUDCTL_DEVICE_LOCK_TOKEN` (still visible to the process
  environment; prefer the other two on a shared machine);
- `--token-file` pointing at a regular file mode `0600` with one line;
- `--token-stdin`, one line on stdin.

Renew and release require that secret **and** the current fencing token.
A previous owner's token, or the right token with an old fencing number,
does not release or renew the new owner. There is no force-release.

## Fencing and break

Each successful acquire for a serial gets the next integer fencing token,
starting at 1. The counter survives release and break, so fencing only
increases.

`break-stale` is the only non-owner clear. It must see all of:

1. the row is already `STALE` (`expires_at <= now`);
2. `--observed-fencing` equals the fencing value just read from `status`;
3. `--actor` names the controller who checked;
4. `--reason` records why the break is safe (at least 8 characters).

A live lock, a missing lock, or a fencing mismatch is not broken. Break does
not acquire. After it returns `FREE`, the controller repeats the external
idle check and only then calls `acquire`, which receives a **new** fencing
token.

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | JSON result on stdout |
| 3 | Conflict: held, stale, or missing when the command required another state |
| 4 | Token or fencing does not match the current owner |
| 5 | Usage, path, permission, schema, or SQLite failure |

## Crash, contention, permissions

- Acquire/renew/release/break take `BEGIN IMMEDIATE` and set `busy_timeout`.
  Two racers against an existing database: one commit wins, the other gets
  conflict `3` because the row is held, stale, or no longer matches. A SQLite
  `database is locked` / `database is busy` that is not that row conflict is a
  store failure and exits `5`. It is not reported as "device busy".
- Creating the file is the one place a lock error is retried. Several processes
  can all see "no database" and then one hits `database is locked` outside
  `busy_timeout`. That cold-create path retries a few times. Once the file
  exists, the same error exits `5`. Losing the race for a free serial still
  exits `3`.
- `synchronous=FULL` and the DELETE journal. A killed process rolls back an
  open transaction on the next open. It does not auto-release a committed lock.
- `status` and `history` open `mode=ro` (not `immutable`) and turn on
  `query_only`. They do not create a missing database. On a stable closed
  database (no writer, no leftover `-journal`) they do not change the directory
  listing or the size/mtime of the database file. They read the latest commit
  even if the writer process has not exited. While a writer holds an
  uncommitted `BEGIN IMMEDIATE` they return the last commit promptly, not the
  dirty row. `BEGIN EXCLUSIVE`, or a database SQLite cannot read, waits at most
  `busy_timeout` and then exits `5`, not device conflict `3`.
- Symlinked database, journal, or token files are refused.
- This is still a local advisory lock. A root user, a copied database, or a
  second `--database` path bypasses it. Those are operational gaps, not
  guarantees this file can close.
