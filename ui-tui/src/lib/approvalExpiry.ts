import { useEffect, useState } from 'react'

export function formatApprovalExpiry(expiresAtMs: number, nowMs = Date.now()): string {
  const remaining = Math.max(0, Math.ceil((expiresAtMs - nowMs) / 1_000))
  const minutes = Math.floor(remaining / 60)
  const seconds = remaining % 60

  return `Expires in: ${minutes}m ${seconds.toString().padStart(2, '0')}s (no response: deny)`
}

export function useApprovalExpiry(expiresAtMs?: number): null | string {
  const [nowMs, setNowMs] = useState(() => Date.now())

  useEffect(() => {
    if (expiresAtMs === undefined) {
      return
    }

    setNowMs(Date.now())
    const timer = setInterval(() => setNowMs(Date.now()), 1_000)

    return () => clearInterval(timer)
  }, [expiresAtMs])

  return expiresAtMs === undefined ? null : formatApprovalExpiry(expiresAtMs, nowMs)
}
