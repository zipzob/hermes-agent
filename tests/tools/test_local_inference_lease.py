import io
import os
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest


def test_default_lock_path_is_shared_across_profiles(tmp_path, monkeypatch):
    from tools.local_inference_lease import shared_local_inference_lock_path

    root = tmp_path / "hermes-root"
    monkeypatch.setenv(
        "HERMES_LOCAL_INFERENCE_LOCK_PATH",
        str(tmp_path / "must-not-override-production-path.lock"),
    )
    monkeypatch.setenv("HERMES_HOME", str(root / "profiles" / "one"))
    first = shared_local_inference_lock_path()
    monkeypatch.setenv("HERMES_HOME", str(root / "profiles" / "two"))
    second = shared_local_inference_lock_path()

    assert first == second == root / "local-inference" / "lease.lock"


def test_shared_lease_times_out_while_another_process_holds_it(tmp_path):
    from tools.local_inference_lease import LocalInferenceLeaseTimeout, local_inference_lease

    lock_path = tmp_path / "shared.lock"
    script = """
import sys, time
from tools.local_inference_lease import local_inference_lease
with local_inference_lease('holder', lock_path=sys.argv[1], timeout=1):
    print('ready', flush=True)
    time.sleep(30)
"""
    holder = subprocess.Popen(
        [sys.executable, "-c", script, str(lock_path)],
        cwd=Path(__file__).resolve().parents[2],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert holder.stdout is not None
        assert holder.stdout.readline().strip() == "ready"
        with pytest.raises(LocalInferenceLeaseTimeout):
            with local_inference_lease("contender", lock_path=lock_path, timeout=0.1):
                pass
    finally:
        holder.terminate()
        holder.wait(timeout=5)


def test_shared_lease_recovers_after_owner_process_exits(tmp_path):
    from tools.local_inference_lease import local_inference_lease

    lock_path = tmp_path / "shared.lock"
    script = """
import sys
from tools.local_inference_lease import local_inference_lease
with local_inference_lease('short-lived', lock_path=sys.argv[1], timeout=1):
    pass
"""
    subprocess.run(
        [sys.executable, "-c", script, str(lock_path)],
        cwd=Path(__file__).resolve().parents[2],
        check=True,
        timeout=5,
    )

    with local_inference_lease("next-owner", lock_path=lock_path, timeout=0.5):
        metadata = lock_path.read_text(encoding="utf-8")
        assert '"owner": "next-owner"' in metadata
        assert f'"pid": {os.getpid()}' in metadata

    assert lock_path.read_text(encoding="utf-8") == ""


def test_windows_lock_adapter_always_locks_byte_zero(monkeypatch):
    from tools import local_inference_lease as lease_module

    calls = []

    class Handle(io.StringIO):
        def fileno(self):
            return 42

    handle = Handle("existing metadata")

    def locking(fd, mode, length):
        calls.append((fd, mode, length, handle.tell()))

    fake_msvcrt = SimpleNamespace(LK_NBLCK=1, LK_UNLCK=2, locking=locking)
    monkeypatch.setattr(lease_module, "fcntl", None)
    monkeypatch.setattr(lease_module, "msvcrt", fake_msvcrt)

    assert lease_module._acquire_file_lock(handle) is True
    lease_module._release_file_lock(handle)

    assert calls == [(42, 1, 1, 0), (42, 2, 1, 0)]


def test_normalize_ollama_base_url_removes_openai_suffix():
    from tools.local_inference_lease import normalize_ollama_base_url

    assert normalize_ollama_base_url("http://127.0.0.1:11434/v1/") == "http://127.0.0.1:11434"
    assert normalize_ollama_base_url("http://localhost:11434") == "http://localhost:11434"


def test_unload_ollama_models_lists_then_expires_each_model(monkeypatch):
    from tools import local_inference_lease as lease_module

    calls = []

    class Response:
        def __init__(self, body):
            self._body = body

        def read(self):
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(request, timeout):
        calls.append((request.full_url, request.data, timeout))
        if request.full_url.endswith("/api/ps"):
            return Response(b'{"models":[{"name":"memory-model"},{"model":"other-model"}]}')
        return Response(b"{}")

    monkeypatch.setattr(lease_module.urllib.request, "urlopen", fake_urlopen)

    unloaded = lease_module.unload_ollama_models("http://127.0.0.1:11434/v1", timeout=2)

    assert unloaded == ["memory-model", "other-model"]
    assert calls[0][0] == "http://127.0.0.1:11434/api/ps"
    assert all(b'"keep_alive": 0' in data for _, data, _ in calls[1:])
