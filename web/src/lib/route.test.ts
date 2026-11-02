import { describe, expect, it } from 'vitest'
import { parseRoute } from './route'

describe('화면 주소', () => {
  it('지도·검증·About', () => {
    expect(parseRoute('')).toBe('map')
    expect(parseRoute('#/')).toBe('map')
    expect(parseRoute('#/validation')).toBe('validation')
    expect(parseRoute('#/about')).toBe('about')
    expect(parseRoute('#/about?x=1')).toBe('about')
    expect(parseRoute('#/unknown')).toBe('map')
  })
})
