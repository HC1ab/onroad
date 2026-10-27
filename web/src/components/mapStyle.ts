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

// 후보 횡단보도 점: 채색과 겹쳐도 보이도록 짙은 갈색 + 흰 테두리
export const CANDIDATE_COLOR = '#5b1f05'
export const CANDIDATE_STROKE = '#ffffff'
