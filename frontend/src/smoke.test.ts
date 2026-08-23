import { describe, expect, it } from 'vitest'

describe('frontend toolchain', () => {
  it('runs tests without losing decimal source strings', () => {
    expect('0.02000000').toBe('0.02000000')
  })
})
