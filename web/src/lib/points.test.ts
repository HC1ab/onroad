import { describe, expect, it } from 'vitest'
import candidates from '@contracts/samples/candidates.json'
import sample from '@contracts/samples/points.json'
import sampleV2 from '@contracts/samples/points_v2.json'
import type { CandidatesResponse, PointsResponse } from '../api/types'
import { candidatesAsPoints, countPoints, DEFAULT_POINT_FILTER, filterPoints, gapWithGreen, mockPointsFor } from './points'

const data = sample as unknown as PointsResponse

describe('횡단보도 점 필터 (피드백 2·12번)', () => {
  it('기본: 분석한 점은 모두, 분석 제외 점은 숨김', () => {
    const c = countPoints(filterPoints(data, DEFAULT_POINT_FILTER))
    expect(c.excluded).toBe(0)
    expect(c.analyzed).toBe(countPoints(data).analyzed)
  })

  it('후보만 · 짧은 초 이상/이하', () => {
    const onlyCand = filterPoints(data, { ...DEFAULT_POINT_FILTER, scope: 'candidates' })
    expect(onlyCand.features.every((f) => f.properties.is_candidate)).toBe(true)
    const gte = filterPoints(data, { ...DEFAULT_POINT_FILTER, gapOp: 'gte', gapValue: 3 })
    expect(gte.features.length).toBeGreaterThan(0)
    expect(gte.features.every((f) => (f.properties.gap_s ?? 0) >= 3)).toBe(true)
    const lte = filterPoints(data, { ...DEFAULT_POINT_FILTER, gapOp: 'lte', gapValue: 0 })
    expect(lte.features.every((f) => (f.properties.gap_s ?? 0) <= 0)).toBe(true)
  })

  it('분석 제외 점을 켜면 함께 나오고, 짧은 초 조건과 무관하다', () => {
    const f = filterPoints(data, { ...DEFAULT_POINT_FILTER, showExcluded: true, gapOp: 'gte', gapValue: 99 })
    expect(f.features.length).toBe(countPoints(data).excluded)
  })
})

describe('짧은 초 계산', () => {
  it('기준식 7 + 연장/속도 와 비교한다', () => {
    expect(gapWithGreen(24, 30, 0.8)).toEqual({ t_need_s: 37, gap_s: 7 })
    expect(gapWithGreen(10, 30, 1.0)).toEqual({ t_need_s: 17, gap_s: -13 })
  })

  it('mock: 속도가 느릴수록 짧은 초가 커진다', () => {
    const at07 = mockPointsFor(data, 0.7, 300)
    const at10 = mockPointsFor(data, 1.0, 300)
    const id = data.features.find((f) => f.properties.status === 'analyzed')!.properties.cw_id
    const g = (d: PointsResponse) => d.features.find((f) => f.properties.cw_id === id)!.properties.gap_s!
    expect(g(at07)).toBeGreaterThan(g(at10))
  })
})

describe('전체 점이 없을 때 후보 점으로 대신', () => {
  it('후보 속성만 채우고 나머지는 null', () => {
    const p = candidatesAsPoints(candidates as unknown as CandidatesResponse)
    expect(p.features.length).toBe(candidates.features.length)
    expect(p.features[0].properties).toMatchObject({ status: 'analyzed', is_candidate: true, length_m: null, green_s: null })
  })
})

describe('적용 기준 필터 (첫 화면 발견 카드)', () => {
  const v2 = sampleV2 as unknown as PointsResponse

  it('3단계 기준 화면에서는 고른 기준의 점만 남긴다', () => {
    const z = filterPoints(v2, { ...DEFAULT_POINT_FILTER, tier: 1 }, true)
    expect(z.features.length).toBeGreaterThan(0)
    expect(z.features.every((f) => f.properties.tier === 1)).toBe(true)
  })

  it('기록값 화면에서는 적용 기준을 보지 않는다', () => {
    expect(filterPoints(v2, { ...DEFAULT_POINT_FILTER, tier: 1 }).features.length)
      .toBe(filterPoints(v2, DEFAULT_POINT_FILTER).features.length)
  })
})
