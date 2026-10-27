import { describe, expect, it } from 'vitest'
import { histogram, mean, pValue, rho } from './validation'

describe('histogram', () => {
  it('모든 값을 빠짐없이 센다', () => {
    const h = histogram([0.1, 0.12, 0.15, 0.2, 0.22], 4)
    expect(h).toHaveLength(4)
    expect(h.reduce((s, b) => s + b.count, 0)).toBe(5)
  })
  it('최댓값은 마지막 구간에 들어간다', () => {
    const h = histogram([0, 1], 2)
    expect(h.map((b) => b.count)).toEqual([1, 1])
  })
  it('include 값까지 범위를 넓힌다', () => {
    const h = histogram([0.1, 0.2], 4, 0.4)
    expect(h[h.length - 1].x1).toBeCloseTo(0.4)
    expect(h.reduce((s, b) => s + b.count, 0)).toBe(2)
  })
  it('값이 모두 같아도 나눌 수 있다', () => {
    expect(histogram([0.3, 0.3], 3).reduce((s, b) => s + b.count, 0)).toBe(2)
  })
  it('값이 없으면 빈 배열', () => {
    expect(histogram([])).toEqual([])
  })
})

describe('표시 함수', () => {
  it('mean', () => {
    expect(mean([0, 0, 2, 1, 0, 2])).toBeCloseTo(0.833, 2)
    expect(mean([])).toBeNull()
  })
  it('rho 는 음수에 긴 빼기표를 쓴다', () => {
    expect(rho(-0.12)).toBe('−0.12')
    expect(rho(0.9)).toBe('0.90')
  })
  it('pValue', () => {
    expect(pValue(0.02)).toBe('0.02')
    expect(pValue(0.0004)).toBe('< 0.001')
  })
})
