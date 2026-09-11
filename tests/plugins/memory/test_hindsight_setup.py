"""Dependency contract for interactive Hindsight setup."""

from types import SimpleNamespace

import pytest

from plugins.memory.hindsight import setup
from tools import lazy_deps


class _StopAfterInstall(Exception):
    pass


def test_local_embedded_setup_installs_mcp2_compatible_runtime(monkeypatch, tmp_path):
    selections = iter(["local_embedded", "ollama"])
    captured = []

    monkeypatch.setattr(setup, "_select", lambda *args, **kwargs: next(selections))

    def capture_install(specs, *, timeout):
        captured.append((specs, timeout))
        raise _StopAfterInstall

    monkeypatch.setattr(lazy_deps, "install_specs", capture_install)
    provider = SimpleNamespace(_config={})

    with pytest.raises(_StopAfterInstall):
        setup.run_setup(provider, str(tmp_path), {"memory": {}})

    assert captured == [
        (["hindsight-all", "fastmcp==4.0.0b3"], 120),
    ]
