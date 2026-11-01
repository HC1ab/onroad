import type { CandidatesResponse, ExcludeReason, PointsResponse, Radius, Speed } from '../api/types'

// 전체 횡단보도 점(지도 점 레이어, 정보 카드)에 쓰는 순수 함수. 화면 코드와 테스트가 함께 쓴다.

export type Bbox = [number, number, number, number]

/** 점 필터 (피드백 2번). 기준 값은 짧은 초(gap_s) */
export interface PointFilter {
  /** all: 분석한 모든 점, candidates: 점검 우선순위 후보만 */
  scope: 'all' | 'candidates'
  /** 짧은 초 조건. null 이면 조건 없음 */
  gapOp: 'gte' | 'lte' | null
  gapValue: number
  /** 분석 제외(녹색신호시간 없음 등) 점 표시 */
  showExcluded: boolean
}

export const DEFAULT_POINT_FILTER: PointFilter = { scope: 'all', gapOp: null, gapValue: 0, showExcluded: false }

export const EXCLUDE_REASON_LABEL: Record<ExcludeReason, string> = {
  green_missing: '녹색신호시간 기록 없음',
  length_missing: '횡단보도 연장 기록 없음',
  green_out_of_range: '녹색신호시간이 정제 범위 밖',
  length_out_of_range: '연장이 정제 범위 밖',
}

export function inBbox([x, y]: number[], [x1, y1, x2, y2]: Bbox): boolean {
  return x >= x1 && x <= x2 && y >= y1 && y <= y2
}

/** 필터를 적용한 점만 남긴다. 클러스터 개수도 이 결과로 센다. */
export function filterPoints(data: PointsResponse, f: PointFilter): PointsResponse {
  const features = data.features.filter(({ properties: p }) => {
    if (p.status === 'excluded') return f.showExcluded
    if (f.scope === 'candidates' && !p.is_candidate) return false
    if (f.gapOp && p.gap_s !== null) {
      if (f.gapOp === 'gte' && p.gap_s < f.gapValue) return false
      if (f.gapOp === 'lte' && p.gap_s > f.gapValue) return false
    }
    return true
  })
  return { ...data, features }
}

export function countPoints(data: PointsResponse | null) {
  const c = { analyzed: 0, candidates: 0, excluded: 0 }
  for (const { properties: p } of data?.features ?? []) {
    if (p.status === 'excluded') c.excluded++
    else {
      c.analyzed++
      if (p.is_candidate) c.candidates++
    }
  }
  return c
}

/** 기준식 필요 시간(초) = 진입 시간 + 연장/속도. 진입 시간은 config.yaml(entry_seconds)과 같게 둔다(사용자 입력·mock 계산용). */
export const ENTRY_S = 7
export const needSeconds = (length_m: number, speed: Speed) => Math.round((ENTRY_S + length_m / speed) * 10) / 10

/** 사용자가 넣은 녹색신호시간으로 그 횡단보도만 기준식과 비교한다(내 입력 기준). */
export function gapWithGreen(length_m: number, green_s: number, speed: Speed) {
  const t_need_s = needSeconds(length_m, speed)
  return { t_need_s, gap_s: Math.round((t_need_s - green_s) * 10) / 10 }
}

/**
 * 서버에 전체 점이 아직 없으면 후보 점으로 대신 그린다(색은 짧은 초, 정보 카드는 일부 값만).
 * 후보만 있으므로 기준식보다 여유 있는 점은 나오지 않는다.
 */
export function candidatesAsPoints(c: CandidatesResponse): PointsResponse {
  return {
    type: 'FeatureCollection',
    _sample: c._sample,
    speed: c.speed,
    radius_m: c.radius_m,
    features: c.features.map((f) => ({
      type: 'Feature',
      geometry: f.geometry,
      properties: {
        cw_id: f.properties.cw_id,
        adm_cd: f.properties.adm_cd,
        status: 'analyzed',
        length_m: null,
        green_s: null,
        t_need_s: null,
        gap_s: f.properties.gap_s,
        flags: null,
        exposure_cnt: f.properties.exposure_cnt,
        is_candidate: true,
        exclude_reason: null,
      },
    })),
  }
}

/**
 * mock 전용: 샘플은 0.8 m/s · 300m 값이라 속도에 맞게 필요 시간·짧은 초를 기준식으로 다시 계산하고,
 * 반경 200m 는 노출이 1개뿐인 점을 후보에서 빼는 것으로 흉내 낸다.
 */
export function mockPointsFor(sample: PointsResponse, speed: Speed, radius: Radius): PointsResponse {
  return {
    ...sample,
    speed,
    radius_m: radius,
    features: sample.features.map((f) => {
      const p = f.properties
      if (p.status === 'excluded' || p.length_m === null || p.green_s === null) return f
      const { t_need_s, gap_s } = gapWithGreen(p.length_m, p.green_s, speed)
      const minExposure = radius === 200 ? 2 : 1
      return { ...f, properties: { ...p, t_need_s, gap_s, is_candidate: gap_s > 0 && p.exposure_cnt >= minExposure } }
    }),
  }
}
