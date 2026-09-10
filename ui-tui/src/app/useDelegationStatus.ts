import { useEffect } from 'react'

import type { GatewayClient } from '../gatewayClient.js'
import type { DelegationStatusResponse } from '../gatewayTypes.js'
import { asRpcResult } from '../lib/rpc.js'

import { applyDelegationStatus, patchDelegationState } from './delegationStore.js'
import { getUiState, patchUiState } from './uiStore.js'

/** Poll outside the parent turn: idle and stalled workers still need reconciliation. */
export function useDelegationStatus(gw: Pick<GatewayClient, 'request'>, sid: string | null) {
  useEffect(() => {
    patchDelegationState({ lifecycle: null })

    if (!sid) {
      return
    }

    let disposed = false
    let pending = false

    const refresh = async () => {
      if (disposed || pending) {
        return
      }

      pending = true

      try {
        const result = asRpcResult<DelegationStatusResponse>(await gw.request('delegation.status', { session_id: sid }))

        if (disposed || getUiState().sid !== sid || !result?.lifecycle) {
          return
        }

        applyDelegationStatus(result)
        const usage = getUiState().usage
        const { active_tasks, stalled_tasks } = result.lifecycle

        if (usage.active_subagents !== active_tasks || usage.stalled_subagents !== stalled_tasks) {
          patchUiState({ usage: { ...usage, active_subagents: active_tasks, stalled_subagents: stalled_tasks } })
        }
      } catch {
        // A failed poll is unknown, not proof that workers have stopped.
      } finally {
        pending = false
      }
    }

    void refresh()
    const timer = setInterval(() => void refresh(), 1500)

    return () => {
      disposed = true
      clearInterval(timer)
    }
  }, [gw, sid])
}
