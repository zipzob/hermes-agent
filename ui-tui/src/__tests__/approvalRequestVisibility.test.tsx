import { PassThrough } from 'node:stream'

import { renderSync } from '@hermes/ink'
import type { ServerRequest } from '@hermes/shared/json-rpc-channel'
import React from 'react'
import stripAnsi from 'strip-ansi'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { createServerRequestHandler } from '../app/createServerRequestHandler.js'
import { getOverlayState, resetOverlayState } from '../app/overlayStore.js'
import { forgetServerRequest, resetServerRequestsForTests, respondToServerRequest } from '../app/serverRequestStore.js'
import { turnController } from '../app/turnController.js'
import { patchUiState, resetUiState } from '../app/uiStore.js'
import { PromptZone } from '../components/appOverlays.js'

const tick = () => new Promise<void>(resolve => setImmediate(resolve))

afterEach(() => {
  resetOverlayState()
  resetUiState()
  resetServerRequestsForTests()
})

describe('background approval visibility', () => {
  it.each([
    ['clarify', 'clarify'],
    ['sudo', 'sudo'],
    ['secret', 'secret'],
    ['vault.unlock_prompt', 'vaultUnlock']
  ] as const)('preserves an unanswered %s request until withdrawn', (method, field) => {
    const onRequest = createServerRequestHandler({ ringPromptBell: vi.fn(), setStatus: vi.fn() })
    expect(onRequest({ id: 'pending-prompt', method, params: {}, respond: vi.fn(), fail: vi.fn() })).toBe(true)
    turnController.idle()
    expect(getOverlayState()[field]?.requestId).toBe('pending-prompt')
    forgetServerRequest('pending-prompt')
    turnController.idle()
    expect(getOverlayState()[field]).toBeNull()
  })

  it('renders a live or replayed approval while the parent is idle and answers its exact request', async () => {
    resetOverlayState()
    resetUiState()
    patchUiState({ busy: false, sid: 'parent-runtime', status: 'ready' })
    const stream = () => Object.assign(new PassThrough(), { columns: 100, rows: 30, isTTY: false })
    const stdout = stream()
    let output = ''
    stdout.on('data', chunk => {
      output += stripAnsi(chunk.toString())
    })
    const answer = vi.fn()
    const acknowledge = vi.fn()

    const onRequest = createServerRequestHandler({
      acknowledgeApproval: acknowledge,
      ringPromptBell: vi.fn(),
      setStatus: status => patchUiState({ status })
    })

    const request: ServerRequest = {
      id: 'srq-background',
      method: 'approval',
      params: {
        request_id: 'approval-background',
        session_id: 'parent-runtime',
        command: 'fixture-approval-command',
        description: 'background task permission'
      },
      respond: answer,
      fail: vi.fn()
    }

    const instance = renderSync(
      <PromptZone
        cols={100}
        onApprovalChoice={vi.fn()}
        onClarifyAnswer={vi.fn()}
        onClarifyQuestionAnswer={vi.fn()}
        onSecretSubmit={vi.fn()}
        onSudoSubmit={vi.fn()}
        onVaultUnlockSubmit={vi.fn()}
      />,
      {
        stdout: stdout as unknown as NodeJS.WriteStream,
        stdin: stream() as unknown as NodeJS.ReadStream,
        stderr: stream() as unknown as NodeJS.WriteStream,
        patchConsole: false
      }
    )

    try {
      expect(onRequest(request)).toBe(true)
      await tick()
      await tick()
      expect(output).toContain('fixture-approval-command')
      expect(acknowledge).toHaveBeenCalledWith('approval-background', 'parent-runtime')
      patchUiState({ busy: true })
      await tick()
      turnController.idle()
      await tick()
      expect(getOverlayState().approval?.requestId).toBe(request.id)
      expect(onRequest({ ...request, replayed: true })).toBe(true)
      await tick()
      expect(output).toContain('background task permission')
      expect(respondToServerRequest(request.id, { choice: 'deny' })).toBe(true)
      expect(respondToServerRequest(request.id, { choice: 'once' })).toBe(false)
      expect(answer).toHaveBeenCalledExactlyOnceWith({ choice: 'deny' })
      turnController.idle()
      expect(getOverlayState().approval).toBeNull()
    } finally {
      instance.unmount()
      instance.cleanup()
    }
  })
})
