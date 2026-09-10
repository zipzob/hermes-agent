import { describe, expect, it } from 'vitest'

import { collapsedPaste, looksLikeDroppedPath } from '../app/useComposerState.js'
import { prepareSlashSubmission, shouldInterpolateSubmission } from '../app/useSubmission.js'
import { looksLikeSlashCommand } from '../domain/slash.js'

describe('collapsed slash paste', () => {
  it('keeps the goal command visible while preserving its multiline body', () => {
    const text = '/goal Update Hermes\nPreserve lifecycle fixes\nVerify every contribution'
    const paste = collapsedPaste(text, 1)

    expect(paste.display).toMatch(/^\/goal \[\[/)
    expect(looksLikeSlashCommand(paste.display)).toBe(true)
    expect(paste.token.text).toBe('Update Hermes\nPreserve lifecycle fixes\nVerify every contribution')
    expect(prepareSlashSubmission(paste.display, [paste.token]).command).toBe(text)
  })

  it('does not promote hidden shell or interpolation syntax', () => {
    for (const text of ['!touch /tmp/never-run\nsecond line', '{!touch /tmp/never-run}\nsecond line']) {
      const paste = collapsedPaste(text, 2)

      expect(paste.display.startsWith('!')).toBe(false)
      expect(looksLikeSlashCommand(paste.display)).toBe(false)
      expect(shouldInterpolateSubmission(paste.display)).toBe(false)
      expect(paste.token.text).toBe(text)
    }
  })

  it('keeps inline slash references and absolute paths as ordinary pasted text', () => {
    for (const text of ['Explain /goal\nnot a command', '/home/zip/example\nnot a command']) {
      const paste = collapsedPaste(text, 3)

      expect(looksLikeSlashCommand(paste.display)).toBe(false)
      expect(paste.token.text).toBe(text)
    }
  })
})

describe('looksLikeDroppedPath', () => {
  it('recognizes macOS screenshot temp paths and file URIs', () => {
    expect(looksLikeDroppedPath('/var/folders/x/T/TemporaryItems/Screenshot\\ 2026-04-21\\ at\\ 1.04.43 PM.png')).toBe(
      true
    )
    expect(
      looksLikeDroppedPath('file:///var/folders/x/T/TemporaryItems/Screenshot%202026-04-21%20at%201.04.43%20PM.png')
    ).toBe(true)
  })

  it('rejects normal multiline or plain text paste', () => {
    expect(looksLikeDroppedPath('hello world')).toBe(false)
    expect(looksLikeDroppedPath('line one\nline two')).toBe(false)
  })

  it('recognizes common image file extensions', () => {
    expect(looksLikeDroppedPath('/Users/me/Desktop/photo.jpg')).toBe(true)
    expect(looksLikeDroppedPath('/Users/me/Desktop/diagram.png')).toBe(true)
    expect(looksLikeDroppedPath('/tmp/capture.webp')).toBe(true)
    expect(looksLikeDroppedPath('/tmp/image.gif')).toBe(true)
  })

  it('recognizes file:// URIs with various extensions', () => {
    expect(looksLikeDroppedPath('file:///home/user/doc.pdf')).toBe(true)
    expect(looksLikeDroppedPath('file:///tmp/screenshot.png')).toBe(true)
  })

  it('recognizes paths with spaces (not backslash-escaped)', () => {
    expect(looksLikeDroppedPath('/var/folders/x/T/TemporaryItems/Screenshot 2026-04-21 at 1.04.43 PM.png')).toBe(true)
  })

  it('rejects empty/whitespace-only input', () => {
    expect(looksLikeDroppedPath('')).toBe(false)
    expect(looksLikeDroppedPath('   ')).toBe(false)
    expect(looksLikeDroppedPath('\n')).toBe(false)
  })

  it('rejects URLs that are not file:// URIs', () => {
    expect(looksLikeDroppedPath('https://example.com/image.png')).toBe(false)
    expect(looksLikeDroppedPath('http://localhost/file.pdf')).toBe(false)
  })

  it('rejects short slash-like strings without path structure', () => {
    // No second '/' or '.' → not a plausible file path
    expect(looksLikeDroppedPath('/help')).toBe(false)
    expect(looksLikeDroppedPath('/model sonnet')).toBe(false)
    expect(looksLikeDroppedPath('/api')).toBe(false)
  })

  it('accepts absolute paths with directory separators or extensions', () => {
    expect(looksLikeDroppedPath('/usr/bin/test')).toBe(true)
    expect(looksLikeDroppedPath('/tmp/file.txt')).toBe(true)
    expect(looksLikeDroppedPath('/etc/hosts')).toBe(true) // has second /
  })
})
