"""Tests for ``hermes_cli.voice`` — the TUI gateway's voice wrapper.

The module is imported *lazily* by ``tui_gateway/server.py`` so that a
box with missing audio deps fails at call time (returning a clean RPC
error) rather than at gateway startup. These tests therefore only
assert the public contract the gateway depends on: the three symbols
exist, ``stop_and_transcribe`` is a no-op when nothing is recording,
and ``speak_text`` tolerates empty input without touching the provider
stack.
"""


import json

import pytest


class TestPublicAPI:
    def test_gateway_symbols_importable(self):
        """Match the exact import shape tui_gateway/server.py uses."""
        from hermes_cli.voice import (
            speak_text,
            start_recording,
            stop_and_transcribe,
        )

        assert callable(start_recording)
        assert callable(stop_and_transcribe)
        assert callable(speak_text)


class TestNormalizeVoiceRecordKeyForPromptToolkit:
    """Round-9 Copilot review regression on #19835.

    Classic CLI only normalized ``ctrl+`` / ``alt+``, so TUI-valid
    aliases like ``control+``, ``option+``, ``opt+`` silently bound a
    different (or no) shortcut in the CLI. Normalizer now maps the
    same set of aliases the TUI parser accepts, so one config value
    binds identically in both runtimes.
    """



    def test_non_string_falls_back_to_default(self):
        from hermes_cli.voice import normalize_voice_record_key_for_prompt_toolkit

        assert normalize_voice_record_key_for_prompt_toolkit(None) == "c-b"
        assert normalize_voice_record_key_for_prompt_toolkit(1) == "c-b"
        assert normalize_voice_record_key_for_prompt_toolkit(True) == "c-b"
        assert normalize_voice_record_key_for_prompt_toolkit({}) == "c-b"


    def test_super_win_fall_back_to_default_in_cli(self):
        """prompt_toolkit has no super modifier, so ``super+b`` / ``win+o``
        would crash the classic CLI at startup if passed through. Fall
        back to the documented default; the CLI binding site is
        expected to warn so users know the shortcut is TUI-only
        (Copilot round-11 on #19835)."""
        from hermes_cli.voice import normalize_voice_record_key_for_prompt_toolkit

        assert normalize_voice_record_key_for_prompt_toolkit("super+b") == "c-b"
        assert normalize_voice_record_key_for_prompt_toolkit("win+o") == "c-b"
        assert normalize_voice_record_key_for_prompt_toolkit("windows+o") == "c-b"

    # Round-10 Copilot review regressions on #19835.



    # Round-14 Copilot review regression on #19835. On macOS the TUI
    # parser rejects alt+c/d/l because hermes-ink reports Alt as
    # ``key.meta`` and isActionMod(darwin) accepts it. The CLI
    # normalizer must mirror that platform-gated rejection so shared
    # configs like ``option+c`` don't bind Alt+C in the CLI while the
    # TUI falls back to Ctrl+B.


class TestVoiceRecordKeyFromConfig:
    """Round-11 Copilot review regression on #19835.

    ``load_config()`` preserves YAML scalar overrides, so a hand-edited
    ``voice: true`` or ``voice: cmd+b`` made the naive
    ``cfg.get('voice', {}).get('record_key')`` chain raise
    AttributeError before voice could run. The shape-safe extractor
    returns None for every malformed shape so the call-site fallback
    (``normalize_…`` / ``format_…``) surfaces the documented default.
    """




    def test_missing_record_key_returns_none(self):
        from hermes_cli.voice import voice_record_key_from_config

        assert voice_record_key_from_config({"voice": {"beep_enabled": True}}) is None
        assert voice_record_key_from_config({}) is None

    def test_normalizer_accepts_extractor_output_directly(self):
        """voice_record_key_from_config + normalize_… must compose —
        None / non-string scalars all fall back to c-b."""
        from hermes_cli.voice import (
            normalize_voice_record_key_for_prompt_toolkit,
            voice_record_key_from_config,
        )

        for raw in (None, True, 1, "cmd+b", ["ctrl+b"]):
            extracted = voice_record_key_from_config({"voice": raw})
            assert normalize_voice_record_key_for_prompt_toolkit(extracted) == "c-b"


