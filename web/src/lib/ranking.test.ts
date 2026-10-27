import { describe, expect, it } from 'vitest'
import type { AreaItem, CrosswalkItem } from '../api/types'
import { rankAreas, sortCrosswalks } from './ranking'

const area = (over: Partial<AreaItem>): AreaItem => ({
  adm_cd: '1',
  adm_name: '가동',
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

describe('rankAreas', () => {
  const items = [
    area({ adm_cd: 'a', adm_name: '가동', short_ratio: 0.1, n_candidate: 9, ratio_65plus: 0.4 }),
    area({ adm_cd: 'b', adm_name: '나동', short_ratio: 0.3, n_candidate: 1 }),
    area({ adm_cd: 'c', adm_name: '다동', short_ratio: 0.5, low_sample: true }),
    area({ adm_cd: 'd', adm_name: '라동', short_ratio: null }),
    area({ adm_cd: 'e', adm_name: '마동', short_ratio: 0.2, ratio_65plus: null }),
  ]

  it('짧음 비율 높은 순, 표본 부족과 값 없음은 뺀다', () => {
    const r = rankAreas(items, 'short_ratio', 10)
    expect(r.rows.map((x) => x.adm_cd)).toEqual(['b', 'e', 'a'])
    expect(r.excludedLowSample).toBe(1)
    expect(r.excludedNoValue).toBe(1)
  })

  it('정렬 기준을 바꿀 수 있다', () => {
    expect(rankAreas(items, 'n_candidate', 10).rows[0].adm_cd).toBe('a')
  })

  it('65세 비율 정렬에서는 그 값이 없는 곳도 뺀다', () => {
    const r = rankAreas(items, 'ratio_65plus', 10)
    expect(r.rows.map((x) => x.adm_cd)).toEqual(['a', 'b'])
    expect(r.excludedNoValue).toBe(2)
  })

  it('N 개까지만 돌려준다', () => {
    expect(rankAreas(items, 'short_ratio', 2).rows).toHaveLength(2)
  })

  it('같은 값이면 짧음 건수, 이름 순으로 정한다', () => {
    const tie = [
      area({ adm_cd: 'x', adm_name: '나동', short_ratio: 0.3, n_short: 3 }),
      area({ adm_cd: 'y', adm_name: '가동', short_ratio: 0.3, n_short: 3 }),
      area({ adm_cd: 'z', adm_name: '다동', short_ratio: 0.3, n_short: 6 }),
    ]
    expect(rankAreas(tie, 'short_ratio', 10).rows.map((x) => x.adm_cd)).toEqual(['z', 'y', 'x'])
  })
})

describe('sortCrosswalks', () => {
  const cw = (cw_id: string, gap_s: number): CrosswalkItem => ({
    cw_id, lat: 35, lon: 129, length_m: 20, green_s: 30, t_need_s: 32, gap_s,
    flags: { senior_center: false, market: false, protect_zone: false, crash_zone_past: false },
    exposure_cnt: 0, is_candidate: false,
  })
  const list = [cw('a', 1), cw('b', -2), cw('c', 5), cw('d', 0)]

  it('짧은 초 큰 순으로 정렬한다', () => {
    expect(sortCrosswalks(list, false).map((c) => c.cw_id)).toEqual(['c', 'a', 'd', 'b'])
  })

  it('짧은 곳만 보면 gap > 0 만 남긴다', () => {
    expect(sortCrosswalks(list, true).map((c) => c.cw_id)).toEqual(['c', 'a'])
  })
})
