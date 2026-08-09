from __future__ import annotations

import json
import stat
import sys
from contextlib import contextmanager, nullcontext
from email.message import Message
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


def test_bundled_plugin_registers_parakeet_provider():
    from agent import transcription_registry
    from hermes_cli.plugins import PluginManager, get_bundled_plugins_dir

    manager = PluginManager()
    manifests = manager._scan_directory(get_bundled_plugins_dir(), source="bundled")
    manifest = next(item for item in manifests if item.key == "transcription/parakeet")
    try:
        manager._load_plugin(manifest)
        assert manifest.kind == "backend"
        assert transcription_registry.get_provider("parakeet") is not None
    finally:
        transcription_registry._reset_for_tests()


def test_provider_health_starts_default_local_service(monkeypatch):
    from plugins.transcription.parakeet import provider as module
    from tools import lazy_deps

    events = []
    monkeypatch.setattr(lazy_deps, "ensure", lambda feature: None)
    monkeypatch.setattr(module, "_config", lambda: {})
    monkeypatch.setattr(module, "_service_token", lambda: "test-token")
    monkeypatch.setattr(
        module,
        "_health",
        lambda url, token, timeout=1.0: bool(events),
    )
    monkeypatch.setattr(
        module,
        "_spawn_service",
        lambda port, idle_timeout, token: events.append((port, idle_timeout, token)),
    )
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)

    assert module.ParakeetTranscriptionProvider().is_available() is True
    assert events == [(8765, 300.0, "test-token")]


def test_provider_does_not_spawn_when_lazy_runtime_is_unavailable(monkeypatch):
    from plugins.transcription.parakeet import provider as module
    from tools import lazy_deps

    def unavailable(_feature):
        raise lazy_deps.FeatureUnavailable(
            "stt.parakeet",
            ("torch",),
            "lazy installs disabled",
        )

    spawn = MagicMock()
    monkeypatch.setattr(lazy_deps, "ensure", unavailable)
    monkeypatch.setattr(module, "_spawn_service", spawn)

    assert module.ParakeetTranscriptionProvider().is_available() is False
    spawn.assert_not_called()


@pytest.mark.parametrize(
    "base_url",
    [
        "http://localhost:8765",
        "http://192.0.2.1:8765",
        "https://127.0.0.1:8765",
        "http://127.0.0.1:8765/path",
        "http://user@127.0.0.1:8765",
    ],
)
def test_provider_never_sends_token_or_audio_to_non_managed_origin(
    tmp_path,
    monkeypatch,
    base_url,
):
    from plugins.transcription.parakeet import provider as module

    audio = tmp_path / "voice.wav"
    audio.write_bytes(b"audio")
    token = MagicMock(return_value="must-not-leak")
    request = MagicMock()
    monkeypatch.setattr(module, "_config", lambda: {"base_url": base_url})
    monkeypatch.setattr(module, "_service_token", token)
    monkeypatch.setattr(module.urllib.request, "urlopen", request)

    result = module.ParakeetTranscriptionProvider().transcribe(str(audio))

    assert result["success"] is False
    assert "127.0.0.1" in result["error"]
    token.assert_not_called()
    request.assert_not_called()


def test_service_token_is_owner_only(tmp_path, monkeypatch):
    from plugins.transcription.parakeet import provider as module

    token_path = tmp_path / "parakeet.token"
    monkeypatch.setattr(module, "_service_token_path", lambda: token_path)

    token = module._service_token()

    assert len(token) >= 32
    assert token_path.read_text(encoding="utf-8").strip() == token
    assert stat.S_IMODE(token_path.stat().st_mode) == 0o600


def test_service_token_waits_for_concurrent_creator(tmp_path, monkeypatch):
    from plugins.transcription.parakeet import provider as module

    token_path = tmp_path / "parakeet.token"
    token_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(module, "_service_token_path", lambda: token_path)

    def finish_creation(_seconds):
        token_path.write_text("concurrent-token", encoding="utf-8")

    monkeypatch.setattr(module.time, "sleep", finish_creation)

    assert module._service_token() == "concurrent-token"
    assert stat.S_IMODE(token_path.stat().st_mode) == 0o600


