import { PassThrough } from 'node:stream'

import type * as HermesInk from '@hermes/ink'
import { renderSync, Text } from '@hermes/ink'
import React from 'react'
import { describe, expect, it, vi } from 'vitest'

const harness = vi.hoisted(() => ({ invalidations: 0 }))

vi.mock('@hermes/ink', async importOriginal => {
  const mod = await importOriginal<typeof HermesInk>()

  return {
    ...mod,
    invalidatePrevFrame: () => {
      harness.invalidations += 1

      return true
    }
  }
})

import { LiveTailFrameBoundary, liveTailStructuralSignature } from '../components/streamingAssistant.js'

const tick = () => new Promise<void>(resolve => setImmediate(resolve))

describe('LiveTailFrameBoundary', () => {
  it('ignores token growth but detects live tree structure changes', () => {
    const signature = (text: string, context = '') =>
      liveTailStructuralSignature({
        blocks: [
          {
            isStreaming: true,
            key: 'streaming',
            msg: { role: 'assistant', text },
            tools: [{ context, id: 'tool-1', name: 'terminal' }]
          }
        ],
        detailsMode: 'expanded',
        detailsModeCommandOverride: false,
        progressVisible: true,
        sections: { tools: 'expanded' }
      })

    expect(signature('a')).toBe(signature('ordinary token growth'))
    expect(signature('a', 'one line')).not.toBe(signature('a', 'one line\nwith detail'))
    expect(
      liveTailStructuralSignature({
        blocks: [
          {
            key: 'reasoning',
            msg: { isLiveReasoning: true, role: 'assistant', text: '', thinking: 'a' }
          }
        ],
        detailsMode: 'expanded',
        detailsModeCommandOverride: false,
        progressVisible: true
      })
    ).toBe(
      liveTailStructuralSignature({
        blocks: [
          {
            key: 'reasoning',
            msg: { isLiveReasoning: true, role: 'assistant', text: '', thinking: 'ordinary token growth' }
          }
        ],
        detailsMode: 'expanded',
        detailsModeCommandOverride: false,
        progressVisible: true
      })
    )
    expect(signature('a')).not.toBe(
      liveTailStructuralSignature({
        blocks: [
          {
            key: 'pending-tools',
            msg: { kind: 'trail', role: 'system', text: '', tools: ['terminal'] }
          }
        ],
        detailsMode: 'expanded',
        detailsModeCommandOverride: false,
        progressVisible: true,
        sections: { tools: 'expanded' }
      })
    )
  })

  it('invalidates only for structural transitions and unmount', async () => {
    const stdout = new PassThrough()
    const stdin = new PassThrough()
    const stderr = new PassThrough()

    Object.assign(stdout, { columns: 100, isTTY: false, rows: 30 })
    Object.assign(stdin, { isTTY: false })
    Object.assign(stderr, { isTTY: false })
    harness.invalidations = 0

    const view = (signature: string, text: string) => (
      <LiveTailFrameBoundary signature={signature}>
        <Text>{text}</Text>
      </LiveTailFrameBoundary>
    )

    const instance = renderSync(view('active-tools:1|streaming', 'a'), {
      patchConsole: false,
      stderr: stderr as unknown as NodeJS.WriteStream,
      stdin: stdin as unknown as NodeJS.ReadStream,
      stdout: stdout as unknown as NodeJS.WriteStream
    })

    await tick()
    const mounted = harness.invalidations
    expect(mounted).toBeGreaterThan(0)

    instance.rerender(view('active-tools:1|streaming', 'ordinary token growth'))
    await tick()
    expect(harness.invalidations).toBe(mounted)

    instance.rerender(view('pending-tools:1', 'tool tree collapsed'))
    await tick()
    expect(harness.invalidations).toBeGreaterThan(mounted)

    const transitioned = harness.invalidations
    instance.unmount()
    await tick()
    expect(harness.invalidations).toBeGreaterThan(transitioned)
    instance.cleanup()
  })
})
