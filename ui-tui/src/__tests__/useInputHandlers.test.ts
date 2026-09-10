import { describe, expect, it, vi } from 'vitest'

import { getOverlayState, patchOverlayState, resetOverlayState } from '../app/overlayStore.js'
import {
  applyVoiceRecordRequest,
  applyVoiceRecordResponse,
  denyApproval,
  dismissSensitivePrompt,
  handleIdleHotkeyExit,
  resolveCtrlCComposerAction,
  shouldAllowIdleHotkeyExit,
  shouldDetachEditedHistoryInput,
  shouldFallThroughForScroll,
  shouldRouteVoiceStopWhileBlocked
} from '../app/useInputHandlers.js'

const baseKey = {
  downArrow: false,
  pageDown: false,
  pageUp: false,
  shift: false,
  upArrow: false,
  wheelDown: false,
  wheelUp: false
}

describe('shouldFallThroughForScroll — keep transcript scrolling alive during prompt overlays', () => {
  it('falls through for wheel scrolls', () => {
    expect(shouldFallThroughForScroll({ ...baseKey, wheelUp: true })).toBe(true)
    expect(shouldFallThroughForScroll({ ...baseKey, wheelDown: true })).toBe(true)
  })

  it('falls through for PageUp / PageDown', () => {
    expect(shouldFallThroughForScroll({ ...baseKey, pageUp: true })).toBe(true)
    expect(shouldFallThroughForScroll({ ...baseKey, pageDown: true })).toBe(true)
  })

  it('falls through for Shift+ArrowUp / Shift+ArrowDown', () => {
    expect(shouldFallThroughForScroll({ ...baseKey, shift: true, upArrow: true })).toBe(true)
    expect(shouldFallThroughForScroll({ ...baseKey, shift: true, downArrow: true })).toBe(true)
  })

  it('does NOT fall through for plain arrows — those drive in-prompt selection', () => {
    expect(shouldFallThroughForScroll({ ...baseKey, upArrow: true })).toBe(false)
    expect(shouldFallThroughForScroll({ ...baseKey, downArrow: true })).toBe(false)
  })

  it('does NOT fall through for plain Shift — without an arrow it is a no-op', () => {
    expect(shouldFallThroughForScroll({ ...baseKey, shift: true })).toBe(false)
  })

  it('does NOT fall through for unrelated state (no scroll keys held)', () => {
    expect(shouldFallThroughForScroll(baseKey)).toBe(false)
  })
})

describe('shouldAllowIdleHotkeyExit', () => {
  it('keeps idle exit hotkeys enabled in normal terminals', () => {
    expect(shouldAllowIdleHotkeyExit(false)).toBe(true)
  })

  it('disables idle exit hotkeys in dashboard chat', () => {
    expect(shouldAllowIdleHotkeyExit(true)).toBe(false)
  })
})

describe('shouldDetachEditedHistoryInput', () => {
  const history = ['older message', 'line one\nline two']

  it('detaches a recalled entry as soon as the user edits it', () => {
    expect(shouldDetachEditedHistoryInput(1, history, 'line one edited\nline two')).toBe(true)
  })

  it('keeps unchanged recalled entries in history navigation', () => {
    expect(shouldDetachEditedHistoryInput(1, history, 'line one\nline two')).toBe(false)
  })

  it('does not detach an ordinary current draft', () => {
    expect(shouldDetachEditedHistoryInput(null, history, 'new draft')).toBe(false)
  })
})

describe('resolveCtrlCComposerAction — draft wins over interrupt', () => {
  it('clears a non-empty composer even while the agent is streaming', () => {
    expect(resolveCtrlCComposerAction({ busy: true, hasDraft: true, hasSession: true })).toBe('clear')
  })

  it('interrupts a running turn when the composer is empty', () => {
    expect(resolveCtrlCComposerAction({ busy: true, hasDraft: false, hasSession: true })).toBe('interrupt')
  })

  it('clears an idle composer instead of exiting', () => {
    expect(resolveCtrlCComposerAction({ busy: false, hasDraft: true, hasSession: true })).toBe('clear')
  })

  it('exits when idle with an empty composer', () => {
    expect(resolveCtrlCComposerAction({ busy: false, hasDraft: false, hasSession: true })).toBe('exit')
  })

  it('does not interrupt a busy session that has no sid yet', () => {
    expect(resolveCtrlCComposerAction({ busy: true, hasDraft: false, hasSession: false })).toBe('exit')
  })
})

describe('handleIdleHotkeyExit', () => {
  it('exits in normal terminals', () => {
    const actions = { die: vi.fn(), sys: vi.fn() }

    handleIdleHotkeyExit(actions, false)

    expect(actions.die).toHaveBeenCalledTimes(1)
    expect(actions.sys).not.toHaveBeenCalled()
  })

  it('asks the dashboard for a fresh chat instead of leaving a ghost session', () => {
    const actions = { die: vi.fn(), sys: vi.fn() }
    const requestDashboardNewSession = vi.fn()

    handleIdleHotkeyExit(actions, true, requestDashboardNewSession)

    expect(actions.die).not.toHaveBeenCalled()
    expect(requestDashboardNewSession).toHaveBeenCalledTimes(1)
    expect(actions.sys).toHaveBeenCalledWith('starting a fresh dashboard chat...')
  })
})

