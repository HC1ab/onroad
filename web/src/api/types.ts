// contracts/*.schema.json 과 같은 형태. 스키마가 바뀌면 여기도 함께 바꾼다.

export type Speed = 0.7 | 0.8 | 1.0
export const SPEEDS: readonly Speed[] = [0.7, 0.8, 1.0]

/** 목적지 노출 반경(m). 기본 300(결정 기록 005), 민감도 200·500 */
export type Radius = 200 | 300 | 500
export const RADII: readonly Radius[] = [200, 300, 500]

export type Quadrant = 'high_high' | 'high_low' | 'low_high' | 'low_low'

export interface AreaItem {
  adm_cd: string
  adm_name: string
  sido: string
  sigungu: string
  n_analyzed: number
  n_short: number
  short_ratio: number | null
  mean_gap_s: number | null
  ratio_65plus: number | null
  quadrant: Quadrant | null
  n_candidate: number
  low_sample: boolean
  /** v2(3단계 기준) 화면일 때만: AreaV2Item 의 값 */
  mean_add_s?: number | null
  n_add2?: number
  coverage_now_mean?: number | null
  coverage_required_mean?: number | null
}

export interface AreasResponse {
  _sample?: boolean
  speed: Speed
  radius_m?: Radius
  /** 표본 하한(config.yaml min_sample). 예전 응답에는 없다 */
  min_sample?: number
  /** v2 화면이면 mean_add_s_median 도 있다(short_ratio_median 은 0) */
  thresholds: { short_ratio_median: number; ratio_65plus_median: number; mean_add_s_median?: number }
  items: AreaItem[]
  /** v2 화면이면 목표 커버리지 */
  target?: Target
}

export interface ExposureFlags {
  senior_center: boolean
  market: boolean
  protect_zone: boolean
  crash_zone_past: boolean
  hospital?: boolean | null
}

export interface CrosswalkItem {
  cw_id: string
  lat: number
  lon: number
  length_m: number
  green_s: number
  t_need_s: number
  gap_s: number
  flags: ExposureFlags
  exposure_cnt: number
  is_candidate: boolean
}

export interface AreaCrosswalksResponse {
  _sample?: boolean
  adm_cd: string
  speed: Speed
  radius_m?: Radius
  items: CrosswalkItem[]
}

export interface CandidatesResponse extends GeoJSON.FeatureCollection<
  GeoJSON.Point,
  { cw_id: string; adm_cd: string; gap_s: number; exposure_cnt: number }
> {
  _sample?: boolean
  speed?: Speed
  radius_m?: Radius
}

export interface MetaResponse extends MetaV2Ext {
  _sample?: boolean
  ref_month: string
  built_at: string
  coverage_ratio: number
  green_def_status: 'unconfirmed' | 'includes_flash' | 'excludes_flash'
  sources: { name: string; url: string; license?: string; modified?: string }[]
  limits_text: string
}

export interface V1Result {
  n: number
  mean_diff_s: number
  flash_included_n: number
  points: {
    cw_id: string
    length_m: number
    recorded_green_s: number
    measured_green_s: number
    measured_flash_s: number
    diff_s: number
  }[]
}

export interface V2Result {
  top_n: number
  pairs: { a: Speed; b: Speed; spearman: number; top_n_overlap: number }[]
}

export interface V3Result {
  speed: Speed
  recent_years: number[]
  overlap_ratio: number
  ratio_vs_random: number
  p_value: number
  n_permutations: number
  random_distribution: number[]
}

export type FacilityKind = 'senior_center' | 'market' | 'protect_zone'

export interface V4Result {
  speed: Speed
  spearman: number
  by_group: { group: string; spearman: number; n: number }[]
  inside_outside: { facility: FacilityKind; inside_short_ratio: number; outside_short_ratio: number }[]
}

export interface V5Result {
  coefficients: { term: string; estimate: number; ci_low: number; ci_high: number }[]
}

/** 검증 결과(F8). 아직 계산하지 않은 항목은 null */
export interface ValidationResponse extends ValidationV2Ext {
  _sample?: boolean
  v1: V1Result | null
  v2: V2Result | null
  v3: V3Result | null
  v4: V4Result | null
  v5: V5Result | null
}

export type BoundaryProps = { adm_cd: string; adm_name: string; sido: string; sigungu: string }
export type BoundariesResponse = GeoJSON.FeatureCollection<GeoJSON.Polygon | GeoJSON.MultiPolygon, BoundaryProps>

