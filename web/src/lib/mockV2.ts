import type {
  AreasResponse,
  AreasV2Response,
  AreaV2Item,
  Coefficient,
  PointProps,
  PointsResponse,
  Quadrant,
  Radius,
  Target,
  V6Result,
  V7Result,
} from '../api/types'
import {
  appliedSpeed,
  elderlyCoverage,
  formulaClass,
  needsDataCheck,
  requiredSeconds,
  tierOf,
  userElderlyRatio,
  V2_COEF,
} from './recommend'

// v2(결정 009) mock. 계약 C3(#73) 샘플이 나오기 전까지 기존 샘플(points·areas)에서 009 식으로 v2 값을 만든다.
// C3 샘플이 병합되면 이 파일 대신 contracts/samples 를 읽는다.

const r1 = (v: number) => Math.round(v * 10) / 10
const r3 = (v: number) => Math.round(v * 1000) / 1000

/** cw_id 로 정한 0~1 값 (mock 거리·이름을 매번 같게) */
function hash01(s: string): number {
  let h = 2166136261
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619)
  return ((h >>> 0) % 1000) / 1000
}

const MOCK_MARKETS = ['반송큰시장', '해운대시장', '구포시장', '부전시장']

/** 점 하나에 v2 값을 붙인다. elderlyP15·uplift 는 민감도 계산용 */
export function withV2(
  p: PointProps,
  residentRatio: number,
  target: Target,
  opt: { elderlyP15?: number; uplift?: number } = {},
): PointProps {
  if (p.status !== 'analyzed' || p.green_s === null || p.length_m === null) return p
  if (needsDataCheck(p.green_s, p.length_m)) {
    return {
      ...p,
      status: 'data_check',
      t_need_s: null,
      gap_s: null,
      is_candidate: false,
      check_reason: '기록값이 일반 기준식(1.0m/s)보다 짧아 기록 방식 확인 중',
    }
  }
  const tier = tierOf(p.flags)
  const user = userElderlyRatio(tier, residentRatio, opt.uplift)
  const v = appliedSpeed(tier, user, target, opt.elderlyP15)
  const t = requiredSeconds(p.green_s, p.length_m, v)
  const h = hash01(p.cw_id)
  const reason_parts = {
    protect_zone_m: tier === 1 ? Math.round(40 + h * 250) : null,
    market_name: tier === 2 ? MOCK_MARKETS[Math.floor(h * MOCK_MARKETS.length)] : null,
    market_m: tier === 2 ? Math.round(30 + h * 260) : null,
  }
  const reason =
    tier === 1
      ? `노인보호구역 ${reason_parts.protect_zone_m}m 안 → 0.7m/s 적용`
      : tier === 2
        ? `대형 시장(${reason_parts.market_name}) ${reason_parts.market_m}m 안 → 이용자 고령 비율 ${Math.round(user * 100)}% 가정, ${v.toFixed(2)}m/s`
        : `주변 주민 고령 비율 ${Math.round(user * 100)}% → ${v.toFixed(2)}m/s`
  return {
    ...p,
    formula_class: formulaClass(p.green_s, p.length_m),
    tier,
    resident_elderly_ratio: r3(residentRatio),
    user_elderly_ratio: r3(user),
    v_applied_mps: Math.round(v * 100) / 100,
    t_required_s: t,
    add_s: r1(t - p.green_s),
    coverage_now: elderlyCoverage(p.length_m, p.green_s, opt.elderlyP15),
    coverage_required: elderlyCoverage(p.length_m, t, opt.elderlyP15),
    reason,
    reason_parts,
    check_reason: null,
  }
}

export function mockPointsV2(
  points: PointsResponse,
  areas: AreasResponse,
  target: Target,
  radius: Radius,
  opt: { elderlyP15?: number; uplift?: number } = {},
): PointsResponse {
  const ratio = new Map(areas.items.map((a) => [a.adm_cd, a.ratio_65plus ?? 0.2]))
  // 반경이 좁으면 시장·보호구역 플래그가 일부 빠지는 것처럼 흉내 낸다(500m 는 300m 와 같게).
  const narrow = radius === 200
  const features = points.features.map((f) => {
    let p = f.properties
    if (narrow && p.flags && hash01(p.cw_id) < 0.35) p = { ...p, flags: { ...p.flags, protect_zone: false, market: false } }
    return { ...f, properties: withV2(p, ratio.get(p.adm_cd) ?? 0.2, target, opt) }
  })
  return { ...points, target, radius_m: radius, features }
}

const median = (xs: number[]) => {
  if (xs.length === 0) return 0
  const s = [...xs].sort((a, b) => a - b)
  const m = Math.floor(s.length / 2)
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2
}