describe('applyVoiceRecordResponse', () => {
  it('reverts optimistic REC state when the gateway reports voice busy', () => {
    const setProcessing = vi.fn()
    const setRecording = vi.fn()
    const sys = vi.fn()

    applyVoiceRecordResponse({ status: 'busy' }, true, { setProcessing, setRecording }, sys)

    expect(setRecording).toHaveBeenCalledWith(false)
    expect(setProcessing).toHaveBeenCalledWith(true)
    expect(sys).toHaveBeenCalledWith('voice: still transcribing; try again shortly')
  })

  it('explains when the interruption listener owns the microphone', () => {
    const setProcessing = vi.fn()
    const setRecording = vi.fn()
    const sys = vi.fn()

    applyVoiceRecordResponse(
      { reason: 'barge_listener_active', status: 'busy' },
      true,
      { setProcessing, setRecording },
      sys
    )
    expect(setRecording).toHaveBeenCalledWith(false)
    expect(setProcessing).toHaveBeenCalledWith(false)
    expect(sys).toHaveBeenCalledWith('voice: already listening for your interruption')
  })

  it('applies authoritative REC state for successful recording starts', () => {
    const setProcessing = vi.fn()
    const setRecording = vi.fn()

    applyVoiceRecordResponse({ status: 'recording' }, true, { setProcessing, setRecording }, vi.fn())

    expect(setRecording).toHaveBeenCalledWith(true)
    expect(setProcessing).toHaveBeenCalledWith(false)
  })

  it('shows STT after the gateway confirms recorder stop', () => {
    const setProcessing = vi.fn()
    const setRecording = vi.fn()

    applyVoiceRecordResponse({ status: 'stopped' }, false, { setProcessing, setRecording }, vi.fn())

    expect(setRecording).toHaveBeenCalledWith(false)
    expect(setProcessing).toHaveBeenCalledWith(true)
  })

  it('reverts optimistic REC state when the gateway returns null', () => {
    const setProcessing = vi.fn()
    const setRecording = vi.fn()

    applyVoiceRecordResponse(null, true, { setProcessing, setRecording }, vi.fn())

    expect(setRecording).toHaveBeenCalledWith(false)
    expect(setProcessing).toHaveBeenCalledWith(false)
  })
})

describe('voice record request routing', () => {
  it('clears REC while shutdown is pending, but waits on starts', () => {
    const setProcessing = vi.fn()
    const setRecording = vi.fn()

    applyVoiceRecordRequest(false, { setProcessing, setRecording })
    expect(setRecording).toHaveBeenCalledWith(false)
    expect(setProcessing).toHaveBeenCalledWith(true)

    setProcessing.mockClear()
    setRecording.mockClear()
    applyVoiceRecordRequest(true, { setProcessing, setRecording })
    expect(setRecording).not.toHaveBeenCalled()
    expect(setProcessing).not.toHaveBeenCalled()
  })

  it('routes only an active recording stop while input is blocked', () => {
    expect(shouldRouteVoiceStopWhileBlocked(true, true, true)).toBe(true)
    expect(shouldRouteVoiceStopWhileBlocked(true, false, true)).toBe(false)
    expect(shouldRouteVoiceStopWhileBlocked(true, true, false)).toBe(false)
    expect(shouldRouteVoiceStopWhileBlocked(false, true, true)).toBe(false)
  })
})

describe('dismissSensitivePrompt', () => {
  it('keeps a newer approval visible when an earlier Ctrl-C denial resolves', async () => {
    resetOverlayState()
    const approval = { command: 'test', description: 'test', requestId: 'old', toolId: 'old-tool' }
    patchOverlayState({ approval })
    let resolve!: (value: object) => void

    const rpc = vi.fn().mockReturnValue(
      new Promise(done => {
        resolve = done
      })
    )

    const pending = denyApproval(approval, rpc)
    const newer = { ...approval, requestId: 'new', toolId: 'new-tool' }

    patchOverlayState({ approval: newer })
    resolve({})
    await pending
    expect(rpc).toHaveBeenCalledWith('approval.respond', expect.objectContaining({ choice: 'deny', request_id: 'old' }))
    expect(getOverlayState().approval).toEqual(newer)
    resetOverlayState()
  })

  it.each([null, {}])('clears the matching Ctrl-C prompt only after acknowledgement: %s', async response => {
    resetOverlayState()
    const approval = { command: 'test', description: 'test', requestId: 'current' }
    patchOverlayState({ approval })
    const rpc = vi.fn().mockResolvedValue(response)
    await denyApproval(approval, rpc)
    expect(getOverlayState().approval).toEqual(response ? null : approval)
    resetOverlayState()
  })

  it('clears a sudo overlay before a stale cancel RPC resolves', async () => {
    resetOverlayState()
    patchOverlayState({ sudo: { requestId: 'sudo-1' } })
    const rpc = vi.fn().mockResolvedValue(null)
    const sys = vi.fn()

    const pending = dismissSensitivePrompt(getOverlayState(), rpc, sys)

    expect(getOverlayState().sudo).toBeNull()
    expect(sys).toHaveBeenCalledWith('sudo cancelled')
    expect(rpc).toHaveBeenCalledWith('sudo.respond', { password: '', request_id: 'sudo-1' })
    await pending
  })

  it('clears a secret overlay before a stale cancel RPC resolves', async () => {
    resetOverlayState()
    patchOverlayState({ secret: { envVar: 'API_KEY', prompt: 'Enter API key', requestId: 'secret-1' } })
    const rpc = vi.fn().mockResolvedValue(null)
    const sys = vi.fn()

    const pending = dismissSensitivePrompt(getOverlayState(), rpc, sys)

    expect(getOverlayState().secret).toBeNull()
    expect(sys).toHaveBeenCalledWith('secret entry cancelled')
    expect(rpc).toHaveBeenCalledWith('secret.respond', { request_id: 'secret-1', value: '' })
    await pending
  })
})
