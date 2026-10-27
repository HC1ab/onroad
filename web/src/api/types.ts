// contracts/*.schema.json 과 같은 형태. 스키마가 바뀌면 여기도 함께 바꾼다.

export type Speed = 0.7 | 0.8 | 1.0
export const SPEEDS: readonly Speed[] = [0.7, 0.8, 1.0]

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
}

export interface AreasResponse {
  _sample?: boolean
  speed: Speed
  thresholds: { short_ratio_median: number; ratio_65plus_median: number }
  items: AreaItem[]
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
  items: CrosswalkItem[]
}

export interface CandidatesResponse extends GeoJSON.FeatureCollection<
  GeoJSON.Point,
  { cw_id: string; adm_cd: string; gap_s: number; exposure_cnt: number }
> {
  _sample?: boolean
  speed?: Speed
  radius_m?: 200 | 300 | 500
}

export interface MetaResponse {
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
export interface ValidationResponse {
  _sample?: boolean
  v1: V1Result | null
  v2: V2Result | null
  v3: V3Result | null
  v4: V4Result | null
  v5: V5Result | null
}

export type BoundaryProps = { adm_cd: string; adm_name: string; sido: string; sigungu: string }
export type BoundariesResponse = GeoJSON.FeatureCollection<GeoJSON.Polygon | GeoJSON.MultiPolygon, BoundaryProps>
