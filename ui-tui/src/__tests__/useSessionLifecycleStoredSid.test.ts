import { PassThrough } from 'stream'

import { renderSync } from '@hermes/ink'
import React, { useEffect } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { turnController } from '../app/turnController.js'
import { resetTurnState } from '../app/turnStore.js'
import { getUiState, resetUiState } from '../app/uiStore.js'
import { useSessionLifecycle } from '../app/useSessionLifecycle.js'

const instances: Array<ReturnType<typeof renderSync>> = []

afterEach(() => {
  for (const instance of instances.splice(0)) {
    instance.unmount()
    instance.cleanup()
  }
})

/** Mount the real hook and hand its API to the test once the first commit is done. */
function mountLifecycle(request: (method: string, params: unknown) => Promise<unknown>) {
  let api: null | ReturnType<typeof useSessionLifecycle> = null

  function Probe() {
    const lifecycle = useSessionLifecycle({
      colsRef: { current: 80 },
      composerActions: { setComposerTokens: vi.fn() } as any,
      gw: { request } as any,
      panel: vi.fn(),
      rpc: request as any,
      scrollRef: { current: null },
      setHistoryItems: vi.fn(),
      setLastUserMsg: vi.fn(),
      setSessionStartedAt: vi.fn(),
      setStickyPrompt: vi.fn(),
      setVoiceProcessing: vi.fn(),
      setVoiceRecording: vi.fn(),
      sys: vi.fn()
    })

    useEffect(() => {
      api = lifecycle
    })

    return null
  }

  const stream = () => Object.assign(new PassThrough(), { columns: 80, isTTY: false, rows: 24 })

  instances.push(
    renderSync(React.createElement(Probe), {
      patchConsole: false,
      stderr: stream() as unknown as NodeJS.WriteStream,
      stdin: stream() as unknown as NodeJS.ReadStream,
      stdout: stream() as unknown as NodeJS.WriteStream
    })
  )

  return () => api!
}

describe('useSessionLifecycle durable session id', () => {
  beforeEach(() => {
    resetUiState()
    resetTurnState()
    turnController.fullReset()
  })

  it('activating an agent-less session records its session_key as the recovery target', async () => {
    const request = vi.fn(async () => ({
      // _fallback_session_info shape: no stored_session_id on the info object.
      info: { cwd: '/tmp/w', lazy: true, model: 'test', skills: {}, tools: {} },
      messages: [],
      running: false,
      session_id: 'runtime-42',
      session_key: 'durable-key-123',
      status: 'idle'
    }))

    const api = mountLifecycle(request)

    await vi.waitFor(() => expect(api()).toBeTruthy())
    api().activateLiveSession('durable-key-123')

    await vi.waitFor(() => expect(getUiState().sid).toBe('runtime-42'))
    expect(request).toHaveBeenCalledWith('session.activate', { session_id: 'durable-key-123' })
    expect(getUiState().storedSid).toBe('durable-key-123')
  })

  it('makes a lazy-created session ready and retains its durable recovery identity', async () => {
    const request = vi.fn(async (method: string) => {
      if (method === 'setup.status') {
        return { provider_configured: true }
      }

      if (method === 'session.create') {
        return {
          info: { cwd: '/tmp/w', lazy: true, model: 'test', skills: {}, tools: {} },
          session_id: 'runtime-new',
          stored_session_id: 'durable-new'
        }
      }

      return null
    })

    const api = mountLifecycle(request)

    await vi.waitFor(() => expect(api()).toBeTruthy())
    await api().newSession()

    expect(getUiState().sid).toBe('runtime-new')
    expect(getUiState().storedSid).toBe('durable-new')
    expect(getUiState().status).toBe('ready')
  })
})