class TestFormatVoiceRecordKeyForStatus:
    """Round-10 Copilot review regression on #19835.

    ``/voice status`` used to print the raw scalar (``True`` / ``1``)
    for non-string configs even though the actual binding falls back
    to Ctrl+B. The formatter routes through the same normalizer so
    status always matches what the CLI actually binds.
    """

    def test_ctrl_and_alt_letter_keys_render_canonically(self):
        from hermes_cli.voice import format_voice_record_key_for_status

        assert format_voice_record_key_for_status("ctrl+b") == "Ctrl+B"
        assert format_voice_record_key_for_status("ctrl+o") == "Ctrl+O"
        assert format_voice_record_key_for_status("alt+r") == "Alt+R"



    def test_non_string_scalar_falls_back_to_ctrl_b_label(self):
        from hermes_cli.voice import format_voice_record_key_for_status

        # Copilot round-10 regression: previously /voice status printed
        # the raw scalar ("True" / "1") even though the actual binding
        # fell back to Ctrl+B.
        assert format_voice_record_key_for_status(True) == "Ctrl+B"
        assert format_voice_record_key_for_status(1) == "Ctrl+B"
        assert format_voice_record_key_for_status(None) == "Ctrl+B"
        assert format_voice_record_key_for_status({}) == "Ctrl+B"

    def test_malformed_configs_fall_back_to_ctrl_b(self):
        from hermes_cli.voice import format_voice_record_key_for_status

        assert format_voice_record_key_for_status("ctrl+spcae") == "Ctrl+B"
        assert format_voice_record_key_for_status("ctrl+alt+r") == "Ctrl+B"
        assert format_voice_record_key_for_status("") == "Ctrl+B"
        assert format_voice_record_key_for_status("  ") == "Ctrl+B"


class TestStopWithoutStart:
    def test_returns_none_when_no_recording_active(self, monkeypatch):
        """Idempotent no-op: stop before start must not raise or touch state."""
        import hermes_cli.voice as voice

        monkeypatch.setattr(voice, "_recorder", None)

        assert voice.stop_and_transcribe() is None


@pytest.mark.real_audio_playback
class TestSpeakTextGuards:
    @pytest.mark.parametrize("text", ["", "   ", "\n\t  "])
    def test_empty_text_is_noop(self, text):
        """Empty / whitespace-only text must return without importing tts_tool
        (the gateway spawns a thread per call, so a no-op on empty input
        keeps the thread pool from churning on trivial inputs)."""
        from hermes_cli.voice import speak_text

        # Should simply return None without raising.
        assert speak_text(text) is None

    def test_speak_text_uses_returned_tts_file_path(self, monkeypatch):
        import hermes_cli.voice as voice
        from tools import tts_tool

        played = []
        returned_path = "/tmp/hermes_voice/actual.flac"

        monkeypatch.setattr(
            tts_tool,
            "text_to_speech_tool",
            lambda **_kwargs: f'{{"success": true, "file_path": "{returned_path}"}}',
        )
        monkeypatch.setattr(voice.os, "makedirs", lambda *_args, **_kwargs: None)
        monkeypatch.setattr(voice.os.path, "isfile", lambda path: path == returned_path)
        monkeypatch.setattr(voice.os.path, "getsize", lambda _path: 1000)
        monkeypatch.setattr(voice.os, "unlink", lambda _path: None)
        monkeypatch.setattr(voice, "play_audio_file", lambda path: played.append(path))

        assert voice.speak_text("Hello world") is None
        assert played == [returned_path]

    def test_speak_text_plays_returned_file_paths(self, monkeypatch):
        import hermes_cli.voice as voice
        from tools import tts_tool

        played = []

        def fake_tts(**kwargs):
            requested_path = kwargs["output_path"]
            ogg_path = requested_path.rsplit(".", 1)[0] + ".ogg"
            # The tool may return a different path than the requested MP3;
            # the result's file_paths is authoritative for playback.
            return json.dumps({
                "success": True,
                "file_path": ogg_path,
                "file_paths": [ogg_path],
            })

        monkeypatch.setattr(tts_tool, "text_to_speech_tool", fake_tts)
        monkeypatch.setattr(voice.os, "makedirs", lambda *_args, **_kwargs: None)
        monkeypatch.setattr(voice.os.path, "isfile", lambda _path: True)
        monkeypatch.setattr(voice.os.path, "getsize", lambda _path: 1000)
        monkeypatch.setattr(voice.os, "unlink", lambda _path: None)
        monkeypatch.setattr(voice, "play_audio_file", lambda path: played.append(path))

        assert voice.speak_text("Hello world") is None
        # Should play the path from the result, not the requested MP3 path
        assert len(played) == 1
        assert played[0].endswith(".ogg")


