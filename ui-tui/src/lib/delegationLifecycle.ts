import type { DelegationLifecycle } from '../gatewayTypes.js'
import type { SubagentProgress } from '../types.js'

/** Progress events are detail, not authoritative proof that a batch is still running. */
export function reconcileDelegationLifecycle(
  items: SubagentProgress[],
  lifecycle: DelegationLifecycle | null
): SubagentProgress[] {
  if (!lifecycle) {
    return items
  }

  const batches = new Map(lifecycle.batches.map(batch => [batch.delegation_id, batch]))

  return items.map(item => {
    if (!item.delegationId || !['running', 'queued'].includes(item.status)) {
      return item
    }

    const batch = batches.get(item.delegationId)

    if (!batch || ['running', 'stalling', 'finalizing'].includes(batch.status)) {
      return item
    }

    if (batch.status === 'stalled') {
      return {
        ...item,
        status: 'timeout',
        summary: batch.runner_settled
          ? 'Batch stalled; runner has stopped.'
          : 'Batch stalled; runner has not stopped. Capacity remains reserved.'
      }
    }

    if (
      batch.status === 'completed' ||
      batch.status === 'error' ||
      batch.status === 'failed' ||
      batch.status === 'interrupted'
    ) {
      return { ...item, status: batch.status }
    }

    return item
  })
}
