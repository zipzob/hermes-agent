/**
 * Ordered Escape ownership for the app's transient window-level layers.
 *
 * Several surfaces bind their own `window` `keydown` Escape handler (narrow-pane
 * reveal, layout edit mode, the zone editor, full-page overlays). Without a
 * shared order a single Escape fired all of them at once — closing a pinned
 * pane *and* exiting edit mode, or dismissing an overlay *and* the pane beneath
 * it. Shared Radix dialogs register their mounted portal content here too:
 * window capture handlers otherwise run before Radix can stop propagation.
 *
 * Contract for a layer handler:
 *   1. bail if `event.defaultPrevented` (a higher propagation-stopping layer
 *      already handled it);
 *   2. bail unless `isTopEscapeLayer(myPriority)` (a higher app layer is open);
 *   3. otherwise act and `event.preventDefault()`.
 *
 * A layer registers its priority (via `pushEscapeLayer`) only while it's open.
 */

// Higher number = closer to the user. Gaps leave room to slot new layers.
export const ESCAPE_PRIORITY = {
  // Global approval shortcuts are a fallback interaction surface. Any modal,
  // overlay, editor, or drag visibly in front must receive Escape first.
  approval: 0,
  narrowOverlay: 10,
  layoutEdit: 20,
  zoneEditor: 30,
  overlay: 40,
  // An in-flight pane drag: Esc means "abort the drag", never ALSO exit edit
  // mode / close the overlay the drag started over. Registered only for the
  // drag's few-hundred-ms lifetime (drag-session.ts).
  drag: 50,
  // Shared Radix dialogs are portaled above the rest of the application and
  // therefore own Escape over every window-level shortcut beneath them.
  modal: 100
} as const

const active = new Map<symbol, number>()

/** Register a layer as open; call the returned disposer when it closes. */
export function pushEscapeLayer(priority: number): () => void {
  const key = Symbol('escape-layer')
  active.set(key, priority)

  return () => {
    active.delete(key)
  }
}

/** True when no open layer outranks `priority`, so its handler should act. */
export function isTopEscapeLayer(priority: number): boolean {
  for (const p of active.values()) {
    if (p > priority) {
      return false
    }
  }

  return true
}
