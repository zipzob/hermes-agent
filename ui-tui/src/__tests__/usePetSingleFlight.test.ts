import { describe, expect, it, vi } from 'vitest'

import { runPetSyncSingleFlight } from '../app/usePet.js'

describe('pet synchronization', () => {
  it('deduplicates overlapping cosmetic frame requests and releases after failure', async () => {
    const lock = { current: false }
    let release: (() => void) | undefined
    const firstTask = vi.fn(() => new Promise<void>(resolve => (release = resolve)))
    const duplicateTask = vi.fn(async () => undefined)

    const first = runPetSyncSingleFlight(lock, firstTask)
    const duplicate = runPetSyncSingleFlight(lock, duplicateTask)

    expect(firstTask).toHaveBeenCalledOnce()
    expect(duplicateTask).not.toHaveBeenCalled()

    release?.()
    await Promise.all([first, duplicate])

    await expect(runPetSyncSingleFlight(lock, async () => Promise.reject(new Error('cosmetic timeout')))).rejects.toThrow(
      'cosmetic timeout'
    )
    expect(lock.current).toBe(false)
  })
})
