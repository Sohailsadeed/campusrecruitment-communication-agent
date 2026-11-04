"""N3: failure-atomic upload storage.

A filesystem write and a database commit are not one transaction, and nothing here pretends they
are. What this module does instead is make every failure leave the disk in a state the database can
still describe:

* content is streamed into a unique temporary file **inside the destination directory**, so
  finalisation is a same-filesystem rename and no reader can ever observe a partial destination;
* the temporary descriptor is flushed, fsynced and closed **before** any rename or deletion;
* an occupied destination is preserved under a unique backup name before the new file is moved in,
  and that backup is restored if the request then fails;
* every path a request created is tracked, so cleanup can only ever remove or restore paths this
  request itself made — a file that was already there is never deleted;
* and because a *path* can change hands between publication and cleanup, cleanup re-checks that the
  destination still holds the bytes this request moved in (`owns_destination`) before it removes or
  overwrites it, so a losing request can never delete the file a committed request points at.

The windows that remain are listed in `MODULE RESIDUAL RISK` at the bottom of this file and are
reported, not hidden.
"""
from __future__ import annotations

import logging
import os
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:  # pragma: no cover - typing only, never imported at runtime
    from fastapi import UploadFile

logger = logging.getLogger("speakflow.upload_store")

#: Default read granularity. Uploads are copied through this buffer, never held whole in memory.
CHUNK_BYTES = 256 * 1024

# Markers are part of every name this module creates. They are what makes cleanup provably
# request-scoped, and they keep a temporary, backup or trash name from ever matching the
# AUTH-E clip grammar (`session_<sid>_..._<uid>.webm`) that the audio routes fullmatch.
_TEMP_MARK = ".upload-part-"
_BACKUP_MARK = ".upload-backup-"
_TRASH_MARK = ".upload-trash-"


class UploadError(RuntimeError):
    """Base for storage-side failures. Never an HTTP status by itself."""


class UploadTooLarge(UploadError):
    """The stream passed the byte budget the caller set. The route decides the status code."""

    def __init__(self, max_bytes: int) -> None:
        super().__init__(f"upload exceeded {max_bytes} bytes")
        self.max_bytes = max_bytes


# ---------------------------------------------------------------------------
# Per-destination serialisation
# ---------------------------------------------------------------------------
_LOCKS: dict = {}
_LOCKS_GUARD = threading.Lock()


def destination_lock_for(path: Path) -> threading.Lock:
    """The lock that serialises publication to this exact destination.

    Keyed per destination on purpose: only the preserve-then-replace section needs mutual
    exclusion, and the slow part (reading the client) happens outside it, so two uploads to
    different slots never wait on each other.
    """
    key = os.path.normcase(str(Path(path)))
    with _LOCKS_GUARD:
        lock = _LOCKS.get(key)
        if lock is None:
            lock = _LOCKS[key] = threading.Lock()
        return lock


def _atomic_replace(src: Path, dst: Path) -> None:
    """`os.replace`, in one patchable place. `os.rename` is not usable here: on Windows it raises
    FileExistsError when the destination exists, which is exactly the retry case."""
    os.replace(str(src), str(dst))


def _write_chunk(fd: int, chunk: bytes) -> int:
    """`os.write`, in one patchable place, so a test can fail the disk on a specific chunk.

    The return value is checked here rather than by each loop: a short write is a partial write, and
    a partial write that is counted as complete would publish a truncated recording as if it were the
    candidate's full answer. `os.write` returns 0 only when no progress is being made, so that is
    treated as a stalled disk rather than spun on forever.
    """
    written = 0
    length = len(chunk)
    while written < length:
        step = os.write(fd, chunk[written:])
        if step <= 0:
            raise OSError(f"upload write stalled after {written} of {length} bytes")
        written += step
    return written


def _marked(path: Path, mark: str) -> Path:
    return path.parent / f"{path.name}{mark}{uuid.uuid4().hex}"


