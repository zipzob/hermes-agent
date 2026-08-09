from __future__ import annotations

import json

from tools.voice_capture_lease import acquire_voice_capture_lease


def test_voice_capture_lease_excludes_second_owner_and_recovers_after_release(tmp_path):
    lock_path = tmp_path / "voice-capture.lock"

    first = acquire_voice_capture_lease(
        "record",
        session_id="session-one",
        lock_path=lock_path,
    )
    assert first is not None

    second = acquire_voice_capture_lease(
        "full_duplex",
        session_id="session-two",
        lock_path=lock_path,
    )
    assert second is None
    assert json.loads(lock_path.read_text(encoding="utf-8"))["session_id"] == "session-one"

    first.release()

    third = acquire_voice_capture_lease(
        "full_duplex",
        session_id="session-two",
        lock_path=lock_path,
    )
    assert third is not None
    third.release()


def test_stale_voice_capture_metadata_does_not_block_new_owner(tmp_path):
    lock_path = tmp_path / "voice-capture.lock"
    lock_path.write_text('{"owner":"stale","pid":1}', encoding="utf-8")

    lease = acquire_voice_capture_lease(
        "record",
        session_id="live-session",
        lock_path=lock_path,
    )

    assert lease is not None
    lease.release()
