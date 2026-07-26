import { PassThrough } from 'stream'

import { renderSync } from '@hermes/ink'
import React from 'react'
import { describe, expect, it } from 'vitest'

import { ToolTrail } from '../components/thinking.js'
import { stripAnsi } from '../lib/text.js'
import { DEFAULT_THEME } from '../theme.js'

describe('ToolTrail payload disclosure', () => {
  it('keeps verbose arguments collapsed until the payload disclosure is opened', async () => {
    const stdout = new PassThrough()
    const stdin = new PassThrough()
    const stderr = new PassThrough()
    let output = ''

    Object.assign(stdout, { columns: 100, isTTY: false, rows: 30 })
    Object.assign(stdin, { isTTY: false })
    Object.assign(stderr, { isTTY: false })
    stdout.on('data', chunk => {
      output += chunk.toString()
    })

    const instance = renderSync(
      <ToolTrail
        detailsMode="expanded"
        t={DEFAULT_THEME}
        trail={['Terminal("npm test") (1.0s) :: Args:\n{\n  "command": "npm test"\n}\nResult:\n{\n  "exit_code": 0\n} ✓']}
      />,
      {
        patchConsole: false,
        stderr: stderr as NodeJS.WriteStream,
        stdin: stdin as NodeJS.ReadStream,
        stdout: stdout as NodeJS.WriteStream
      }
    )

    await new Promise(resolve => setImmediate(resolve))
    const frame = stripAnsi(output)
    instance.unmount()
    instance.cleanup()

    expect(frame).toContain('▸ Payload')
    expect(frame).not.toContain('"command": "npm test"')
    expect(frame).not.toContain('"exit_code": 0')
  })
})
