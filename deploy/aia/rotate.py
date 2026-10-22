#!/usr/bin/env python3
"""Root-only AIA API credential rotation: 90-day token, rotate after 60 days."""
from __future__ import annotations

import fcntl
import os
import re
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

COMPOSE = (
    "/usr/bin/docker", "compose", "-p", "mateerp",
    "--env-file", "/opt/MateERP/.env.production",
    "-f", "/opt/MateERP/compose.production.yml",
    "exec", "-T", "backend", "python", "manage.py",
)
ROOT = Path("/etc/mateerp/aia")
TOKEN = ROOT / "token"
PREVIOUS = ROOT / "token.previous"
LOCK = ROOT / ".rotation.lock"
INTERVAL = 60 * 24 * 3600
PATTERN = re.compile(rb"^aia_([a-f0-9]{16})_[A-Za-z0-9_-]{40,100}$")
URL = "https://erp.netamate.com"


class RotationError(RuntimeError):
    pass


def load(path: Path) -> bytes:
    if path.is_symlink():
        raise RotationError("Credential symlink not accepted.")
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o077:
        raise RotationError("Credential permissions or owner invalid.")
    with path.open("rb") as stream:
        value = stream.read(256).strip()
    if not PATTERN.fullmatch(value):
        raise RotationError("Credential has invalid format.")
    return value


def prefix(value: bytes) -> str:
    match = PATTERN.fullmatch(value)
    if not match:
        raise RotationError("Invalid credential.")
    return match.group(1).decode("ascii")


def backend(*args: str) -> bytes:
    try:
        process = subprocess.run(
            [*COMPOSE, *args], cwd="/opt/MateERP", capture_output=True,
            timeout=100, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RotationError("Backend unavailable.") from exc
    if process.returncode:
        # Never include stderr; it could contain sensitive data.
        raise RotationError("Backend token management command failed.")
    return process.stdout.strip()


def issue() -> bytes:
    return backend(
        "issue_aia_token", "--name", "MateERP AIA automated rotation",
        "--days", "90",
    )


def revoke(value: bytes) -> None:
    backend("revoke_aia_token", prefix(value))


def status(path: str, value: bytes) -> int:
    request = urllib.request.Request(
        URL + path,
        headers={"Authorization": "Bearer " + value.decode("ascii"),
                 "Accept": "application/json"},
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=20) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code


def verify(value: bytes) -> None:
    try:
        allowed = status("/api/v1/sales/customers/?page=1", value)
        denied = status("/api/v1/users/", value)
    except (OSError, urllib.error.URLError) as exc:
        raise RotationError("HTTPS token smoke test connection failed.") from exc
    if (allowed, denied) != (200, 403):
        raise RotationError("HTTPS authorized/denied verification failed.")


def sync_dir() -> None:
    fd = os.open(ROOT, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def stage(value: bytes) -> Path:
    fd, name = tempfile.mkstemp(prefix=".token-new-", dir=str(ROOT))
    result = Path(name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as writer:
            writer.write(value + b"\n")
            writer.flush()
            os.fsync(writer.fileno())
    except BaseException:
        result.unlink(missing_ok=True)
        raise
    return result


def recover_previous() -> None:
    if not PREVIOUS.exists():
        return
    old = load(PREVIOUS)
    if not TOKEN.exists():
        os.replace(PREVIOUS, TOKEN)
    elif old != load(TOKEN):
        revoke(old)
        PREVIOUS.unlink()
    else:
        PREVIOUS.unlink()
    sync_dir()
    print("Recovered interrupted token switch safely.")


def rotate() -> None:
    if os.geteuid() != 0:
        raise RotationError("Rotation must run as root.")
    if ROOT.is_symlink():
        raise RotationError("Credential directory cannot be a symlink.")
    ROOT.mkdir(parents=True, mode=0o700, exist_ok=True)
    meta = ROOT.stat()
    if meta.st_uid != 0 or (meta.st_mode & 0o777) != 0o700:
        raise RotationError("Credential directory must be root owned 0700.")
    os.umask(0o077)
    fd = os.open(LOCK, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        recover_previous()
        current = load(TOKEN) if TOKEN.exists() else None
        if current is not None and time.time() - TOKEN.stat().st_mtime < INTERVAL:
            print("Current AIA token healthy; no rotation due.")
            return

        fresh: bytes | None = None
        temporary: Path | None = None
        promoted = False
        try:
            fresh = issue()
            if not PATTERN.fullmatch(fresh):
                raise RotationError("Backend issued invalid credential format.")
            verify(fresh)
            temporary = stage(fresh)
            if current is not None:
                os.link(TOKEN, PREVIOUS, follow_symlinks=False)
                sync_dir()
            os.replace(temporary, TOKEN)
            promoted = True
            sync_dir()
            if current is not None:
                revoke(current)
                PREVIOUS.unlink()
                sync_dir()
            print("AIA token verified and rotated; previous token revoked.")
        except Exception:
            if fresh is not None and not promoted:
                try:
                    revoke(fresh)
                except RotationError:
                    print("WARNING: unpromoted credential revocation failed.",
                          file=sys.stderr)
            raise
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


if __name__ == "__main__":
    try:
        rotate()
    except (RotationError, OSError, ValueError) as error:
        print(f"AIA rotation failed: {type(error).__name__}: {error}",
              file=sys.stderr)
        sys.exit(1)
