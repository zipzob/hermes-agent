import { describe, expect, it } from 'vitest'

import { formatVoiceStatusLabel, recordingDeadlineFromStatus } from '../lib/voiceStatus.js'

describe('recordingDeadlineFromStatus', () => {
  it('derives an authoritative deadline from a listening event', () => {
    expect(
      recordingDeadlineFromStatus({
        max_recording_seconds: 300,
        started_at_ms: 1_000,
        state: 'listening'
      })
    ).toBe(301_000)
  })

  it('clears the deadline outside listening and for disabled cutoffs', () => {
    expect(recordingDeadlineFromStatus({ max_recording_seconds: 60, started_at_ms: 1_000, state: 'transcribing' })).toBeNull()
    expect(recordingDeadlineFromStatus({ max_recording_seconds: 0, started_at_ms: 1_000, state: 'listening' })).toBeNull()
  })
})

describe('formatVoiceStatusLabel', () => {
  it('shows silence as the primary countdown and the hard cap as a helper', () => {
    expect(formatVoiceStatusLabel({ deadlineMs: 301_000, enabled: true, nowMs: 1_000, processing: false, recording: true, silenceRemainingSeconds: null, tts: false })).toBe('● REC · max 5:00')
    expect(formatVoiceStatusLabel({ deadlineMs: 301_000, enabled: true, nowMs: 1_000, processing: false, recording: true, silenceRemainingSeconds: 4.2, tts: false })).toBe('● REC silence 5s · max 5:00')
    expect(formatVoiceStatusLabel({ deadlineMs: 301_000, enabled: true, nowMs: 300_001, processing: false, recording: true, silenceRemainingSeconds: 0.4, tts: false })).toBe('● REC silence 1s · max 1s')
  })

  it('preserves non-recording voice labels', () => {
    expect(formatVoiceStatusLabel({ deadlineMs: null, enabled: true, nowMs: 0, processing: true, recording: false, tts: false })).toBe('◉ STT')
    expect(formatVoiceStatusLabel({ deadlineMs: null, enabled: true, nowMs: 0, processing: false, recording: false, tts: true })).toBe('voice on [tts]')
  })
})
