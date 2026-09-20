import { PassThrough } from 'stream'

import { renderSync } from '@hermes/ink'
import { stripAnsi } from '@hermes/shared/ansi'
import React from 'react'
import { describe, expect, it } from 'vitest'

import { Thinking } from '../components/thinking.js'
import { DEFAULT_THEME } from '../theme.js'

const renderThinking = (reasoning: string, active = true) => {
  const stdout = new PassThrough()
  const stdin = new PassThrough()
  const stderr = new PassThrough()
  let output = ''

  Object.assign(stdout, { columns: 40, isTTY: false, rows: 10 })
  Object.assign(stdin, { isTTY: false })
  Object.assign(stderr, { isTTY: false })
  stdout.on('data', chunk => {
    output += chunk.toString()
  })

  const instance = renderSync(<Thinking active={active} reasoning={reasoning} streaming={false} t={DEFAULT_THEME} />, {
    patchConsole: false,
    stderr: stderr as NodeJS.WriteStream,
    stdin: stdin as NodeJS.ReadStream,
    stdout: stdout as NodeJS.WriteStream
  })

  return { instance, output: () => stripAnsi(output) }
}

describe('Thinking pending activity', () => {
  it('renders a one-cell activity glyph before reasoning text arrives', () => {
    const { instance, output } = renderThinking('')
    const line =
      output()
        .split('\n')
        .find(candidate => candidate.includes('└─')) ?? ''

    expect(line).toMatch(/└─ \S/)
    expect([...line.slice(line.indexOf('└─ ') + 3)].length).toBe(1)

    instance.unmount()
    instance.cleanup()
  })

  it('keeps an inactive empty thinking row absent', () => {
    const { instance, output } = renderThinking('', false)

    expect(output()).toBe('')

    instance.unmount()
    instance.cleanup()
  })

  it('uses the same tree lead before and after reasoning arrives', () => {
    const pending = renderThinking('')
    const reasoning = renderThinking('first reasoning token')
    const pendingLine =
      pending
        .output()
        .split('\n')
        .find(candidate => candidate.includes('└─')) ?? ''
    const reasoningLine =
      reasoning
        .output()
        .split('\n')
        .find(candidate => candidate.includes('└─')) ?? ''

    expect(pendingLine.slice(0, pendingLine.indexOf('└─ ') + 3)).toBe(
      reasoningLine.slice(0, reasoningLine.indexOf('└─ ') + 3)
    )

    pending.instance.unmount()
    pending.instance.cleanup()
    reasoning.instance.unmount()
    reasoning.instance.cleanup()
  })
})
