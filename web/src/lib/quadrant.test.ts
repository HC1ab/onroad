import { describe, expect, it } from 'vitest'
import type { AreaItem } from '../api/types'
import { buildPoints, classify, countPriority, niceMax, ticks } from './quadrant'

const area = (over: Partial<AreaItem>): AreaItem => ({
  adm_cd: '21090730',
  adm_name: '우1동',
  sido: '부산광역시',
  sigungu: '해운대구',
  n_analyzed: 20,
  n_short: 5,
  short_ratio: 0.25,
  mean_gap_s: 2,
  ratio_65plus: 0.2,
  quadrant: null,
  n_candidate: 3,
  low_sample: false,
  ...over,
})

describe('classify', () => {
  const t = { x: 0.2, y: 0.25 }
  it('두 축이 모두 경계 이상이면 high_high', () => {
    expect(classify(0.3, 0.3, t)).toBe('high_high')
  })
  it('경계선과 같은 값은 high 로 본다', () => {
    expect(classify(0.2, 0.25, t)).toBe('high_high')
  })
  it('축별로 따로 판정한다', () => {
    expect(classify(0.3, 0.1, t)).toBe('high_low')
    expect(classify(0.1, 0.3, t)).toBe('low_high')
    expect(classify(0.1, 0.1, t)).toBe('low_low')
  })
})

describe('buildPoints', () => {
  it('비율이 없는 읍면동은 점을 찍지 않고 제외 수에 센다', () => {
    const r = buildPoints(
      [area({}), area({ adm_cd: '1', short_ratio: null }), area({ adm_cd: '2', ratio_65plus: null })],
      { x: 0.2, y: 0.2 },
    )
    expect(r.points).toHaveLength(1)
    expect(r.excluded).toBe(2)
  })
})

describe('countPriority', () => {
  it('오른쪽 위 칸에서 표본 부족은 빼고 센다', () => {
    const t = { x: 0.2, y: 0.2 }
    const { points } = buildPoints(
      [
        area({ adm_cd: 'a', short_ratio: 0.3, ratio_65plus: 0.3 }),
        area({ adm_cd: 'b', short_ratio: 0.3, ratio_65plus: 0.3, low_sample: true }),
        area({ adm_cd: 'c', short_ratio: 0.1, ratio_65plus: 0.3 }),
      ],
      t,
    )
    expect(countPriority(points)).toBe(1)
  })
})

describe('niceMax', () => {
  it('최소 0.5 를 보장한다', () => {
    expect(niceMax([0.12, 0.3])).toBe(0.5)
  })
  it('0.1 단위로 올린다', () => {
    expect(niceMax([0.61])).toBe(0.7)
    expect(niceMax([0.6])).toBe(0.6)
  })
  it('1 을 넘지 않는다', () => {
    expect(niceMax([1])).toBe(1)
  })
})

describe('ticks', () => {
  it('좁은 범위는 0.1 간격', () => {
    expect(ticks(0.5)).toEqual([0, 0.1, 0.2, 0.3, 0.4, 0.5])
  })
  it('넓은 범위는 0.2 간격', () => {
    expect(ticks(1)).toEqual([0, 0.2, 0.4, 0.6, 0.8, 1])
  })
})
