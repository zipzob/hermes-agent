import { describe, expect, it } from 'vitest'

import Output from './output.js'
import { cellAt, CharPool, createScreen, HyperlinkPool, StylePool } from './screen.js'

const WIDTH = 8
const HEIGHT = 4

function createOutput() {
  const stylePool = new StylePool()
  const screen = createScreen(WIDTH, HEIGHT, stylePool, new CharPool(), new HyperlinkPool())

  return new Output({ height: HEIGHT, screen, stylePool, width: WIDTH })
}

describe('Output absolute clears', () => {
  it('excludes a later disjoint absolute clear from a previous-screen blit', () => {
    const previous = createOutput()
    previous.write(0, 2, 'STALE')
    const previousScreen = previous.get()

    const output = createOutput()
    output.blit(previousScreen, 0, 0, WIDTH, HEIGHT)
    output.clear({ height: 1, width: WIDTH, x: 0, y: 0 }, true)
    output.clear({ height: 1, width: WIDTH, x: 0, y: 2 }, true)
    const screen = output.get()

    expect(cellAt(screen, 0, 2)?.char).toBe(' ')
    expect(cellAt(screen, 1, 2)?.char).toBe(' ')
    expect(cellAt(screen, 0, 1)?.char).toBe(' ')
  })
})