class TestContinuousAPI:
    """Continuous (VAD) mode API — CLI-parity loop entry points."""



    def test_stop_continuous_idempotent_when_inactive(self, monkeypatch):
        """stop_continuous must not raise when no loop is active — the
        gateway's voice.toggle off path calls it unconditionally."""
        import hermes_cli.voice as voice

        monkeypatch.setattr(voice, "_continuous_active", False)
        monkeypatch.setattr(voice, "_continuous_recorder", None)

        # Should return cleanly without exceptions
        assert voice.stop_continuous() is None
        assert voice.is_continuous_active() is False

    def test_double_start_is_idempotent(self, monkeypatch):
        """A second start_continuous while already active is a no-op — prevents
        two overlapping capture threads fighting over the microphone when the
        UI double-fires (e.g. both /voice on and Ctrl+B within the same tick)."""
        import hermes_cli.voice as voice

        monkeypatch.setattr(voice, "_continuous_active", True)
        called = {"n": 0}

        class FakeRecorder:
            def start(self, on_silence_stop=None, on_silence_progress=None, on_cutoff=None):
                called["n"] += 1

            def cancel(self):
                pass

        monkeypatch.setattr(voice, "_continuous_recorder", FakeRecorder())

        started = voice.start_continuous(on_transcript=lambda _t: None)

        # The guard inside start_continuous short-circuits before rec.start()
        assert started is True
        assert called["n"] == 0