/** 분석 제외 사유 (F1 제외 사유 표와 같은 기준) */
export type ExcludeReason = 'green_missing' | 'length_missing' | 'green_out_of_range' | 'length_out_of_range'

/** 전체 횡단보도 점 하나의 속성 (points.schema.json). excluded·data_check 는 시간 값이 null. v2 필드(C3)는 선택 */
export interface PointProps extends PointV2 {
  cw_id: string
  adm_cd: string
  status: 'analyzed' | 'excluded' | 'data_check'
  length_m: number | null
  green_s: number | null
  t_need_s: number | null
  gap_s: number | null
  flags: ExposureFlags | null
  exposure_cnt: number
  is_candidate: boolean
  exclude_reason: ExcludeReason | null
}

export interface PointsResponse extends GeoJSON.FeatureCollection<GeoJSON.Point, PointProps> {
  _sample?: boolean
  speed?: Speed
  /** v2 응답이면 목표 커버리지 */
  target?: Target
  radius_m?: Radius
}

// ---- v2: 3단계 기준 (결정 009, 계약 C3 #73). C3 샘플이 나오기 전까지 웹 mock 으로 개발 ----

/** 목표 커버리지. 기본 0.85, 민감도 0.90·0.95 */
export type Target = 0.85 | 0.9 | 0.95
export const TARGETS: readonly Target[] = [0.85, 0.9, 0.95]

/** 1 노인보호구역 · 2 대형 전통시장 · 3 그 외(주민 고령 비율) */
export type Tier = 1 | 2 | 3

/** 기록값이 어느 기준식(속도)과 같은지. 허용오차 config formula_tolerance_s */
export type FormulaClass = '1.0' | '0.8' | '0.7' | 'other'

export interface ReasonParts {
  protect_zone_m: number | null
  market_name: string | null
  market_m: number | null
}

/** points 의 v2 필드. status=analyzed 일 때만 값이 있고 나머지는 null */
export interface PointV2 {
  formula_class?: FormulaClass | null
  tier?: Tier | null
  resident_elderly_ratio?: number | null
  user_elderly_ratio?: number | null
  v_applied_mps?: number | null
  /** = max(green_s, 7 + L/v) */
  t_required_s?: number | null
  /** = t_required_s − green_s (≥ 0) */
  add_s?: number | null
  /** 고령 보행자 기준 커버리지(정답 확률 아님) */
  coverage_now?: number | null
  coverage_required?: number | null
  reason?: string | null
  reason_parts?: ReasonParts | null
  /** status=data_check 일 때 사유 */
  check_reason?: string | null
}

export interface AreaV2Item {
  adm_cd: string
  adm_name: string
  sido: string
  sigungu: string
  n_analyzed: number
  mean_add_s: number | null
  /** 2초 이상 추가되는 횡단보도 수 (config add_seconds_threshold) */
  n_add2: number
  coverage_now_mean: number | null
  coverage_required_mean: number | null
  ratio_65plus: number | null
  quadrant: Quadrant | null
  low_sample: boolean
}

export interface AreasV2Response {
  _sample?: boolean
  target: Target
  radius_m?: Radius
  min_sample?: number
  thresholds: { mean_add_s_median: number; ratio_65plus_median: number }
  items: AreaV2Item[]
}

/** V6 지하철 무임 비율: 대형 시장 근처 역의 잔차 차이와 순열 검정 */
export interface V6Result {
  n_stations: number
  n_market_stations: number
  diff_pp: number
  p_value: number
  n_permutations: number
  seed: number
  uplift: number
  uplift_range: [number, number]
}

/** V7 0.7식 적용률: 구역별 대상 수와 기록값이 0.7 기준식과 같은 수 */
export interface V7Result {
  groups: { group: 'child_zone' | 'senior_zone' | 'outside'; radius_m: number | null; n: number; n_formula_07: number }[]
}

export interface ValidationV2Ext {
  v6?: V6Result | null
  v7?: V7Result | null
}

export interface Coefficient {
  key: string
  label: string
  value: string
  source: string
  level: string
}

export interface MetaV2Ext {
  coefficients?: Coefficient[]
  /** 고령자 속도 민감도(0.76)로 다시 계산했을 때 2초 이상 추가 수 등 요약 */
  sensitivity?: { label: string; value: string }[]
}
