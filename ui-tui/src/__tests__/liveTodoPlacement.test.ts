import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

const here = dirname(fileURLToPath(import.meta.url))
const layoutSource = readFileSync(join(here, '..', 'components', 'appLayout.tsx'), 'utf8')

describe('live todo placement', () => {
  it('keeps the active todo panel mounted outside virtualized transcript rows', () => {
    const virtualRows = layoutSource.indexOf('transcript.virtualRows.slice')
    const bottomSpacer = layoutSource.indexOf('transcript.virtualHistory.bottomSpacer')
    const liveTodo = layoutSource.indexOf('<LiveTodoPanel />')
    const streaming = layoutSource.indexOf('<StreamingAssistant')

    expect(virtualRows).toBeGreaterThan(-1)
    expect(bottomSpacer).toBeGreaterThan(virtualRows)
    expect(liveTodo).toBeGreaterThan(bottomSpacer)
    expect(liveTodo).toBeLessThan(streaming)
    expect(layoutSource).not.toContain('row.index === lastUserIdx')
  })
})