export function mockAreasV2(areas: AreasResponse, points: PointsResponse, target: Target, radius: Radius): AreasV2Response {
  const minSample = areas.min_sample ?? 5
  const by = new Map<string, PointProps[]>()
  for (const { properties: p } of points.features) {
    if (p.status !== 'analyzed' || p.add_s == null) continue
    by.set(p.adm_cd, [...(by.get(p.adm_cd) ?? []), p])
  }
  const mean = (xs: number[]) => (xs.length ? xs.reduce((s, x) => s + x, 0) / xs.length : null)
  const base = areas.items.map((a) => {
    const ps = by.get(a.adm_cd) ?? []
    const m = mean(ps.map((p) => p.add_s!))
    const cn = mean(ps.map((p) => p.coverage_now!))
    const cr = mean(ps.map((p) => p.coverage_required!))
    return {
      adm_cd: a.adm_cd,
      adm_name: a.adm_name,
      sido: a.sido,
      sigungu: a.sigungu,
      n_analyzed: ps.length,
      mean_add_s: m === null ? null : r1(m),
      n_add2: ps.filter((p) => p.add_s! >= V2_COEF.addSecondsThreshold).length,
      coverage_now_mean: cn === null ? null : r3(cn),
      coverage_required_mean: cr === null ? null : r3(cr),
      ratio_65plus: a.ratio_65plus,
      low_sample: ps.length < minSample,
    }
  })
  const ok = base.filter((a) => !a.low_sample && a.mean_add_s !== null && a.ratio_65plus !== null)
  const thresholds = { mean_add_s_median: r1(median(ok.map((a) => a.mean_add_s!))), ratio_65plus_median: r3(median(ok.map((a) => a.ratio_65plus!))) }
  const items: AreaV2Item[] = base.map((a) => {
    let quadrant: Quadrant | null = null
    if (!a.low_sample && a.mean_add_s !== null && a.ratio_65plus !== null) {
      const x = a.mean_add_s > thresholds.mean_add_s_median ? 'high' : 'low'
      const y = a.ratio_65plus > thresholds.ratio_65plus_median ? 'high' : 'low'
      quadrant = `${x}_${y}` as Quadrant
    }
    return { ...a, quadrant }
  })
  return { _sample: true, target, radius_m: radius, min_sample: minSample, thresholds, items }
}

/** 결정 009 V6 표와 같은 값(mock) */
export const MOCK_V6: V6Result = {
  n_stations: 101,
  n_market_stations: 7,
  diff_pp: 10.95,
  p_value: 0.004,
  n_permutations: 5000,
  seed: 20261101,
  uplift: V2_COEF.marketUplift,
  uplift_range: V2_COEF.marketUpliftRange,
}

/** #82 완료 조건의 비율(28% / 14% / 4.7%)에 맞춘 mock */
export const MOCK_V7: V7Result = {
  groups: [
    { group: 'child_zone', radius_m: 150, n: 1200, n_formula_07: 336 },
    { group: 'senior_zone', radius_m: 300, n: 650, n_formula_07: 91 },
    { group: 'outside', radius_m: null, n: 9800, n_formula_07: 461 },
  ],
}

export const MOCK_COEFFICIENTS: Coefficient[] = [
  { key: 'entry_seconds', label: '보행진입시간', value: '7초', source: '서울시 교통정보 누리집, 경찰청 매뉴얼 인용', level: '공식' },
  { key: 'target_coverage', label: '목표 커버리지', value: '85% (민감도 90·95%)', source: '느린 쪽 15퍼센타일 설계 관례 (한음 외 2020, MUTCD 4E.06)', level: '공식 관례' },
  { key: 'speed_general', label: '일반인 보행속도', value: '평균 1.29, 15퍼센타일 1.01m/s', source: '한음 외(2020) 실측', level: '학술(초록)' },
  { key: 'speed_elderly', label: '고령자 보행속도', value: '평균 1.13, 15퍼센타일 0.85m/s (민감도 0.76)', source: '한음 외(2020), 여수 2016', level: '학술(초록)' },
  { key: 'distribution', label: '분포 모양', value: '정규분포 (표준편차 약 0.27)', source: '계산을 위한 가정', level: '가정' },
  { key: 'tier1_speed', label: '1단계 속도', value: '0.7m/s', source: '경찰청 업무편람(2022) 교통약자 기준 개정', level: '학술·언론' },
  { key: 'radius', label: '반경', value: '300m', source: '보호구역 지정 범위(시설 주 출입문 300m)', level: '공식' },
  { key: 'big_market', label: '대형 시장 기준', value: '점포 200개 이상', source: 'V6 에서 효과가 보인 선, 100·150·300 민감도', level: '데이터 + 팀 판단' },
  { key: 'market_uplift', label: '2단계 시장 보정', value: '+0.137 (범위 0.063~0.157)', source: 'V6 지하철 무임 비율 (대형 시장 근처 역 7곳, 수안·부전 영향 큼)', level: '데이터' },
]

/** 민감도(#80): 고령자 속도 0.76, 시장 보정 범위 양 끝에서 2초 이상 추가 수가 어떻게 바뀌는지 */
export function mockSensitivity(points: PointsResponse, areas: AreasResponse): { label: string; value: string }[] {
  const n = (opt: { elderlyP15?: number; uplift?: number }) =>
    mockPointsV2(points, areas, 0.85, 300, opt).features.filter((f) => (f.properties.add_s ?? 0) >= V2_COEF.addSecondsThreshold).length
  const base = n({})
  const [lo, hi] = V2_COEF.marketUpliftRange
  return [
    { label: '기본 (목표 85%, 반경 300m)', value: `2초 이상 추가 ${base}곳` },
    { label: `고령자 15퍼센타일 속도 ${V2_COEF.elderlyP15Sensitivity}m/s`, value: `${n({ elderlyP15: V2_COEF.elderlyP15Sensitivity })}곳` },
    { label: `시장 보정 ${lo}`, value: `${n({ uplift: lo })}곳` },
    { label: `시장 보정 ${hi}`, value: `${n({ uplift: hi })}곳` },
  ]
}
