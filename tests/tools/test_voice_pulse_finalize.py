"""Focused coverage for the upstream-preserving Pulse finalization port."""
from unittest.mock import MagicMock

import pytest

from tools import voice_mode


def recorder_with_capture(tmp_path, payload, returncode=0):
    path = tmp_path / "capture.flac"
    path.write_bytes(payload)
    proc = MagicMock(returncode=returncode)
    recorder = voice_mode.AudioRecorder()
    recorder._recording = True
    recorder._fallback_process = proc
    recorder._fallback_path = str(path)
    return recorder, proc, path


def test_successful_stop_saves_capture(tmp_path, monkeypatch):
    recorder, proc, source = recorder_with_capture(tmp_path, b"x" * 100)
    destination = tmp_path / "saved.flac"
    monkeypatch.setattr(voice_mode, "_new_recording_path", lambda ext: str(destination))
    assert recorder.stop() == str(destination)
    assert destination.read_bytes() == b"x" * 100
    assert not source.exists()
    assert recorder._fallback_process is None
    proc.wait.assert_called_once_with(timeout=5)
    proc.kill.assert_not_called()


def test_failed_capture_reports_stderr(tmp_path):
    recorder, proc, _ = recorder_with_capture(tmp_path, b"x" * 100, returncode=1)
    proc.stderr.read.return_value = b"capture failed"
    with pytest.raises(RuntimeError, match="capture failed"):
        recorder.stop()
    assert recorder._fallback_process is None


def test_short_capture_is_not_returned(tmp_path):
    recorder, _, _ = recorder_with_capture(tmp_path, b"short")
    assert recorder.stop() is None
    assert recorder._fallback_process is None