class TestContinuousLoopSimulation:
    """End-to-end simulation of the VAD loop with a fake recorder.

    Proves auto-restart works: the silence callback must trigger transcribe →
    on_transcript → re-call rec.start(on_silence_stop=same_cb). Also covers
    the 3-strikes no-speech halt.
    """

    @pytest.fixture
    def fake_recorder(self, monkeypatch):
        import hermes_cli.voice as voice

        # Reset module state between tests.
        monkeypatch.setattr(voice, "_continuous_active", False)
        monkeypatch.setattr(voice, "_continuous_stopping", False)
        monkeypatch.setattr(voice, "_continuous_recorder", None)
        monkeypatch.setattr(voice, "_continuous_no_speech_count", 0)
        monkeypatch.setattr(voice, "_continuous_on_transcript", None)
        monkeypatch.setattr(voice, "_continuous_on_status", None)
        monkeypatch.setattr(voice, "_continuous_on_capture_stopped", None, raising=False)
        monkeypatch.setattr(voice, "_continuous_on_silence_progress", None)
        monkeypatch.setattr(voice, "_continuous_on_cutoff", None)
        monkeypatch.setattr(voice, "_continuous_on_silent_limit", None)
        monkeypatch.setattr(voice, "_continuous_auto_restart", True, raising=False)
        monkeypatch.setattr(voice, "_voice_busy_probe", None, raising=False)
        monkeypatch.setattr(voice, "_play_beep", lambda *_, **__: None)

        class FakeRecorder:
            _silence_threshold = 200
            _silence_duration = 3.0
            is_recording = False

            def __init__(self):
                self.start_calls = 0
                self.last_callback = None
                self.stopped = 0
                self.cancelled = 0
                self.shutdowns = 0
                # Preset WAV path returned by stop()
                self.next_stop_wav = "/tmp/fake.wav"
                self.fail_stop = False
                self.fail_next_start = False

            def start(self, on_silence_stop=None, on_silence_progress=None, on_cutoff=None):
                if self.fail_next_start:
                    self.fail_next_start = False
                    raise RuntimeError("boom")
                self.start_calls += 1
                self.last_callback = on_silence_stop
                self.is_recording = True

            def stop(self):
                if self.fail_stop:
                    raise RuntimeError("stop failed")
                self.stopped += 1
                self.is_recording = False
                return self.next_stop_wav

            def cancel(self):
                self.cancelled += 1
                self.is_recording = False

            def shutdown(self):
                self.shutdowns += 1

        rec = FakeRecorder()
        monkeypatch.setattr(voice, "create_audio_recorder", lambda: rec)
        # Skip real file ops in the silence callback.
        monkeypatch.setattr(voice.os.path, "isfile", lambda _p: False)
        return rec

    def test_loop_auto_restarts_after_transcript(self, fake_recorder, monkeypatch):
        import hermes_cli.voice as voice

        monkeypatch.setattr(
            voice,
            "transcribe_recording",
            lambda _p: {"success": True, "transcript": "hello world"},
        )
        monkeypatch.setattr(voice, "is_whisper_hallucination", lambda _t: False)

        transcripts = []
        statuses = []

        voice.start_continuous(
            on_transcript=lambda t: transcripts.append(t),
            on_status=lambda s: statuses.append(s),
        )

        assert fake_recorder.start_calls == 1
        assert statuses == ["listening"]

        # Simulate AudioRecorder's silence detector firing.
        fake_recorder.last_callback()

        assert transcripts == ["hello world"]
        assert fake_recorder.start_calls == 2  # auto-restarted
        assert statuses == ["listening", "transcribing", "listening"]
        assert voice.is_continuous_active() is True

        voice.stop_continuous()






    def test_capture_stopped_callback_runs_after_stop_before_transcription(
        self, fake_recorder, monkeypatch
    ):
        import hermes_cli.voice as voice

        events = []
        original_stop = fake_recorder.stop

        def tracked_stop():
            events.append("stop")
            return original_stop()

        fake_recorder.stop = tracked_stop
        monkeypatch.setattr(
            voice,
            "transcribe_recording",
            lambda _p: events.append("transcribe")
            or {"success": True, "transcript": "hello world"},
        )

        voice.start_continuous(
            on_transcript=lambda _text: None,
            on_capture_stopped=lambda: events.append("capture_stopped"),
        )
        fake_recorder.last_callback()

        assert events[:3] == ["stop", "capture_stopped", "transcribe"]

        voice.stop_continuous()

    def test_capture_stopped_callback_waits_for_stream_shutdown(
        self, fake_recorder, monkeypatch, tmp_path
    ):
        import threading

        import hermes_cli.voice as voice
        from tools.voice_capture_lease import acquire_voice_capture_lease

        shutdown_entered = threading.Event()
        allow_shutdown = threading.Event()
        capture_stopped = threading.Event()
        lock_path = tmp_path / "voice-capture.lock"
        owning_lease = acquire_voice_capture_lease(
            "record", session_id="first", lock_path=lock_path
        )
        assert owning_lease is not None

        def blocked_shutdown():
            shutdown_entered.set()
            assert allow_shutdown.wait(timeout=2)
            fake_recorder.shutdowns += 1

        def release_capture():
            owning_lease.release()
            capture_stopped.set()

        fake_recorder.shutdown = blocked_shutdown
        monkeypatch.setattr(
            voice,
            "transcribe_recording",
            lambda _p: {"success": True, "transcript": "hello world"},
        )
        voice.start_continuous(
            on_transcript=lambda _text: None,
            on_capture_stopped=release_capture,
            auto_restart=False,
        )

        stop_thread = threading.Thread(target=fake_recorder.last_callback)
        stop_thread.start()
        try:
            assert shutdown_entered.wait(timeout=1)
            assert capture_stopped.is_set() is False
            assert acquire_voice_capture_lease(
                "full_duplex", session_id="second", lock_path=lock_path
            ) is None
        finally:
            allow_shutdown.set()
            stop_thread.join(timeout=2)

        assert not stop_thread.is_alive()
        assert fake_recorder.shutdowns == 1
        assert capture_stopped.is_set() is True
        contender = acquire_voice_capture_lease(
            "full_duplex", session_id="second", lock_path=lock_path
        )
        assert contender is not None
        contender.release()

    def test_capture_stopped_callback_is_not_released_when_shutdown_fails(
        self, fake_recorder, monkeypatch
    ):
        import hermes_cli.voice as voice

        def failed_shutdown():
            raise RuntimeError("stream still open")

        fake_recorder.shutdown = failed_shutdown
        capture_stopped = []
        monkeypatch.setattr(
            voice,
            "transcribe_recording",
            lambda _p: {"success": True, "transcript": "hello world"},
        )
        voice.start_continuous(
            on_transcript=lambda _text: None,
            on_capture_stopped=lambda: capture_stopped.append(True),
            auto_restart=False,
        )

        fake_recorder.last_callback()

        assert capture_stopped == []

    def test_capture_stopped_callback_is_not_released_when_shutdown_times_out(
        self, fake_recorder, monkeypatch
    ):
        import hermes_cli.voice as voice

        fake_recorder.shutdown = lambda: False
        capture_stopped = []
        monkeypatch.setattr(
            voice,
            "transcribe_recording",
            lambda _p: {"success": True, "transcript": "hello world"},
        )
        voice.start_continuous(
            on_transcript=lambda _text: None,
            on_capture_stopped=lambda: capture_stopped.append(True),
            auto_restart=False,
        )

        fake_recorder.last_callback()

        assert capture_stopped == []

    @pytest.mark.parametrize("keep_audio", [False, True])
    def test_pulse_wait_timeout_keeps_capture_lease(
        self, monkeypatch, tmp_path, keep_audio
    ):
        import subprocess
        from unittest.mock import MagicMock

        import hermes_cli.voice as voice
        from tools.voice_capture_lease import acquire_voice_capture_lease
        from tools.voice_mode import AudioRecorder

        lock_path = tmp_path / "voice-capture.lock"
        owner = acquire_voice_capture_lease(
            "full_duplex", session_id="first", lock_path=lock_path
        )
        assert owner is not None

        fallback = tmp_path / "fallback.flac"
        fallback.write_bytes(b"recording")
        proc = MagicMock()
        proc.wait.side_effect = subprocess.TimeoutExpired("parec", 2)
        recorder = AudioRecorder()
        recorder._fallback_process = proc
        recorder._fallback_path = str(fallback)
        recorder._stream = "pulse-fallback"
        recorder._recording = True
        monkeypatch.setattr(voice, "_continuous_capture_stopped_notified", False)

        try:
            voice._shutdown_continuous_capture(
                recorder,
                keep_audio=keep_audio,
                on_capture_stopped=owner.release,
            )
            contender = acquire_voice_capture_lease(
                "full_duplex", session_id="second", lock_path=lock_path
            )
            assert contender is None
            assert recorder._fallback_process is proc
            assert recorder._stream == "pulse-fallback"
            assert fallback.exists()
        finally:
            owner.release()

    def test_termux_stop_failure_keeps_capture_lease(
        self, monkeypatch, tmp_path
    ):
        import hermes_cli.voice as voice
        from tools.voice_capture_lease import acquire_voice_capture_lease
        from tools.voice_mode import TermuxAudioRecorder

        lock_path = tmp_path / "voice-capture.lock"
        owner = acquire_voice_capture_lease(
            "full_duplex", session_id="first", lock_path=lock_path
        )
        assert owner is not None

        fallback = tmp_path / "recording.aac"
        fallback.write_bytes(b"recording")
        recorder = TermuxAudioRecorder()
        recorder._recording = True
        recorder._recording_path = str(fallback)
        monkeypatch.setattr(recorder, "_stop_termux_recording", lambda: False)
        monkeypatch.setattr(voice, "_continuous_capture_stopped_notified", False)

        try:
            voice._shutdown_continuous_capture(
                recorder,
                keep_audio=True,
                on_capture_stopped=owner.release,
            )
            contender = acquire_voice_capture_lease(
                "full_duplex", session_id="second", lock_path=lock_path
            )
            assert contender is None
            assert recorder.is_recording is True
            assert recorder._recording_path == str(fallback)
            assert fallback.exists()
        finally:
            owner.release()

    def test_overlapping_stops_notify_only_after_owning_shutdown(
        self, fake_recorder, monkeypatch
    ):
        import threading
        import time

        import hermes_cli.voice as voice

        first_stop_entered = threading.Event()
        allow_first_stop = threading.Event()
        callback_events = []
        stop_calls = 0
        original_stop = fake_recorder.stop

        def blocked_first_stop():
            nonlocal stop_calls
            stop_calls += 1
            if stop_calls == 1:
                first_stop_entered.set()
                assert allow_first_stop.wait(timeout=2)
            return original_stop()

        fake_recorder.stop = blocked_first_stop
        monkeypatch.setattr(
            voice,
            "transcribe_recording",
            lambda _p: {"success": True, "transcript": "hello world"},
        )

        voice.start_continuous(
            on_transcript=lambda _text: None,
            on_capture_stopped=lambda: callback_events.append("capture_stopped"),
            auto_restart=False,
        )
        automatic_stop = threading.Thread(target=fake_recorder.last_callback)
        automatic_stop.start()
        assert first_stop_entered.wait(timeout=1)

        explicit_stop = threading.Thread(
            target=lambda: voice.stop_continuous(force_transcribe=True)
        )
        explicit_stop.start()
        try:
            time.sleep(0.05)
            assert callback_events == []
        finally:
            allow_first_stop.set()
            automatic_stop.join(timeout=2)
            explicit_stop.join(timeout=2)

        assert not automatic_stop.is_alive()
        assert not explicit_stop.is_alive()
        assert callback_events == ["capture_stopped"]

    def test_cancel_without_transcription_does_not_play_completion_beep(
        self, fake_recorder, monkeypatch
    ):
        import hermes_cli.voice as voice

        events = []
        monkeypatch.setattr(
            voice,
            "_play_beep",
            lambda frequency, count=1: events.append((frequency, count)),
        )

        voice.start_continuous(on_transcript=lambda _text: None)
        events.clear()  # Ignore the recording-start cue.
        voice.stop_continuous(force_transcribe=False)

        assert fake_recorder.cancelled == 1
        assert events == []

    def test_auto_restart_false_stops_after_first_transcript(self, fake_recorder, monkeypatch):
        import hermes_cli.voice as voice

        monkeypatch.setattr(
            voice,
            "transcribe_recording",
            lambda _p: {"success": True, "transcript": "single shot"},
        )
        monkeypatch.setattr(voice, "is_whisper_hallucination", lambda _t: False)

        transcripts = []
        statuses = []

        voice.start_continuous(
            on_transcript=lambda t: transcripts.append(t),
            on_status=lambda s: statuses.append(s),
            auto_restart=False,
        )
        fake_recorder.last_callback()

        assert transcripts == ["single shot"]
        assert fake_recorder.start_calls == 1
        assert statuses == ["listening", "transcribing", "idle"]
        assert voice.is_continuous_active() is False

    def test_auto_restart_false_retains_silent_strikes_across_starts(
        self, fake_recorder, monkeypatch
    ):
        import hermes_cli.voice as voice

        monkeypatch.setattr(
            voice,
            "transcribe_recording",
            lambda _p: {"success": True, "transcript": ""},
        )
        monkeypatch.setattr(voice, "is_whisper_hallucination", lambda _t: False)

        silent_limit_fired = []

        for _ in range(3):
            voice.start_continuous(
                on_transcript=lambda _t: None,
                on_silent_limit=lambda: silent_limit_fired.append(True),
                auto_restart=False,
            )
            fake_recorder.last_callback()

        assert silent_limit_fired == [True]
        assert voice.is_continuous_active() is False
        assert fake_recorder.start_calls == 3

    def test_force_transcribe_stop_delivers_current_buffer(self, fake_recorder, monkeypatch):
        import hermes_cli.voice as voice

        class ImmediateThread:
            def __init__(self, target, daemon=False):
                self.target = target

            def start(self):
                self.target()

        monkeypatch.setattr(voice.threading, "Thread", ImmediateThread)
        monkeypatch.setattr(
            voice,
            "transcribe_recording",
            lambda _p: {"success": True, "transcript": "manual stop"},
        )
        monkeypatch.setattr(voice, "is_whisper_hallucination", lambda _t: False)

        transcripts = []
        statuses = []

        voice.start_continuous(
            on_transcript=lambda t: transcripts.append(t),
            on_status=lambda s: statuses.append(s),
        )
        voice.stop_continuous(force_transcribe=True)

        assert fake_recorder.stopped == 1
        assert transcripts == ["manual stop"]
        assert statuses == ["listening", "transcribing", "idle"]
        assert voice.is_continuous_active() is False

    def test_force_transcribe_empty_single_shots_hit_silent_limit(
        self, fake_recorder, monkeypatch
    ):
        import hermes_cli.voice as voice

        class ImmediateThread:
            def __init__(self, target, daemon=False):
                self.target = target

            def start(self):
                self.target()

        monkeypatch.setattr(voice.threading, "Thread", ImmediateThread)
        monkeypatch.setattr(
            voice,
            "transcribe_recording",
            lambda _p: {"success": True, "transcript": ""},
        )
        monkeypatch.setattr(voice, "is_whisper_hallucination", lambda _t: False)

        silent_limit_fired = []

        for _ in range(3):
            voice.start_continuous(
                on_transcript=lambda _t: None,
                on_silent_limit=lambda: silent_limit_fired.append(True),
                auto_restart=False,
            )
            voice.stop_continuous(force_transcribe=True)

        assert silent_limit_fired == [True]
        assert fake_recorder.stopped == 3
        assert voice._continuous_no_speech_count == 0

    def test_force_transcribe_empty_does_not_play_completion_beep(
        self, fake_recorder, monkeypatch
    ):
        import hermes_cli.voice as voice

        class ImmediateThread:
            def __init__(self, target, daemon=False):
                self.target = target

            def start(self):
                self.target()

        events = []
        monkeypatch.setattr(voice.threading, "Thread", ImmediateThread)
        monkeypatch.setattr(
            voice,
            "transcribe_recording",
            lambda _p: {"success": True, "transcript": ""},
        )
        monkeypatch.setattr(
            voice,
            "_play_beep",
            lambda frequency, count=1: events.append((frequency, count)),
        )

        voice.start_continuous(on_transcript=lambda _t: None, auto_restart=False)
        events.clear()  # Ignore the recording-start cue.
        voice.stop_continuous(force_transcribe=True)

        assert events == []

    def test_force_transcribe_valid_single_shot_resets_silent_strikes(
        self, fake_recorder, monkeypatch
    ):
        import hermes_cli.voice as voice

        class ImmediateThread:
            def __init__(self, target, daemon=False):
                self.target = target

            def start(self):
                self.target()

        monkeypatch.setattr(voice.threading, "Thread", ImmediateThread)
        monkeypatch.setattr(voice, "_continuous_no_speech_count", 2)
        monkeypatch.setattr(
            voice,
            "transcribe_recording",
            lambda _p: {"success": True, "transcript": "manual stop"},
        )
        monkeypatch.setattr(voice, "is_whisper_hallucination", lambda _t: False)

        transcripts = []
        silent_limit_fired = []

        voice.start_continuous(
            on_transcript=lambda t: transcripts.append(t),
            on_silent_limit=lambda: silent_limit_fired.append(True),
            auto_restart=False,
        )
        voice.stop_continuous(force_transcribe=True)

        assert transcripts == ["manual stop"]
        assert silent_limit_fired == []
        assert voice._continuous_no_speech_count == 0

    def test_force_transcribe_stop_failure_cancels_and_clears_stopping(
        self, fake_recorder, monkeypatch
    ):
        import hermes_cli.voice as voice

        class ImmediateThread:
            def __init__(self, target, daemon=False):
                self.target = target

            def start(self):
                self.target()

        monkeypatch.setattr(voice.threading, "Thread", ImmediateThread)
        fake_recorder.fail_stop = True

        statuses = []
        voice.start_continuous(
            on_transcript=lambda _t: None,
            on_status=lambda s: statuses.append(s),
        )
        voice.stop_continuous(force_transcribe=True)

        assert fake_recorder.cancelled == 1
        assert statuses == ["listening", "transcribing", "idle"]
        assert voice.is_continuous_active() is False
        assert voice._continuous_stopping is False

    def test_restart_failure_reports_idle(self, fake_recorder, monkeypatch):
        import hermes_cli.voice as voice

        monkeypatch.setattr(
            voice,
            "transcribe_recording",
            lambda _p: {"success": True, "transcript": "hello world"},
        )
        monkeypatch.setattr(voice, "is_whisper_hallucination", lambda _t: False)

        statuses = []
        voice.start_continuous(on_transcript=lambda _t: None, on_status=statuses.append)

        fake_recorder.fail_next_start = True
        fake_recorder.last_callback()

        assert statuses == ["listening", "transcribing", "idle"]
        assert voice.is_continuous_active() is False

    def test_silent_limit_halts_loop_after_three_strikes(self, fake_recorder, monkeypatch):
        import hermes_cli.voice as voice

        # Transcription returns no speech — fake_recorder.stop() returns the
        # path, but transcribe returns empty text, counting as silence.
        monkeypatch.setattr(
            voice,
            "transcribe_recording",
            lambda _p: {"success": True, "transcript": ""},
        )
        monkeypatch.setattr(voice, "is_whisper_hallucination", lambda _t: False)

        transcripts = []
        silent_limit_fired = []

        voice.start_continuous(
            on_transcript=lambda t: transcripts.append(t),
            on_silent_limit=lambda: silent_limit_fired.append(True),
        )

        # Fire silence callback 3 times
        for _ in range(3):
            fake_recorder.last_callback()

        assert transcripts == []
        assert silent_limit_fired == [True]
        assert voice.is_continuous_active() is False
        assert fake_recorder.cancelled >= 1


    def test_silent_cycles_do_not_count_while_tts_playing(self, fake_recorder, monkeypatch):
        """TTS speaking: the user is listening, not ignoring the mic."""
        import hermes_cli.voice as voice

        monkeypatch.setattr(
            voice,
            "transcribe_recording",
            lambda _p: {"success": True, "transcript": ""},
        )
        monkeypatch.setattr(voice, "is_whisper_hallucination", lambda _t: False)
        # Keep the TTS-wait re-arm path from blocking: _tts_playing cleared
        # means "playing"; use a tiny wait timeout via a fake event-like shim.
        monkeypatch.setattr(voice, "_voice_busy_probe", None)

        class _FakePlaying:
            def is_set(self):
                return False

            def wait(self, timeout=None):
                return True

        monkeypatch.setattr(voice, "_tts_playing", _FakePlaying())

        silent_limit_fired = []
        voice.start_continuous(
            on_transcript=lambda _t: None,
            on_silent_limit=lambda: silent_limit_fired.append(True),
        )
        for _ in range(4):
            fake_recorder.last_callback()

        assert silent_limit_fired == []
        assert voice._continuous_no_speech_count == 0
        voice.stop_continuous()






