import type { AreaItem, Quadrant } from '../api/types'

// 사분면 계산. 가중합 점수는 만들지 않는다(PRD 3장). 두 축을 따로 경계선과 비교할 뿐이다.

export interface Thresholds {
  /** 짧음 비율 경계(가로축) */
  x: number
  /** 65세 이상 비율 경계(세로축) */
  y: number
}

export interface PlotPoint {
  adm_cd: string
  adm_name: string
  sigungu: string
  x: number
  y: number
  low_sample: boolean
  quadrant: Quadrant
}

/** 경계선과 같은 값은 high 로 본다(API 의 quadrant 계산과 같은 규칙). */
export function classify(x: number, y: number, t: Thresholds): Quadrant {
  return `${x >= t.x ? 'high' : 'low'}_${y >= t.y ? 'high' : 'low'}` as Quadrant
}

/**
 * 축 최댓값. 0.1 단위로 올리고 최소 floor 를 보장해 속도를 바꿔도 축이 크게 흔들리지 않게 한다.
 * 비율이므로 1 을 넘지 않는다.
 */
export function niceMax(values: number[], floor = 0.5): number {
  const m = values.reduce((a, b) => Math.max(a, b), 0)
  const up = Math.ceil(Math.round(m * 1000) / 100) / 10
  return Math.min(1, Math.max(floor, up))
}

export interface BuildResult {
  points: PlotPoint[]
  /** 짧음 비율이나 65세 이상 비율이 없어 찍지 못한 읍면동 수 */
  excluded: number
}

export function buildPoints(items: AreaItem[], t: Thresholds): BuildResult {
  const points: PlotPoint[] = []
  let excluded = 0
  for (const it of items) {
    if (it.short_ratio === null || it.ratio_65plus === null) {
      excluded++
      continue
    }
    points.push({
      adm_cd: it.adm_cd,
      adm_name: it.adm_name,
      sigungu: it.sigungu,
      x: it.short_ratio,
      y: it.ratio_65plus,
      low_sample: it.low_sample,
      quadrant: classify(it.short_ratio, it.ratio_65plus, t),
    })
  }
  return { points, excluded }
}

/** 점검 우선순위 후보 지역 수: 오른쪽 위 칸이면서 표본 부족이 아닌 곳 */
export function countPriority(points: PlotPoint[]): number {
  return points.filter((p) => !p.low_sample && p.quadrant === 'high_high').length
}

/** 눈금: 0부터 max 까지. 범위가 넓으면 0.2 간격 */
export function ticks(max: number): number[] {
  const step = max > 0.6 ? 0.2 : 0.1
  const out: number[] = []
  for (let v = 0; v <= max + 1e-9; v += step) out.push(Math.round(v * 100) / 100)
  return out
}
