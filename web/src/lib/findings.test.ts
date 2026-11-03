import { describe, expect, it } from 'vitest'
import type { PointProps, PointsResponse, ValidationResponse } from '../api/types'
import { computeFindings } from './findings'

const pt = (p: Partial<PointProps>): PointsResponse['features'][number] => ({
  type: 'Feature',
  geometry: { type: 'Point', coordinates: [129, 35] },
  properties: {
    cw_id: 'x', adm_cd: '1', status: 'analyzed', length_m: 30, green_s: 37, t_need_s: null, gap_s: null,
    flags: null, exposure_cnt: 0, is_candidate: false, exclude_reason: null, ...p,
  },
})

const points: PointsResponse = {
  type: 'FeatureCollection',
  features: [
    pt({ tier: 1, formula_class: '1.0', add_s: 12, coverage_now: 0.7, coverage_required: 0.95 }),
    pt({ tier: 1, formula_class: '0.7', add_s: 0, coverage_now: 0.9, coverage_required: 0.9 }),
    pt({ tier: 1, formula_class: '1.0', add_s: 6, coverage_now: 0.8, coverage_required: 0.95 }),
    pt({ tier: 3, formula_class: '1.0', add_s: 2.5 }),
    pt({ tier: 3, formula_class: '1.0', add_s: 0.5 }),
    pt({ tier: 2, formula_class: '1.0', add_s: 0 }),
    pt({ tier: 1, status: 'excluded', add_s: null }),
  ],
} as PointsResponse

const validation = {
  v1: null, v2: null, v4: null, v5: null,
  v3: { speed: 0.7, recent_years: [2021, 2025], overlap_ratio: 0.12, ratio_vs_random: 1.43, p_value: 0.001, n_permutations: 1000, random_distribution: [] },
  v7: { groups: [{ group: 'child_zone', radius_m: 150, n: 200, n_formula_07: 50 }] },
} as ValidationResponse

describe('첫 화면 발견 카드 수치', () => {
  const f = computeFindings(points, validation)

  it('보호구역 기준: 분석한 점만 세고, 0.7식과 어린이보호구역 비율을 함께 낸다', () => {
    expect(f.zone).toEqual({ n: 3, n07: 1, childRatio: 0.25 })
  })

  it('2초 이상 추가 중 보호구역 몫과 평균 추가 초·커버리지', () => {
    expect(f.focus).toMatchObject({ nAdd2: 3, zoneAdd2: 2, zoneMeanAdd: 9, restMeanAdd: 1.5 })
    expect(f.focus?.zoneCovNow).toBeCloseTo(0.8)
    expect(f.focus?.zoneCovReq).toBeCloseTo(0.9333, 3)
  })

  it('사고다발지역 겹침은 V3 결과를 그대로 쓴다', () => {
    expect(f.accident).toMatchObject({ ratio: 0.12, vsRandom: 1.43, p: 0.001 })
  })

  it('데이터가 없으면 카드를 비운다', () => {
    expect(computeFindings(null, null)).toEqual({ zone: null, focus: null, accident: null })
  })
})
