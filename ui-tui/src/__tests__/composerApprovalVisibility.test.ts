import { describe, expect, it } from 'vitest'

import { composerDraftVisible } from '../app/overlayStore.js'

const emptyOverlay = {
  agents: false,
  agentsInitialHistoryIndex: 0,
  ambient: [],
  approval: null,
  billing: null,
  clarify: null,
  confirm: null,
  journey: false,
  modelPicker: false,
  pager: null,
  petPicker: false,
  pluginsHub: false,
  secret: null,
  sessions: false,
  skillsHub: false,
  subscription: null,
  sudo: null,
  vaultUnlock: null,
  widget: null
}

describe('composer draft visibility while another input layer owns keys', () => {
  it('keeps the draft mounted behind approval and other prompt-flow cards', () => {
    for (const key of ['approval', 'billing', 'clarify', 'confirm', 'secret', 'subscription', 'sudo', 'vaultUnlock']) {
      expect(composerDraftVisible({ ...emptyOverlay, [key]: {} } as never)).toBe(true)
    }
  })

  it('hides the draft behind full/floating navigation surfaces', () => {
    for (const key of [
      'agents',
      'journey',
      'modelPicker',
      'pager',
      'petPicker',
      'pluginsHub',
      'sessions',
      'skillsHub',
      'widget'
    ]) {
      expect(composerDraftVisible({ ...emptyOverlay, [key]: {} } as never)).toBe(false)
    }
  })
})
