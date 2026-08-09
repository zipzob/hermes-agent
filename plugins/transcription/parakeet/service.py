"""Single host-local Parakeet model owner and bounded request queue."""

from __future__ import annotations

import argparse
import gc
import importlib.util
import json
import math
import os
import shutil
import secrets
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import nullcontext
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.local_inference_lease import (  # noqa: E402
    local_inference_lease,
    normalize_ollama_base_url,
    unload_ollama_models,
)

_PROTOCOL = "hermes-parakeet-v1"
_DEFAULT_MODEL = "nvidia/parakeet-tdt-0.6b-v3"
_MAX_AUDIO_BYTES = 100 * 1024 * 1024
_CLIENT_READ_TIMEOUT = 30.0
_REQUEST_LOCK = threading.Lock()
_MODEL_LOCK = threading.Lock()
_MODEL: Any = None
_PROCESSOR: Any = None
_MODEL_NAME = ""
_MODEL_DEVICE = ""
_MODEL_DTYPE = ""
_LAST_ACTIVITY = time.monotonic()
_ACTIVE_REQUESTS = 0
_ACTIVITY_LOCK = threading.Lock()


def _parse_lease_timeout(value: str | None) -> float:
    """Return a finite bounded lease timeout, falling back safely."""
    try:
        parsed = float(value or "180")
    except (TypeError, ValueError):
        return 180.0
    if not math.isfinite(parsed) or not 0.001 <= parsed <= 3600.0:
        return 180.0
    return parsed
_SERVICE_TOKEN = ""


def _runtime_available() -> bool:
    return all(
        importlib.util.find_spec(module) is not None
        for module in ("torch", "transformers", "librosa")
    ) and shutil.which("ffmpeg") is not None


def _load_components(model_name: str, device: str, dtype_name: str):
    global _MODEL, _PROCESSOR, _MODEL_NAME, _MODEL_DEVICE, _MODEL_DTYPE

    import torch
    from transformers import AutoModelForTDT, AutoProcessor

    resolved_device = device
    if resolved_device == "auto":
        resolved_device = "cuda" if torch.cuda.is_available() else "cpu"
    if dtype_name == "auto":
        dtype_name = "float16" if resolved_device == "cuda" else "float32"
    dtype = getattr(torch, dtype_name, None)
    if dtype is None:
        raise ValueError(f"unsupported Parakeet dtype: {dtype_name}")

    with _MODEL_LOCK:
        cache_key = (model_name, resolved_device, dtype_name)
        active_key = (_MODEL_NAME, _MODEL_DEVICE, _MODEL_DTYPE)
        if _MODEL is None or active_key != cache_key:
            if _MODEL is not None:
                _release_components(torch)
            _PROCESSOR = AutoProcessor.from_pretrained(model_name)
            _MODEL = AutoModelForTDT.from_pretrained(model_name, dtype=dtype).to(resolved_device)
            _MODEL.eval()
            _MODEL_NAME = model_name
            _MODEL_DEVICE = resolved_device
            _MODEL_DTYPE = dtype_name
        else:
            # Shared-GPU requests park cached weights on CPU between utterances.
            # Move the same model back only after the caller acquires the lease.
            _MODEL = _MODEL.to(resolved_device)
            _MODEL.eval()
    return _PROCESSOR, _MODEL, torch


def _release_components(torch_module: Any) -> None:
    global _MODEL, _PROCESSOR, _MODEL_NAME, _MODEL_DEVICE, _MODEL_DTYPE
    _MODEL = None
    _PROCESSOR = None
    _MODEL_NAME = ""
    _MODEL_DEVICE = ""
    _MODEL_DTYPE = ""
    gc.collect()
    cuda = getattr(torch_module, "cuda", None)
    if cuda is not None and hasattr(cuda, "empty_cache"):
        cuda.empty_cache()


def _park_components(torch_module: Any) -> None:
    """Keep weights cached in CPU RAM while releasing all Parakeet GPU memory."""
    global _MODEL
    with _MODEL_LOCK:
        if _MODEL is not None and str(getattr(_MODEL, "device", "")) != "cpu":
            try:
                _MODEL = _MODEL.to("cpu")
            except Exception:
                # Fail closed: if parking is unavailable, destroy the cached
                # model before the caller releases the shared GPU lease.
                _release_components(torch_module)
                return
        cuda = getattr(torch_module, "cuda", None)
        if cuda is not None and hasattr(cuda, "empty_cache"):
            cuda.empty_cache()


def _decode_audio(path: str, sampling_rate: int):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required for Parakeet STT")
    raw = subprocess.check_output(
        [
            ffmpeg,
            "-v", "error",
            "-i", path,
            "-f", "f32le",
            "-acodec", "pcm_f32le",
            "-ac", "1",
            "-ar", str(sampling_rate),
            "-",
        ],
        timeout=300,
    )
    import numpy as np

    return np.frombuffer(raw, dtype=np.float32).copy()


def _profile_ollama_url() -> str:
    configured = os.environ.get("HERMES_LOCAL_INFERENCE_OLLAMA_URL", "").strip()
    if configured:
        return normalize_ollama_base_url(configured)
    try:
        from hermes_constants import get_hermes_home

        path = get_hermes_home() / "hindsight" / "config.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        if str(data.get("llm_provider", "")).lower() == "ollama":
            return normalize_ollama_base_url(str(data.get("llm_base_url") or ""))
    except Exception:
        pass
    return ""