class TestBeepsEnabledTruthyStrings:
    """voice.beep_enabled quoted in YAML ("false"/"off") must disable beeps —
    bool("false") is True, so the gate must use utils.is_truthy_value (#49883)."""

    def _enabled_with(self, monkeypatch, value):
        import hermes_cli.voice as voice

        monkeypatch.setattr(
            "hermes_cli.config.load_config",
            lambda: {"voice": {"beep_enabled": value}},
        )
        return voice._beeps_enabled()

    def test_quoted_false_string_disables(self, monkeypatch):
        assert self._enabled_with(monkeypatch, "false") is False


    def test_real_booleans_pass_through(self, monkeypatch):
        assert self._enabled_with(monkeypatch, True) is True
        assert self._enabled_with(monkeypatch, False) is False


@pytest.mark.real_audio_playback
class TestSpeakTextStreamingDispatch:
    """speak_text routes through the generic streaming dispatcher (#58930)
    when a chunked streaming provider resolves — one dispatcher, zero
    parallel streaming implementations."""

    def test_streaming_provider_routes_through_dispatcher(self, monkeypatch):
        import hermes_cli.voice as voice
        import tools.tts_streaming as ts
        from tools import tts_tool

        streamed = []

        def fake_stream(text_queue, stop_event, done_event, *a, **k):
            while True:
                item = text_queue.get()
                if item is None:
                    break
                streamed.append(item)
            done_event.set()

        monkeypatch.setattr(
            ts, "resolve_streaming_provider", lambda cfg, preferred=None: object()
        )
        monkeypatch.setattr(tts_tool, "stream_tts_to_speaker", fake_stream)

        synced = []
        monkeypatch.setattr(
            tts_tool, "text_to_speech_tool", lambda **kw: synced.append(kw) or "{}"
        )

        assert voice.speak_text("Hello streaming world") is None
        assert streamed == ["Hello streaming world"]
        assert synced == [], "sync whole-file path must be skipped when streaming"


