import { describe, expect, it } from 'vitest'
import points from '@contracts/samples/points.json'
import areas from '@contracts/samples/areas.json'
import type { AreasResponse, PointsResponse } from '../api/types'
import { mockAreasV2, mockPointsV2 } from './mockV2'
import { appliedSpeed, elderlyCoverage, mixtureSpeed, normCdf, requiredSeconds, tierOf } from './recommend'

describe('3단계 기준 계산 (결정 009)', () => {
  it('정규 누적분포', () => {
    expect(normCdf(0)).toBeCloseTo(0.5, 6)
    expect(normCdf(-1.0364)).toBeCloseTo(0.15, 3)
  })

  it('섞인 분포의 15퍼센타일: p=0 이면 일반 1.01, p=1 이면 고령 0.85', () => {
    expect(mixtureSpeed(0, 0.85)).toBeCloseTo(1.01, 2)
    expect(mixtureSpeed(1, 0.85)).toBeCloseTo(0.85, 2)
    expect(mixtureSpeed(0.3, 0.9)).toBeLessThan(mixtureSpeed(0.3, 0.85))
  })

  it('단계와 적용 속도: 1단계 0.7 고정, 그 외 0.7~1.0 로 자름', () => {
    expect(tierOf({ protect_zone: true, market: true, senior_center: false, crash_zone_past: false })).toBe(1)
    expect(tierOf({ protect_zone: false, market: true, senior_center: false, crash_zone_past: false })).toBe(2)
    expect(tierOf(null)).toBe(3)
    expect(appliedSpeed(1, 1, 0.85)).toBe(0.7)
    expect(appliedSpeed(3, 0, 0.85)).toBe(1.0)
  })

  it('필요 시간은 기록값보다 줄이지 않는다', () => {
    expect(requiredSeconds(60, 20, 1.0)).toBe(60)
    expect(requiredSeconds(30, 20, 0.8)).toBe(32)
  })

  it('고령 커버리지: 0.85m/s 로 딱 맞는 시간이면 85%', () => {
    expect(elderlyCoverage(17, 7 + 17 / 0.85)).toBeCloseTo(0.85, 2)
    expect(elderlyCoverage(17, 7)).toBe(0)
  })
})

describe('v2 mock', () => {
  const pv = mockPointsV2(points as unknown as PointsResponse, areas as AreasResponse, 0.85, 300)
  const props = pv.features.map((f) => f.properties)

  it('단계 1·2·3 과 data_check 가 모두 있다', () => {
    for (const t of [1, 2, 3]) expect(props.some((p) => p.tier === t)).toBe(true)
    expect(props.some((p) => p.status === 'data_check')).toBe(true)
  })

  it('analyzed 는 add_s ≥ 0, 필요 시간 = 기록 + 추가, 커버리지 현재 ≤ 기준 적용', () => {
    for (const p of props.filter((x) => x.status === 'analyzed')) {
      expect(p.add_s!).toBeGreaterThanOrEqual(0)
      expect(p.t_required_s!).toBeCloseTo(p.green_s! + p.add_s!, 1)
      expect(p.coverage_now!).toBeLessThanOrEqual(p.coverage_required!)
    }
  })

  it('목표를 높이면 추가 초 합이 늘어난다', () => {
    const sum = (t: 0.85 | 0.95) =>
      mockPointsV2(points as unknown as PointsResponse, areas as AreasResponse, t, 300).features.reduce((s, f) => s + (f.properties.add_s ?? 0), 0)
    expect(sum(0.95)).toBeGreaterThan(sum(0.85))
  })

  it('읍면동 v2: 표본 미만은 사분면 없음, 경계값은 중앙값', () => {
    const a = mockAreasV2(areas as AreasResponse, pv, 0.85, 300)
    expect(a.items.length).toBe(areas.items.length)
    for (const it of a.items) if (it.low_sample) expect(it.quadrant).toBeNull()
    expect(a.thresholds.mean_add_s_median).toBeGreaterThanOrEqual(0)
  })
})
