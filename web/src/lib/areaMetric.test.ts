import { describe, expect, it } from 'vitest'
import type { AreaItem } from '../api/types'
import { ADD_METRIC, RATIO_METRIC, withQuantileSteps } from './areaMetric'

const area = (i: number, v: Partial<AreaItem>): AreaItem =>
  ({ adm_cd: String(2600000000 + i), low_sample: false, short_ratio: null, mean_add_s: null, ...v }) as AreaItem

describe('withQuantileSteps', () => {
  it('값을 5분위로 나눠 5색을 모두 쓴다', () => {
    const items = Array.from({ length: 100 }, (_, i) => area(i, { mean_add_s: i / 10 }))
    const m = withQuantileSteps(ADD_METRIC, items)
    expect(m.steps.map(([b]) => b)).toEqual([0, 2, 4, 6, 8])
    expect(m.steps.map(([, c]) => c)).toEqual(ADD_METRIC.steps.map(([, c]) => c))
    expect(m.legendStops).toEqual(['0.0초', '2.0초', '4.0초', '6.0초', '8.0초', '9.9초'])
  })

  it('대부분 0 이면 0 위쪽 값을 다시 나눠 색 차이를 남긴다', () => {
    // 실데이터 일괄 속도 1.0 처럼 80% 가 0%
    const items = Array.from({ length: 50 }, (_, i) => area(i, { short_ratio: i < 40 ? 0 : (i - 39) / 25 }))
    const m = withQuantileSteps(RATIO_METRIC, items)
    expect(m.steps[0][0]).toBe(0)
    expect(m.steps.length).toBeGreaterThanOrEqual(4)
    expect(m.steps[1][0]).toBeGreaterThan(0)
  })

  it('표본 부족과 값 없음은 빼고 계산한다', () => {
    const items = [
      ...Array.from({ length: 10 }, (_, i) => area(i, { mean_add_s: i })),
      area(50, { mean_add_s: 100, low_sample: true }),
      area(51, { mean_add_s: null }),
    ]
    const m = withQuantileSteps(ADD_METRIC, items)
    expect(m.scale).toEqual(['0.0초', '9.0초'])
  })

  it('값이 한쪽에 몰려 경계가 겹치면 합치고, 색은 양 끝을 살린다', () => {
    // 실데이터 일괄 속도 0.8 처럼 대부분 100%
    const items = Array.from({ length: 20 }, (_, i) => area(i, { short_ratio: i < 4 ? 0.5 + i / 10 : 1 }))
    const m = withQuantileSteps(RATIO_METRIC, items)
    const bs = m.steps.map(([b]) => b)
    expect(new Set(bs).size).toBe(bs.length)
    expect(bs).toEqual([...bs].sort((a, b) => a - b))
    expect(m.steps[0][1]).toBe(RATIO_METRIC.steps[0][1])
    expect(m.steps[m.steps.length - 1][1]).toBe(RATIO_METRIC.steps[RATIO_METRIC.steps.length - 1][1])
  })

  it('값이 2개 미만이면 고정 구간 그대로', () => {
    expect(withQuantileSteps(ADD_METRIC, [area(1, { mean_add_s: 3 })])).toBe(ADD_METRIC)
  })
})
