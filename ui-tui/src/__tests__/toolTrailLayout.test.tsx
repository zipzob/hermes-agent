import { PassThrough } from 'stream'

import { renderSync } from '@hermes/ink'
import { stripAnsi } from '@hermes/shared/ansi'
import React from 'react'
import { describe, expect, it } from 'vitest'

import { ToolTrail } from '../components/thinking.js'
import { DEFAULT_THEME } from '../theme.js'

const renderTrailAt = (columns: number) => {
  const stdout = new PassThrough()
  const stdin = new PassThrough()
  const stderr = new PassThrough()
  let output = ''

  Object.assign(stdout, { columns, isTTY: false, rows: 20 })
  Object.assign(stdin, { isTTY: false })
  Object.assign(stderr, { isTTY: false })
  stdout.on('data', chunk => {
    output += chunk.toString()
  })

  const instance = renderSync(
    <ToolTrail
      detailsMode="expanded"
      t={DEFAULT_THEME}
      tools={[{ context: 'very-long-file-name.ts', id: 'patch-1', name: 'patch' }]}
    />,
    {
      patchConsole: false,
      stderr: stderr as NodeJS.WriteStream,
      stdin: stdin as NodeJS.ReadStream,
      stdout: stdout as NodeJS.WriteStream
    }
  )

  return {
    frame: () => stripAnsi(output),
    unmount: () => {
      instance.unmount()
      instance.cleanup()
    }
  }
}

describe('ToolTrail narrow live-tool layout', () => {
  it('keeps the Patch label beside its nonshrinking live indicator at the wrap boundary', () => {
    const trail = renderTrailAt(13)

    try {
      const toolLine = trail.frame().split('\n').find(line => line.includes('●')) ?? ''

      // Thirteen columns cannot fit the complete label, but it must reserve
      // room for the label rather than emitting an indicator-only row.
      expect(toolLine).toMatch(/└─ ● \S Patc/)
      expect(toolLine).not.toMatch(/● \S\s*$/)
    } finally {
      trail.unmount()
    }
  })
})
