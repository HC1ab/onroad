import type { PointsResponse, ValidationResponse } from '../api/types'
import { ADD_THRESHOLD_S } from './points'

// 첫 화면 "부산에서 찾은 것" 카드 세 장의 수치. 모두 내보낸 점·검증 결과에서 세며, 숫자를 코드에 적지 않는다.

export interface Findings {
  /** 노인보호구역 반경 안(보호구역 기준) 횡단보도 중 기록값이 0.7m/s 기준식과 같은 곳 */
  zone: { n: number; n07: number; childRatio: number | null } | null
  /** 2초 이상 추가가 노인보호구역 주변에 몰려 있는가 */
  focus: {
    nAdd2: number
    zoneAdd2: number
    /** 보호구역 기준 횡단보도 중 추가가 생기는 곳의 평균 추가 초 */
    zoneMeanAdd: number
    zoneCovNow: number
    zoneCovReq: number
    /** 나머지(시장·주민 기준) 중 추가가 생기는 곳의 평균 추가 초 */
    restMeanAdd: number
  } | null
  /** V3: 점검 우선순위 후보와 최근 노인 보행사고 다발지역의 겹침 */
  accident: { ratio: number; vsRandom: number; p: number; years: number[]; speed: number } | null
}

const mean = (xs: number[]) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0)

export function computeFindings(points: PointsResponse | null, validation: ValidationResponse | null): Findings {
  const analyzed = (points?.features ?? []).map((f) => f.properties).filter((p) => p.status === 'analyzed' && p.add_s != null)
  const zone = analyzed.filter((p) => p.tier === 1)
  const child = validation?.v7?.groups.find((g) => g.group === 'child_zone')
  const add = (p: (typeof analyzed)[number]) => p.add_s ?? 0

  return {
    zone: zone.length
      ? {
          n: zone.length,
          n07: zone.filter((p) => p.formula_class === '0.7').length,
          childRatio: child?.n ? child.n_formula_07 / child.n : null,
        }
      : null,
    focus: zone.length
      ? {
          nAdd2: analyzed.filter((p) => add(p) >= ADD_THRESHOLD_S).length,
          zoneAdd2: zone.filter((p) => add(p) >= ADD_THRESHOLD_S).length,
          zoneMeanAdd: mean(zone.filter((p) => add(p) > 0).map(add)),
          zoneCovNow: mean(zone.flatMap((p) => (p.coverage_now != null ? [p.coverage_now] : []))),
          zoneCovReq: mean(zone.flatMap((p) => (p.coverage_required != null ? [p.coverage_required] : []))),
          restMeanAdd: mean(analyzed.filter((p) => p.tier !== 1 && add(p) > 0).map(add)),
        }
      : null,
    accident: validation?.v3
      ? {
          ratio: validation.v3.overlap_ratio,
          vsRandom: validation.v3.ratio_vs_random,
          p: validation.v3.p_value,
          years: validation.v3.recent_years,
          speed: validation.v3.speed,
        }
      : null,
  }
}