def _file_identity(path: Path) -> Optional[tuple]:
    """`(st_dev, st_ino)` for one path, or None when the path is not there.

    This is how a request proves a destination is still *its* file. Size and name cannot do it: two
    staged uploads to one deterministic slot produce same-sized files at the same path. On NTFS the
    file index changes when a path is re-created and survives a rename, so the pair distinguishes
    the bytes this request moved in from the bytes another request moved in afterwards. Verified on
    this host (Windows, CPython 3.12) rather than assumed. `None` means the path holds nothing,
    which `superseded()` reads as "free to restore into", not as "someone else's".
    """
    try:
        stat = os.stat(str(path))
    except OSError:
        return None
    return (stat.st_dev, stat.st_ino)


def _open_temp(final_path: Path) -> "tuple[int, Path]":
    """A fresh, exclusive **binary** temp file beside `final_path`, with the process umask deciding
    the mode.

    O_EXCL means a collision cannot silently reuse another request's temp file, and creating the
    temp with a plain `open`-equivalent mode keeps the permissions an upload has always ended up
    with instead of tightening them behind the contract.

    O_BINARY is not decoration. Without it the CRT opens the descriptor in *text* mode on Windows
    and `os.write` translates every `0x0A` in the body to `0x0D 0x0A` — which silently rewrites a
    WebM recording, changes its length, and corrupts it, because a recording is arbitrary bytes and
    `0x0A` appears in real Matroska EBML IDs and in compressed frames. The uploaded bytes must reach
    the disk unmodified, so the descriptor is opened explicitly binary rather than inherited mode.
    `getattr` keeps the flag zero on platforms that have no text/binary distinction.
    """
    directory = final_path.parent
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    while True:
        candidate = _marked(final_path, _TEMP_MARK)
        try:
            fd = os.open(str(candidate), flags, 0o666)
        except FileExistsError:
            continue
        return fd, candidate


