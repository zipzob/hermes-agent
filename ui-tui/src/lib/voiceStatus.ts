export interface VoiceStatusPayload {
  max_recording_seconds?: unknown
  silence_remaining_seconds?: unknown
  started_at_ms?: unknown
  state?: unknown
}

export interface VoiceStatusLabelState {
  deadlineMs: null | number
  enabled: boolean
  nowMs: number
  processing: boolean
  recording: boolean
  silenceRemainingSeconds?: null | number
  tts: boolean
}

export function recordingDeadlineFromStatus(payload: VoiceStatusPayload): null | number {
  if (payload.state !== 'listening') {
    return null
  }

  const startedAt = Number(payload.started_at_ms)
  const maxSeconds = Number(payload.max_recording_seconds)

  if (!Number.isFinite(startedAt) || !Number.isFinite(maxSeconds) || startedAt < 0 || maxSeconds <= 0) {
    return null
  }

  return startedAt + maxSeconds * 1000
}

export function formatVoiceStatusLabel(state: VoiceStatusLabelState): string {
  if (state.recording) {
    const silence = Number(state.silenceRemainingSeconds)

    const silenceLabel = Number.isFinite(silence) && state.silenceRemainingSeconds !== null
      ? ` silence ${Math.max(0, Math.ceil(silence))}s`
      : ''

    if (state.deadlineMs === null) {
      return `● REC${silenceLabel}`
    }

    const remaining = Math.max(0, Math.ceil((state.deadlineMs - state.nowMs) / 1000))

    const hardLimit = remaining >= 60
      ? `${Math.floor(remaining / 60)}:${String(remaining % 60).padStart(2, '0')}`
      : `${remaining}s`

    return `● REC${silenceLabel} · max ${hardLimit}`
  }

  if (state.processing) {
    return '◉ STT'
  }

  return `voice ${state.enabled ? 'on' : 'off'}${state.tts ? ' [tts]' : ''}`
}
