import type * as React from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

const effects = vi.hoisted(() => ({ cleanups: [] as (() => void)[] }))
vi.mock('react', async importOriginal => ({
  ...(await importOriginal<typeof React>()),
  useEffect: (effect: () => (() => void) | undefined) => {
    const cleanup = effect()

    if (cleanup) {
      effects.cleanups.push(cleanup)
    }
  }
}))

import { getDelegationState, resetDelegationState } from '../app/delegationStore.js'
import { getUiState, patchUiState } from '../app/uiStore.js'
import { useDelegationStatus } from '../app/useDelegationStatus.js'
import type { GatewayClient } from '../gatewayClient.js'
import type { DelegationLifecycle } from '../gatewayTypes.js'
import { reconcileDelegationLifecycle } from '../lib/delegationLifecycle.js'
import type { SubagentProgress } from '../types.js'

const lifecycle: DelegationLifecycle = {
  active_tasks: 0,
  stalled_tasks: 2,
  batches: [{ delegation_id: 'batch', status: 'stalled', task_count: 2, runner_settled: false }]
}

const item: SubagentProgress = {
  id: 'child',
  delegationId: 'batch',
  depth: 0,
  goal: 'work',
  index: 0,
  notes: [],
  parentId: null,
  status: 'running',
  taskCount: 2,
  thinking: [],
  toolCount: 0,
  tools: []
}

afterEach(() => {
  effects.cleanups.splice(0).forEach(cleanup => cleanup())
  vi.useRealTimers()
  resetDelegationState()
})

describe('idle delegation reconciliation', () => {
  it('refreshes counts and cached rows while idle; failed polls preserve warnings, settlement clears them', async () => {
    vi.useFakeTimers()
    patchUiState({ sid: 'tab-a', busy: false })
    const request = vi.fn().mockResolvedValue({ lifecycle })
    useDelegationStatus({ request } as Pick<GatewayClient, 'request'>, 'tab-a')
    await vi.advanceTimersByTimeAsync(0)
    expect(request).toHaveBeenCalledWith('delegation.status', { session_id: 'tab-a' })
    expect(getUiState().usage.stalled_subagents).toBe(2)
    const reconciled = reconcileDelegationLifecycle([item], getDelegationState().lifecycle)
    expect(reconciled[0]?.status).toBe('timeout')
    expect(reconciled[0]?.summary).toContain('has not stopped')
    expect(item.status).toBe('running') // Historical evidence is immutable.
    request.mockRejectedValueOnce(new Error('disconnected'))
    await vi.advanceTimersByTimeAsync(1500)
    expect(getUiState().usage.stalled_subagents).toBe(2)
    request.mockResolvedValue({
      lifecycle: { ...lifecycle, stalled_tasks: 0, batches: [{ ...lifecycle.batches[0], runner_settled: true }] }
    })
    await vi.advanceTimersByTimeAsync(1500)
    expect(getUiState().usage.stalled_subagents).toBe(0)
    expect(reconcileDelegationLifecycle([item], getDelegationState().lifecycle)[0]?.summary).toContain('has stopped')

    for (const status of ['error', 'failed', 'interrupted', 'completed']) {
      expect(
        reconcileDelegationLifecycle([item], {
          ...lifecycle,
          batches: [{ delegation_id: 'batch', task_count: 2, runner_settled: true, status }]
        })[0]?.status
      ).toBe(status)
    }
  })

  it('never overlaps requests or applies a late response to another session', async () => {
    vi.useFakeTimers()
    patchUiState({ sid: 'tab-a', usage: { ...getUiState().usage, stalled_subagents: 0 } })
    let resolve!: (value: unknown) => void

    const request = vi.fn(
      () =>
        new Promise(r => {
          resolve = r
        })
    )

    useDelegationStatus({ request } as Pick<GatewayClient, 'request'>, 'tab-a')
    await vi.advanceTimersByTimeAsync(4500)
    expect(request).toHaveBeenCalledTimes(1)
    patchUiState({ sid: 'tab-b' })
    resolve({ lifecycle })
    await vi.advanceTimersByTimeAsync(0)
    expect(getUiState().usage.stalled_subagents).toBe(0)
    expect(getDelegationState().lifecycle).toBeNull()
  })
})