# ---------------------------------------------------------------------------
# One staged upload
# ---------------------------------------------------------------------------
@dataclass
class StagedUpload:
    """A destination this request is preparing. Owns nothing until it publishes."""

    target_dir: Path
    final_path: Path
    temp_path: Path
    _fd: Optional[int] = None
    closed: bool = False
    published: bool = False
    #: Set only when this request moved a pre-existing occupant aside. Restoring it is our job.
    backup_path: Optional[Path] = None
    #: The identity of the bytes this request moved in, captured under the destination lock. Nothing
    #: may touch `final_path` on the way out unless the file there still matches it.
    published_identity: Optional[tuple] = None

    # -- writing ---------------------------------------------------------
    def _guard(self) -> int:
        if self.closed or self._fd is None:
            raise UploadError("staged upload is already closed")
        return self._fd

    def write_from(self, source, *, max_bytes: Optional[int] = None,
                   chunk_bytes: Optional[int] = None) -> int:
        """Copy `source` (a binary file object) in bounded chunks. Synchronous callers only."""
        size = 0
        chunk_size = chunk_bytes or CHUNK_BYTES
        fd = self._guard()
        while True:
            chunk = source.read(chunk_size)
            if not chunk:
                break
            size += len(chunk)
            if max_bytes is not None and size > max_bytes:
                raise UploadTooLarge(max_bytes)
            _write_chunk(fd, chunk)
        return size

    async def write_from_upload(self, upload: "UploadFile", *, max_bytes: Optional[int] = None,
                                chunk_bytes: Optional[int] = None) -> int:
        """Copy a FastAPI `UploadFile` in bounded chunks.

        `read(n)` is always called with a size, so the whole body is never materialised — the
        failure-injection suite asserts on the sizes actually requested.
        """
        size = 0
        chunk_size = chunk_bytes or CHUNK_BYTES
        fd = self._guard()
        while True:
            chunk = await upload.read(chunk_size)
            if not chunk:
                break
            size += len(chunk)
            if max_bytes is not None and size > max_bytes:
                raise UploadTooLarge(max_bytes)
            _write_chunk(fd, chunk)
        return size

    # -- closing ---------------------------------------------------------
    def close(self) -> None:
        """Flush, fsync and close. Idempotent, and always runs before a rename or a delete."""
        if self.closed:
            return
        fd, self._fd = self._fd, None
        self.closed = True
        if fd is None:
            return
        try:
            os.fsync(fd)
        except OSError as exc:  # durability is best-effort; the write itself already succeeded
            logger.warning("upload fsync failed for %s: %s", self.temp_path.name, exc)
        finally:
            try:
                os.close(fd)
            except OSError as exc:
                logger.error("upload descriptor close failed for %s: %s", self.temp_path, exc)

    # -- publishing ------------------------------------------------------
    def publish(self) -> Path:
        """Move the completed temp file onto the destination, preserving any occupant first."""
        self.close()
        with destination_lock_for(self.final_path):
            if self.final_path.exists():
                self.backup_path = _marked(self.final_path, _BACKUP_MARK)
                _atomic_replace(self.final_path, self.backup_path)
            try:
                _atomic_replace(self.temp_path, self.final_path)
            except OSError:
                if self.backup_path is not None:
                    _restore(self.backup_path, self.final_path, context="publish rollback")
                    self.backup_path = None
                raise
            # Captured inside the same lock that serialises publication, so the identity recorded
            # here is the identity of the bytes this request put there and nothing else.
            self.published_identity = _file_identity(self.final_path)
            self.published = True
        return self.final_path

    # -- ownership -------------------------------------------------------
    def superseded(self) -> bool:
        """Whether some *other* request's bytes now sit at `final_path`.

        A path can change hands between publication and cleanup: two requests for one deterministic
        clip slot are serialised while each publishes, but nothing serialises the window between one
        request's publication and its commit. Without this test the losing request's rollback would
        delete, or overwrite with an older copy, the file the winning request's row now points at.
        An empty destination is not supersession: nothing stands to be destroyed there, and a backup
        this request holds must still be put back.
        """
        if not self.published or self.published_identity is None:
            return False
        occupant = _file_identity(self.final_path)
        return occupant is not None and occupant != self.published_identity

    # -- undo ------------------------------------------------------------
    def abort(self) -> None:
        """Remove what this request made, and put back what this request preserved. Nothing else."""
        self.close()
        if self.published:
            if self.superseded():
                # Another request owns this slot now. Its bytes are what the database describes, so
                # this request leaves the destination alone and only reclaims what is still its own.
                logger.error(
                    "upload abort left the destination alone (%s): this request published file index "
                    "%s, the slot holds %s",
                    self.final_path, self.published_identity[1],
                    _file_identity(self.final_path)[1],
                )
                if self.backup_path is not None:
                    # A copy of bytes a later publication has already displaced. Nothing references
                    # it, and the later request holds its own copy for its own restore.
                    _remove(self.backup_path, context="abort superseded backup")
                    self.backup_path = None
            elif self.backup_path is not None:
                trash = _marked(self.final_path, _TRASH_MARK)
                try:
                    _atomic_replace(self.final_path, trash)
                except OSError as exc:
                    logger.error("upload abort could not move the new file aside (%s): %s",
                                 self.final_path, exc)
                else:
                    _restore(self.backup_path, self.final_path, context="abort")
                    self.backup_path = None
                    _remove(trash, context="abort trash")
            else:
                # This request created the destination; removing it cannot destroy anyone's file.
                _remove(self.final_path, context="abort published file")
        _remove(self.temp_path, context="abort temp")

    def drop_backup(self) -> None:
        """Success path: the preserved copy is no longer needed."""
        if self.backup_path is not None:
            _remove(self.backup_path, context="committed backup")
            self.backup_path = None

    def owned_paths(self) -> List[Path]:
        paths = [self.temp_path, self.final_path]
        if self.backup_path is not None:
            paths.append(self.backup_path)
        return paths


def _restore(backup: Path, final: Path, *, context: str) -> None:
    """Put a preserved destination back. If the slot currently holds this request's file, that file
    goes to trash first so the restore cannot fail because of a busy destination."""
    if not backup.exists():
        logger.error("upload %s: preserved copy %s is gone; destination cannot be restored",
                     context, backup)
        return
    if final.exists():
        trash = _marked(final, _TRASH_MARK)
        try:
            _atomic_replace(final, trash)
        except OSError as exc:
            logger.error("upload %s: could not move %s aside: %s", context, final, exc)
            return
        try:
            _atomic_replace(backup, final)
        except OSError as exc:
            logger.error("upload %s: could not restore %s over %s: %s", context, backup, final, exc)
            return
        _remove(trash, context=f"{context} trash")
    else:
        try:
            _atomic_replace(backup, final)
        except OSError as exc:
            logger.error("upload %s: could not restore %s: %s", context, backup, exc)


