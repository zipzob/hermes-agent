"""Hermes STT provider for one host-local Parakeet service."""

from __future__ import annotations

import json
import logging
import os
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Optional

from agent.transcription_provider import TranscriptionProvider
from hermes_constants import get_default_hermes_root

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "http://127.0.0.1:8765"
DEFAULT_MODEL = "nvidia/parakeet-tdt-0.6b-v3"
_PROTOCOL = "hermes-parakeet-v1"


def _loopback_base_url(value: str) -> str:
    """Validate and normalize the managed service's loopback-only origin."""
    try:
        parsed = urllib.parse.urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Parakeet base_url must be an HTTP 127.0.0.1 origin") from exc
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or parsed.username is not None
        or parsed.password is not None
        or port is None
        or not 1 <= port <= 65535
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Parakeet base_url must be an HTTP 127.0.0.1 origin")
    return f"http://127.0.0.1:{port}"


def _config() -> dict[str, Any]:
    try:
        from hermes_cli.config import load_config

        stt = load_config().get("stt") or {}
        value = stt.get("parakeet") or {}
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _service_token_path() -> Path:
    return get_default_hermes_root() / "local-inference" / "parakeet.token"


def _service_token() -> str:
    path = _service_token_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        token = path.read_text(encoding="utf-8").strip()
        if token:
            path.chmod(0o600)
            return token
    except FileNotFoundError:
        pass
    token = secrets.token_urlsafe(32)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        for _attempt in range(50):
            token = path.read_text(encoding="utf-8").strip()
            if token:
                path.chmod(0o600)
                return token
            time.sleep(0.01)
        raise RuntimeError(f"Parakeet service token remained empty: {path}")
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(token + "\n")
    return token


def _health(base_url: str, token: str, *, timeout: float = 1.0) -> bool:
    try:
        base_url = _loopback_base_url(base_url)
        request = urllib.request.Request(
            f"{base_url.rstrip('/')}/health",
            headers={"Authorization": f"Bearer {token}"},
            method="GET",
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
        return payload.get("protocol") == _PROTOCOL and bool(payload.get("runtime_available"))
    except Exception:
        return False


def _service_log_path() -> Path:
    return get_default_hermes_root() / "local-inference" / "parakeet.log"


def _spawn_service(port: int, idle_timeout: float, token: str) -> None:
    service = Path(__file__).with_name("service.py")
    log_path = _service_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_handle = log_path.open("ab")
    command = [
        sys.executable,
        str(service),
        "--port",
        str(port),
        "--idle-timeout",
        str(idle_timeout),
    ]
    kwargs: dict[str, Any] = {
        "stdout": log_handle,
        "stderr": subprocess.STDOUT,
        "cwd": str(Path(__file__).resolve().parents[3]),
        "close_fds": True,
        "env": {**os.environ, "HERMES_PARAKEET_TOKEN": token},
    }
    if os.name == "nt":  # pragma: no cover - native Windows
        kwargs["creationflags"] = (
            getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
    else:
        kwargs["start_new_session"] = True
    try:
        subprocess.Popen(command, stdin=subprocess.DEVNULL, **kwargs)
    finally:
        log_handle.close()


def _ensure_service(base_url: str, *, startup_timeout: float, idle_timeout: float) -> bool:
    try:
        base_url = _loopback_base_url(base_url)
    except ValueError:
        return False
    token = _service_token()
    if _health(base_url, token):
        return True
    try:
        port = int(base_url.rsplit(":", 1)[1].rstrip("/"))
    except (ValueError, IndexError):
        return False
    _spawn_service(port, idle_timeout, token)
    deadline = time.monotonic() + max(0.0, startup_timeout)
    while time.monotonic() < deadline:
        if _health(base_url, token):
            return True
        time.sleep(0.1)
    return False


class ParakeetTranscriptionProvider(TranscriptionProvider):
    @property
    def name(self) -> str:
        return "parakeet"

    @property
    def display_name(self) -> str:
        return "NVIDIA Parakeet (shared local)"

    def default_model(self) -> str:
        return DEFAULT_MODEL

    def list_models(self) -> list[dict[str, Any]]:
        return [{
            "id": DEFAULT_MODEL,
            "display": "Parakeet TDT 0.6B v3",
            "languages": ["multilingual"],
        }]

    def is_available(self) -> bool:
        from tools.lazy_deps import FeatureUnavailable, ensure

        try:
            ensure("stt.parakeet")
        except FeatureUnavailable as exc:
            logger.warning("Parakeet runtime is unavailable: %s", exc)
            return False
        cfg = _config()
        try:
            base_url = _loopback_base_url(str(cfg.get("base_url") or DEFAULT_BASE_URL))
        except ValueError as exc:
            logger.warning("Invalid Parakeet service URL: %s", exc)
            return False
        return _ensure_service(
            base_url,
            startup_timeout=float(cfg.get("startup_timeout", 30.0)),
            idle_timeout=float(cfg.get("idle_timeout", 300.0)),
        )

    def transcribe(
        self,
        file_path: str,
        *,
        model: Optional[str] = None,
        language: Optional[str] = None,
        **extra: Any,
    ) -> dict[str, Any]:
        cfg = _config()
        try:
            base_url = _loopback_base_url(str(cfg.get("base_url") or DEFAULT_BASE_URL))
            audio = Path(file_path).read_bytes()
            headers = {
                "Authorization": f"Bearer {_service_token()}",
                "Content-Type": "application/octet-stream",
                "X-Hermes-Filename": Path(file_path).name,
                "X-Hermes-Model": str(model or cfg.get("model") or DEFAULT_MODEL),
                "X-Hermes-Language": str(language or ""),
                "X-Hermes-Device": str(cfg.get("device") or "auto"),
                "X-Hermes-Dtype": str(cfg.get("dtype") or "auto"),
                "X-Hermes-Shared-Gpu": "true" if cfg.get("shared_gpu", True) else "false",
                "X-Hermes-Lease-Timeout": str(cfg.get("shared_gpu_timeout", 180.0)),
                "X-Hermes-Ollama-Url": str(cfg.get("ollama_base_url") or ""),
            }
            request = urllib.request.Request(
                f"{base_url}/transcribe",
                data=audio,
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(  # noqa: S310
                request,
                timeout=float(cfg.get("request_timeout", 300.0)),
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("service returned a non-object response")
            payload.setdefault("provider", self.name)
            payload.setdefault("transcript", "")
            return payload
        except Exception as exc:
            logger.warning("Parakeet service request failed: %s", exc)
            return {
                "success": False,
                "transcript": "",
                "provider": self.name,
                "error": f"Parakeet service request failed: {exc}",
            }