def test_provider_posts_audio_and_maps_service_envelope(tmp_path, monkeypatch):
    from plugins.transcription.parakeet import provider as module

    audio = tmp_path / "voice.m4a"
    audio.write_bytes(b"audio-bytes")
    requests = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps({"success": True, "transcript": "hello"}).encode()

    def fake_urlopen(request, timeout):
        requests.append((request, timeout))
        return Response()

    monkeypatch.setattr(
        module,
        "_config",
        lambda: {
            "base_url": "http://127.0.0.1:9999",
            "request_timeout": 42,
        },
    )
    monkeypatch.setattr(module, "_service_token", lambda: "test-token")
    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)

    result = module.ParakeetTranscriptionProvider().transcribe(
        str(audio),
        model="nvidia/parakeet-test",
        language="de",
    )

    assert result == {"success": True, "transcript": "hello", "provider": "parakeet"}
    request, timeout = requests[0]
    assert request.full_url == "http://127.0.0.1:9999/transcribe"
    assert request.data == b"audio-bytes"
    assert request.headers["X-hermes-model"] == "nvidia/parakeet-test"
    assert request.headers["X-hermes-language"] == "de"
    assert request.headers["X-hermes-shared-gpu"] == "true"
    assert request.headers["Authorization"] == "Bearer test-token"
    assert timeout == 42


def test_shared_service_parks_model_before_releasing_lease(monkeypatch, tmp_path):
    from plugins.transcription.parakeet import service

    events = []

    @contextmanager
    def fake_lease(owner, timeout):
        events.append(("lease-enter", owner, timeout))
        try:
            yield
        finally:
            events.append(("lease-exit",))

    class Inputs(dict):
        def to(self, **_kwargs):
            return self

    class Processor:
        feature_extractor = SimpleNamespace(sampling_rate=16000)

        def __call__(self, *_args, **_kwargs):
            return Inputs(samples="fake")

        def decode(self, *_args, **_kwargs):
            return "shared transcript"

    class Model:
        device = "cuda"
        dtype = "float16"

        def generate(self, **_kwargs):
            events.append(("inference",))
            return SimpleNamespace(sequences=[[1]])

    fake_torch = SimpleNamespace(inference_mode=lambda: nullcontext())
    monkeypatch.setattr(service, "local_inference_lease", fake_lease)
    monkeypatch.setattr(
        service,
        "unload_ollama_models",
        lambda url: events.append(("ollama-unload", url)) or ["memory-model"],
    )
    monkeypatch.setattr(
        service,
        "_load_components",
        lambda *_args: (Processor(), Model(), fake_torch),
    )
    monkeypatch.setattr(service, "_decode_audio", lambda *_args: object())
    monkeypatch.setattr(
        service,
        "_park_components",
        lambda _torch: events.append(("parakeet-park",)),
    )

    result = service._transcribe(
        str(tmp_path / "voice.wav"),
        model_name="test-model",
        device="cuda",
        dtype_name="float16",
        shared_gpu=True,
        lease_timeout=12,
        ollama_url="http://127.0.0.1:11434/v1",
    )

    assert result["transcript"] == "shared transcript"
    assert events == [
        ("lease-enter", "stt:parakeet-service", 12),
        ("ollama-unload", "http://127.0.0.1:11434"),
        ("inference",),
        ("parakeet-park",),
        ("lease-exit",),
    ]


def test_service_parks_model_on_cpu_and_reuses_cached_weights(monkeypatch):
    from plugins.transcription.parakeet import service

    models = []

    class Model:
        def __init__(self, dtype):
            self.dtype = dtype
            self.device = ""
            self.moves = []

        def to(self, device):
            self.device = device
            self.moves.append(device)
            return self

        def eval(self):
            return self

    class AutoModel:
        @staticmethod
        def from_pretrained(_model_name, *, dtype):
            model = Model(dtype)
            models.append(model)
            return model

    fake_torch = SimpleNamespace(
        float16="float16",
        cuda=SimpleNamespace(is_available=lambda: True, empty_cache=lambda: None),
    )
    fake_transformers = SimpleNamespace(
        AutoModelForTDT=AutoModel,
        AutoProcessor=SimpleNamespace(from_pretrained=lambda _name: object()),
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "transformers", fake_transformers)
    service._release_components(fake_torch)

    _processor, first, _torch = service._load_components("same-model", "cuda", "float16")
    service._park_components(fake_torch)
    _processor, second, _torch = service._load_components("same-model", "cuda", "float16")

    assert first is second
    assert len(models) == 1
    assert first.moves == ["cuda", "cpu", "cuda"]
    service._release_components(fake_torch)


def test_service_drops_model_if_cpu_parking_fails(monkeypatch):
    from plugins.transcription.parakeet import service

    cleared = []

    class Model:
        dtype = "float16"
        device = ""

        def to(self, device):
            if device == "cpu":
                raise RuntimeError("cpu transfer failed")
            self.device = device
            return self

        def eval(self):
            return self

    fake_torch = SimpleNamespace(
        float16="float16",
        cuda=SimpleNamespace(
            is_available=lambda: True,
            empty_cache=lambda: cleared.append("cuda-cleared"),
        ),
    )
    fake_transformers = SimpleNamespace(
        AutoModelForTDT=SimpleNamespace(
            from_pretrained=lambda *_args, **_kwargs: Model()
        ),
        AutoProcessor=SimpleNamespace(from_pretrained=lambda _name: object()),
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "transformers", fake_transformers)
    service._release_components(fake_torch)
    service._load_components("same-model", "cuda", "float16")

    service._park_components(fake_torch)

    assert service._MODEL is None
    assert cleared[-1] == "cuda-cleared"


