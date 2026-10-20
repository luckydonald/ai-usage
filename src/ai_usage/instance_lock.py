"""Kill-resilient single-instance lock based on a kernel `flock`."""

import fcntl
import os
from pathlib import Path
from types import TracebackType


class InstanceLockHeld(Exception):
    def __init__(self, path: Path, holder_pid: int | None):
        self.path = path
        self.holder_pid = holder_pid
        super().__init__(f"{path} is locked by pid {holder_pid if holder_pid is not None else 'unknown'}")
    # end def
# end class


class InstanceLock:
    """
    Exclusive lock owned by the open file descriptor, not by the file's existence.

    The kernel drops it when the process dies (SIGKILL, crash), so a leftover lock file never blocks the next start.
    The file is deliberately never unlinked; the stored pid is informational only.
    """

    def __init__(self, path: Path):
        self.path = path
        self.fd: int | None = None
    # end def

    def read_holder_pid(self) -> int | None:
        try:
            return int(self.path.read_text().strip())
        except (OSError, ValueError):
            return None
        # end try
    # end def

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            raise InstanceLockHeld(self.path, self.read_holder_pid()) from None
        # end try
        os.ftruncate(fd, 0)
        os.write(fd, str(os.getpid()).encode())
        self.fd = fd
    # end def

    def release(self) -> None:
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
        # end if
    # end def

    def __enter__(self) -> "InstanceLock":
        self.acquire()
        return self
    # end def

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.release()
    # end def
# end class
