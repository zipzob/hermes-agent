import { PassThrough } from 'stream'

import { renderSync } from '@hermes/ink'
import React from 'react'
import { describe, expect, it, vi } from 'vitest'

const harness = vi.hoisted(() => ({
  handler: undefined as undefined | ((input: string, key: Record<string, boolean>) => void),
  invalidations: 0
}))

vi.mock('@hermes/ink', async importOriginal => {
  const mod = await importOriginal()

  return {
    ...mod,
    invalidatePrevFrame: () => {
      harness.invalidations += 1

      return true
    },
    useInput: (handler: (input: string, key: Record<string, boolean>) => void) => {
      harness.handler = handler
    }
  }
})

import { ApprovalPrompt } from '../components/prompts.js'
import { DEFAULT_THEME } from '../theme.js'

const tick = () => new Promise<void>(resolve => setImmediate(resolve))

describe('ApprovalPrompt frame invalidation', () => {
  it('renders the backend expiry as visible fail-closed text', async () => {
    const stdout = new PassThrough()
    const stdin = new PassThrough()
    const stderr = new PassThrough()
    let output = ''

    Object.assign(stdout, { columns: 100, isTTY: false, rows: 30 })
    Object.assign(stdin, { isTTY: false })
    Object.assign(stderr, { isTTY: false })
    stdout.on('data', chunk => {
      output += chunk.toString()
    })

    const instance = renderSync(
      <ApprovalPrompt
        cols={100}
        onChoice={() => {}}
        req={{ allowPermanent: true, command: 'echo test', description: 'test command', expiresAtMs: Date.now() + 15 * 60_000 }}
        t={DEFAULT_THEME}
      />,
      {
        patchConsole: false,
        stderr: stderr as NodeJS.WriteStream,
        stdin: stdin as NodeJS.ReadStream,
        stdout: stdout as NodeJS.WriteStream
      }
    )

    await tick()
    expect(output).toContain('Expires in: 15m')
    expect(output).toContain('(no response: deny)')
    instance.unmount()
    instance.cleanup()
  })

  it('invalidates cached rows when selection moves and when the prompt unmounts', async () => {
    const stdout = new PassThrough()
    const stdin = new PassThrough()
    const stderr = new PassThrough()

    Object.assign(stdout, { columns: 100, isTTY: false, rows: 30 })
    Object.assign(stdin, { isTTY: false })
    Object.assign(stderr, { isTTY: false })
    harness.handler = undefined
    harness.invalidations = 0

    const instance = renderSync(
      <ApprovalPrompt
        cols={100}
        onChoice={() => {}}
        req={{ allowPermanent: true, command: 'echo test', description: 'test command' }}
        t={DEFAULT_THEME}
      />,
      {
        patchConsole: false,
        stderr: stderr as NodeJS.WriteStream,
        stdin: stdin as NodeJS.ReadStream,
        stdout: stdout as NodeJS.WriteStream
      }
    )

    await tick()
    const mounted = harness.invalidations
    expect(mounted).toBeGreaterThan(0)

    harness.handler?.('', { downArrow: true })
    await tick()
    expect(harness.invalidations).toBeGreaterThan(mounted)

    const moved = harness.invalidations
    instance.unmount()
    await tick()
    expect(harness.invalidations).toBeGreaterThan(moved)
    instance.cleanup()
  })
})