def test_service_model_cache_includes_device_and_dtype(monkeypatch):
    from plugins.transcription.parakeet import service

    models = []

    class Model:
        def __init__(self, dtype):
            self.dtype = dtype
            self.device = ""

        def to(self, device):
            self.device = device
            return self

        def eval(self):
            return self

    class AutoModel:
        @staticmethod
        def from_pretrained(_model_name, *, dtype):
            model = Model(dtype)
            models.append(model)
            return model

    fake_torch = SimpleNamespace(
        float16="float16",
        float32="float32",
        cuda=SimpleNamespace(is_available=lambda: True, empty_cache=lambda: None),
    )
    fake_transformers = SimpleNamespace(
        AutoModelForTDT=AutoModel,
        AutoProcessor=SimpleNamespace(from_pretrained=lambda _name: object()),
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "transformers", fake_transformers)
    service._release_components(fake_torch)

    _processor, first, _torch = service._load_components("same-model", "cpu", "float32")
    _processor, second, _torch = service._load_components("same-model", "cuda", "float16")

    assert first is not second
    assert (first.device, first.dtype) == ("cpu", "float32")
    assert (second.device, second.dtype) == ("cuda", "float16")
    service._release_components(fake_torch)


@pytest.mark.parametrize(
    ("stream", "expected_status"),
    [
        (BytesIO(b"short"), 400),
        (SimpleNamespace(read=lambda _length: (_ for _ in ()).throw(TimeoutError())), 408),
    ],
)
def test_service_rejects_incomplete_or_timed_out_uploads(
    stream,
    expected_status,
    monkeypatch,
):
    from plugins.transcription.parakeet import service

    responses = []
    transcribe = MagicMock()
    handler = object.__new__(service.Handler)
    handler.path = "/transcribe"
    handler.headers = Message()
    handler.headers["Authorization"] = "Bearer test-token"
    handler.headers["Content-Length"] = "10"
    handler.headers["X-Hermes-Filename"] = "voice.wav"
    handler.rfile = stream
    handler._json = lambda status, payload: responses.append((status, payload))
    monkeypatch.setattr(service, "_SERVICE_TOKEN", "test-token")
    monkeypatch.setattr(service, "_ACTIVE_REQUESTS", 0)
    monkeypatch.setattr(service, "_transcribe", transcribe)

    handler.do_POST()

    assert responses[0][0] == expected_status
    assert service._ACTIVE_REQUESTS == 0
    transcribe.assert_not_called()


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (None, 180.0),
        ("not-a-number", 180.0),
        ("nan", 180.0),
        ("inf", 180.0),
        ("-inf", 180.0),
        ("0", 180.0),
        ("-1", 180.0),
        ("3600.1", 180.0),
        ("0.001", 0.001),
        ("3600", 3600.0),
    ],
)
def test_service_bounds_lease_timeout_header(header, expected, monkeypatch):
    from plugins.transcription.parakeet import service

    responses = []
    transcribe = MagicMock(return_value={"success": True, "transcript": "ok"})
    handler = object.__new__(service.Handler)
    handler.path = "/transcribe"
    handler.headers = Message()
    handler.headers["Authorization"] = "Bearer test-token"
    handler.headers["Content-Length"] = "5"
    handler.headers["X-Hermes-Filename"] = "voice.wav"
    if header is not None:
        handler.headers["X-Hermes-Lease-Timeout"] = header
    handler.rfile = BytesIO(b"audio")
    handler._json = lambda status, payload: responses.append((status, payload))
    monkeypatch.setattr(service, "_SERVICE_TOKEN", "test-token")
    monkeypatch.setattr(service, "_ACTIVE_REQUESTS", 0)
    monkeypatch.setattr(service, "_transcribe", transcribe)

    handler.do_POST()

    assert responses == [(200, {"success": True, "transcript": "ok"})]
    assert transcribe.call_args.kwargs["lease_timeout"] == expected
    assert service._ACTIVE_REQUESTS == 0


def test_service_health_reports_protocol_without_loading_model(monkeypatch):
    from plugins.transcription.parakeet import service

    monkeypatch.setattr(service, "_runtime_available", lambda: True)
    assert service._PROTOCOL == "hermes-parakeet-v1"
    assert service._MODEL is None
