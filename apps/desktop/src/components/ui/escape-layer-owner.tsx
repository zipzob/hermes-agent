import { useLayoutEffect } from 'react'

import { pushEscapeLayer } from '@/lib/escape-layers'

/** Register a visual interaction layer only while its portaled content is mounted. */
export function EscapeLayerOwner({ priority }: { priority: number }) {
  useLayoutEffect(() => pushEscapeLayer(priority), [priority])

  return null
}