def _remove(path: Path, *, context: str) -> None:
    """Delete one path this module created. Cleanup failures are logged, never swallowed quietly."""
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        logger.error("upload cleanup (%s) failed for %s: %s", context, path, exc)


def fault_label(exc: BaseException) -> str:
    """A path-free description of a storage failure, for the log line a report may surface.

    An `os.replace` or `os.open` error quotes the absolute paths it was given, so `str(exc)` cannot
    be interpolated into a route warning wholesale. The class and the errno are the two parts that
    still diagnose the fault — the full message stays in this module's own ERROR records, which are
    for the operator who has to find an orphan file, not for the candidate's session.
    """
    errno = getattr(exc, "errno", None)
    return f"{type(exc).__name__}[errno={errno}]" if errno is not None else type(exc).__name__


# ---------------------------------------------------------------------------
# Request-scoped bookkeeping
# ---------------------------------------------------------------------------
class UploadTransaction:
    """Every file one request may create, tracked so cleanup cannot reach anything else."""

    def __init__(self) -> None:
        self._items: List[StagedUpload] = []

    def stage(self, target_dir: Path, final_name: str) -> StagedUpload:
        directory = Path(target_dir)
        if not directory.is_dir():
            raise UploadError(f"destination directory does not exist: {directory.name}")
        fd, temp_path = _open_temp(directory / final_name)
        item = StagedUpload(target_dir=directory, final_path=directory / final_name,
                            temp_path=temp_path, _fd=fd)
        self._items.append(item)
        return item

    def discard(self, item: StagedUpload) -> None:
        """Undo one staged upload and forget it — the optional-audio case that keeps succeeding."""
        if item in self._items:
            self._items.remove(item)
        item.abort()

    def finalize(self) -> None:
        """The request committed: keep every published file, drop only our backups."""
        for item in list(self._items):
            item.drop_backup()
            if not item.published:
                item.abort()
        self._items.clear()

    def rollback(self) -> None:
        """The request failed: remove our files and restore destinations we displaced."""
        for item in reversed(self._items):
            item.abort()
        self._items.clear()

    @property
    def staged(self) -> List[StagedUpload]:
        return list(self._items)


def transaction() -> UploadTransaction:
    return UploadTransaction()


# ---------------------------------------------------------------------------
# MODULE RESIDUAL RISK (reported, not fixed here)
# 1. A process killed after publish() and before db.commit() leaves a complete file that no row
#    references. Only a reconciliation sweep against the database could reclaim it; none exists.
# 2. A cleanup that itself fails (busy destination on Windows, read-only directory) leaves the file
#    it could not remove. Every such failure is logged with the path; nothing is deleted blindly to
#    make the log quiet.
# 3. os.replace cannot publish over a destination another process has open for reading (Windows
#    PermissionError). The previous truncate-in-place code failed the same way, so this is parity,
#    not an improvement.
# 4. A truncated client body is indistinguishable from a complete one: the contract carries no
#    checksum or per-part length. This module guarantees that no partial *server-side write* is
#    published as a destination; it cannot guarantee the client sent everything.
# 5. `destination_lock_for` keeps one lock per destination path for the life of the process. Clip
#    slots are deterministic per (session, question, user), so the table grows with the number of
#    distinct slots this process has ever written to. It is small and bounded by upload count, but
#    it is not reclaimed; a long-lived worker accumulating it is a known, unaddressed limit.
# 6. Serialisation covers publication, not the whole request. Between one request publishing and
#    another committing, the slot can briefly hold the bytes of the request that will turn out to
#    have failed. Both requests then settle to the committed one's file (the loser restores its own
#    backup or leaves the winner's file alone), but a reader in that window sees a recording no row
#    has yet adopted. Closing it needs the destination lock held across the commit, which an
#    `async def` handler cannot do without blocking the event loop.
# 7. The supersession check trusts `(st_dev, st_ino)`. On a filesystem that reports a constant file
#    index the check always answers "still mine" and cleanup behaves as it did before the guard —
#    i.e. this is an improvement on filesystems that identify files, and neutral elsewhere. Not
#    verified beyond this host's NTFS temp directory.
# ---------------------------------------------------------------------------
