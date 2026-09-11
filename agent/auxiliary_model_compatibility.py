"""Compatibility checks for economical auxiliary model routing."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
import hashlib
import threading
import time
from typing import Literal

from agent.model_metadata import strip_codex_context_variant_suffix

CompatibilityVerdict = Literal["compatible", "incompatible", "unknown"]
Catalog = Mapping[str, object] | Iterable[str]
CatalogLoader = Callable[[str], Catalog | tuple[Catalog, bool]]
_INCOMPATIBLE_TTL_SECONDS = 3600
_incompatible_cache: dict[tuple[str, str], float] = {}
_incompatible_cache_lock = threading.Lock()


def _wire_slug(model: str) -> str:
    normalized = strip_codex_context_variant_suffix(model)
    return normalized.strip().lower().rsplit("/", 1)[-1]


def _cache_key(model: str, access_token: str) -> tuple[str, str]:
    fingerprint = hashlib.sha256(access_token.encode("utf-8")).hexdigest()[:16]
    return fingerprint, _wire_slug(model)


def record_codex_model_incompatibility(model: str, *, access_token: str) -> None:
    if not access_token:
        return
    with _incompatible_cache_lock:
        _incompatible_cache[_cache_key(model, access_token)] = time.monotonic()


def probe_codex_model_compatibility(
    model: str,
    *,
    access_token: str,
    catalog_loader: CatalogLoader | None = None,
) -> CompatibilityVerdict:
    """Resolve *model* against a raw account-scoped Codex catalog.

    Empty or failed discovery is inconclusive and must not block a request.
    """
    if not access_token:
        return "unknown"
    key = _cache_key(model, access_token)
    now = time.monotonic()
    with _incompatible_cache_lock:
        rejected_at = _incompatible_cache.get(key)
        if rejected_at is not None and now - rejected_at < _INCOMPATIBLE_TTL_SECONDS:
            return "incompatible"
        if rejected_at is not None:
            _incompatible_cache.pop(key, None)
    if catalog_loader is None:
        from agent.model_metadata import _fetch_codex_oauth_context_lengths_with_source

        catalog_loader = _fetch_codex_oauth_context_lengths_with_source
    try:
        loaded = catalog_loader(access_token)
        catalog = loaded[0] if isinstance(loaded, tuple) else loaded
        slugs = catalog.keys() if isinstance(catalog, Mapping) else catalog
        available = {_wire_slug(str(slug)) for slug in slugs}
    except Exception:
        return "unknown"
    if not available:
        return "unknown"
    return "compatible" if _wire_slug(model) in available else "incompatible"