def _transcribe(
    path: str,
    *,
    model_name: str,
    device: str,
    dtype_name: str,
    shared_gpu: bool,
    lease_timeout: float,
    ollama_url: str,
) -> dict[str, Any]:
    lease = (
        local_inference_lease("stt:parakeet-service", timeout=lease_timeout)
        if shared_gpu
        else nullcontext()
    )
    with _REQUEST_LOCK, lease:
        if shared_gpu:
            origin = normalize_ollama_base_url(ollama_url) or _profile_ollama_url()
            if origin:
                unload_ollama_models(origin)
        processor, model, torch = _load_components(model_name, device, dtype_name)
        try:
            sampling_rate = int(processor.feature_extractor.sampling_rate)
            audio = _decode_audio(path, sampling_rate)
            inputs = processor(audio, sampling_rate=sampling_rate, return_tensors="pt")
            inputs = inputs.to(device=model.device, dtype=model.dtype)
            with torch.inference_mode():
                output = model.generate(**inputs, return_dict_in_generate=True)
            transcript = processor.decode(output.sequences[0], skip_special_tokens=True)
            if isinstance(transcript, list):
                transcript = transcript[0] if transcript else ""
            return {
                "success": True,
                "transcript": str(transcript).strip(),
                "provider": "parakeet",
                "backend": "shared-service",
            }
        finally:
            if shared_gpu:
                _park_components(torch)


class Handler(BaseHTTPRequestHandler):
    server_version = "HermesParakeet/1"

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(_CLIENT_READ_TIMEOUT)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        supplied = self.headers.get("Authorization", "")
        expected = f"Bearer {_SERVICE_TOKEN}"
        if _SERVICE_TOKEN and secrets.compare_digest(supplied, expected):
            return True
        self._json(401, {"error": "unauthorized"})
        return False

    def do_GET(self) -> None:
        if not self._authorized():
            return
        if self.path != "/health":
            self._json(404, {"error": "not found"})
            return
        self._json(200, {
            "protocol": _PROTOCOL,
            "runtime_available": _runtime_available(),
        })

    def do_POST(self) -> None:
        global _ACTIVE_REQUESTS, _LAST_ACTIVITY
        if not self._authorized():
            return
        if self.path != "/transcribe":
            self._json(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > _MAX_AUDIO_BYTES:
            self._json(413, {"success": False, "transcript": "", "error": "invalid audio size"})
            return

        suffix = Path(self.headers.get("X-Hermes-Filename", "audio.wav")).suffix
        if not suffix or len(suffix) > 10:
            suffix = ".audio"
        with _ACTIVITY_LOCK:
            _ACTIVE_REQUESTS += 1
            _LAST_ACTIVITY = time.monotonic()
        temp_path = ""
        try:
            try:
                body = self.rfile.read(length)
            except TimeoutError:
                self._json(408, {
                    "success": False,
                    "transcript": "",
                    "error": "audio upload timed out",
                })
                return
            if len(body) != length:
                self._json(400, {
                    "success": False,
                    "transcript": "",
                    "error": "incomplete audio upload",
                })
                return
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as audio_file:
                audio_file.write(body)
                temp_path = audio_file.name
            result = _transcribe(
                temp_path,
                model_name=self.headers.get("X-Hermes-Model") or _DEFAULT_MODEL,
                device=(self.headers.get("X-Hermes-Device") or "auto").lower(),
                dtype_name=(self.headers.get("X-Hermes-Dtype") or "auto").lower(),
                shared_gpu=(self.headers.get("X-Hermes-Shared-Gpu") or "false").lower() == "true",
                lease_timeout=_parse_lease_timeout(
                    self.headers.get("X-Hermes-Lease-Timeout")
                ),
                ollama_url=self.headers.get("X-Hermes-Ollama-Url") or "",
            )
            self._json(200, result)
        except Exception as exc:
            self._json(500, {
                "success": False,
                "transcript": "",
                "provider": "parakeet",
                "error": f"Parakeet transcription failed: {exc}",
            })
        finally:
            if temp_path:
                Path(temp_path).unlink(missing_ok=True)
            with _ACTIVITY_LOCK:
                _ACTIVE_REQUESTS -= 1
                _LAST_ACTIVITY = time.monotonic()


def _idle_watchdog(server: ThreadingHTTPServer, timeout: float) -> None:
    if timeout <= 0:
        return
    while True:
        time.sleep(min(5.0, max(0.5, timeout / 4)))
        with _ACTIVITY_LOCK:
            idle = _ACTIVE_REQUESTS == 0 and time.monotonic() - _LAST_ACTIVITY >= timeout
        if idle:
            server.shutdown()
            return


def main() -> int:
    global _SERVICE_TOKEN
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--idle-timeout", type=float, default=300.0)
    args = parser.parse_args()
    _SERVICE_TOKEN = os.environ.get("HERMES_PARAKEET_TOKEN", "")
    if not _SERVICE_TOKEN:
        raise RuntimeError("HERMES_PARAKEET_TOKEN is required")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    threading.Thread(
        target=_idle_watchdog,
        args=(server, args.idle_timeout),
        daemon=True,
        name="parakeet-idle-watchdog",
    ).start()
    try:
        server.serve_forever(poll_interval=0.2)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
