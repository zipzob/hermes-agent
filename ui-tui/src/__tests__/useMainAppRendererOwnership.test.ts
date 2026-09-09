import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

const source = readFileSync(join(dirname(fileURLToPath(import.meta.url)), '../app/useMainApp.ts'), 'utf8')

describe('terminal repaint ownership', () => {
  it('leaves focus and resize repaint recovery to the Ink renderer', () => {
    expect(source).not.toContain('useTerminalFocus')
    expect(source).not.toMatch(/setCols\(stdout\.columns \?\? 80\)\s+forceRedraw\(stdout\)/)
    expect(source).toContain('setCols(stdout.columns ?? 80)')
  })
})
