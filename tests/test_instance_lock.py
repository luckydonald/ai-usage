import os
import signal
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from ai_usage.instance_lock import InstanceLock, InstanceLockHeld


def test_second_acquire_fails_while_held(tmp_path: Path) -> None:
    path = tmp_path / "crawler.lock"
    with InstanceLock(path):
        with pytest.raises(InstanceLockHeld) as raised:
            InstanceLock(path).acquire()
        # end with
        assert raised.value.holder_pid == os.getpid()
    # end with
# end def


def test_acquire_after_release_and_with_stale_file(tmp_path: Path) -> None:
    path = tmp_path / "crawler.lock"
    with InstanceLock(path):
        pass
    # end with
    assert path.exists()
    with InstanceLock(path):
        pass
    # end with
# end def


def test_lock_survives_sigkill_of_holder(tmp_path: Path) -> None:
    path = tmp_path / "crawler.lock"
    script = textwrap.dedent(
        """
        import sys, time
        from pathlib import Path
        from ai_usage.instance_lock import InstanceLock
        InstanceLock(Path(sys.argv[1])).acquire()
        print("locked", flush=True)
        time.sleep(60)
        """
    )
    holder = subprocess.Popen([sys.executable, "-c", script, str(path)], stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout is not None
        assert holder.stdout.readline().strip() == "locked"
        with pytest.raises(InstanceLockHeld):
            InstanceLock(path).acquire()
        # end with
        holder.send_signal(signal.SIGKILL)
        holder.wait()
    finally:
        holder.kill()
        holder.wait()
    # end try
    assert path.exists()
    with InstanceLock(path):
        pass
    # end with
# end def
