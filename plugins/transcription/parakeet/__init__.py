"""Bundled Parakeet transcription provider."""

from .provider import ParakeetTranscriptionProvider


def register(ctx) -> None:
    ctx.register_transcription_provider(ParakeetTranscriptionProvider())
