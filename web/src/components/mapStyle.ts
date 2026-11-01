// 짧음 비율(0~1) → 단일 색 계열 명도(색맹 대응). 지도와 범례가 같이 쓴다.
export const RATIO_STEPS: [number, string][] = [
  [0, '#fdeee3'],
  [0.1, '#f9cfb0'],
  [0.2, '#f3a36b'],
  [0.3, '#e57a35'],
  [0.4, '#b84f12'],
]
export const LOW_SAMPLE_COLOR = '#c9ccd1'
export const HATCH_LINE_COLOR = '#8b9099'
export const NO_VALUE_COLOR = '#eceef0'

/**
 * 횡단보도 점: 짧은 초(gap_s) 발산형 색(피드백 1번). 기준식보다 여유 = 파랑, 0 = 흰색, 짧음 = 빨강.
 * 빨강·초록 대신 파랑·빨강을 써서 적록색약에서도 구분된다.
 */
export const GAP_STOPS: [number, string][] = [
  [-10, '#2166ac'],
  [-4, '#92c5de'],
  [0, '#f7f7f7'],
  [4, '#f4a582'],
  [10, '#b2182b'],
]
/** 범례 눈금: 이 초를 넘으면 가장 진한 색 */
export const GAP_RANGE_S = 10
export const POINT_STROKE = '#4b5563'
/** 점검 우선순위 후보는 테두리를 굵고 진하게 */
export const CANDIDATE_STROKE = '#111827'
/** 분석 제외(녹색신호시간 없음 등): 속 빈 점 */
export const EXCLUDED_STROKE = '#6b7280'
/** 내가 실측·녹색시간을 입력한 점 */
export const MY_INPUT_STROKE = '#7c3aed'
export const CLUSTER_STROKE = '#ffffff'
