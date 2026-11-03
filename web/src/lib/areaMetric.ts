import type { AreaItem, AreasResponse, AreasV2Response } from '../api/types'
import { ADD_STEPS, RATIO_STEPS } from '../components/mapStyle'
import { pct0, pct1, sec1 } from './format'

// 읍면동 채색·사분면 가로축에 쓰는 지표. 기록값 화면은 짧음 비율, 3단계 기준 화면은 평균 추가 초(결정 009).

export interface AreaMetric {
  key: 'short_ratio' | 'mean_add_s'
  value: (a: AreaItem) => number | null
  median: (t: AreasResponse['thresholds']) => number
  /** 지도 색 단계 [하한, 색] */
  steps: [number, string][]
  fmt: (v: number | null) => string
  tick: (v: number) => string
  niceMax: (values: number[]) => number
  ticks: (max: number) => number[]
  legendTitle: string
  scale: [string, string]
  /** 5분위로 다시 정한 경우 범례 구간 경계 글자(최솟값 … 최댓값). 없으면 scale 양 끝만 쓴다 */
  legendStops?: string[]
  axisLabel: string
  short: string
  tooltip: (a: { value: number | null; n_add2?: number }) => string
}

const ratioTicks = (max: number) => {
  const step = max > 0.6 ? 0.2 : 0.1
  const out: number[] = []
  for (let v = 0; v <= max + 1e-9; v += step) out.push(Math.round(v * 100) / 100)
  return out
}

export const RATIO_METRIC: AreaMetric = {
  key: 'short_ratio',
  value: (a) => a.short_ratio,
  median: (t) => t.short_ratio_median,
  steps: RATIO_STEPS,
  fmt: pct1,
  tick: pct0,
  niceMax: (values) => {
    const m = values.reduce((a, b) => Math.max(a, b), 0)
    return Math.min(1, Math.max(0.5, Math.ceil(Math.round(m * 1000) / 100) / 10))
  },
  ticks: ratioTicks,
  legendTitle: '기준식보다 짧은 횡단보도 비율',
  scale: ['0%', '40% 이상'],
  axisLabel: '기준식보다 짧은 비율 →',
  short: '짧음',
  tooltip: ({ value }) => `기준식보다 짧음 ${value === null ? '—' : pct0(value)}`,
}

export const ADD_METRIC: AreaMetric = {
  key: 'mean_add_s',
  value: (a) => a.mean_add_s ?? null,
  median: (t) => t.mean_add_s_median ?? 0,
  steps: ADD_STEPS,
  fmt: sec1,
  tick: (v) => `${v}초`,
  niceMax: (values) => Math.max(4, Math.ceil(values.reduce((a, b) => Math.max(a, b), 0))),
  ticks: (max) => {
    const step = max > 8 ? 2 : 1
    const out: number[] = []
    for (let v = 0; v <= max + 1e-9; v += step) out.push(v)
    return out
  },
  legendTitle: '기준 적용 시 평균 추가 초',
  scale: ['0초', '6초 이상'],
  axisLabel: '기준 적용 시 평균 추가 초 →',
  short: '평균 추가',
  tooltip: ({ value, n_add2 }) => `기준 적용 시 평균 +${sec1(value)}${n_add2 !== undefined ? ` · 2초 이상 추가 ${n_add2}곳` : ''}`,
}

/**
 * 지도 색 구간을 지금 화면 값의 5분위로 다시 정한다(#124). 고정 구간은 실데이터에서 값이 한쪽에 몰려
 * 거의 한 색으로 보였다. 표본 부족·값 없음은 빼고 계산한다.
 * 같은 값이 몰려 경계가 겹치면(예: 대부분 0%) 그 값 위쪽을 다시 나누고, 그래도 모자라면 구간 수를 줄인다.
 * 색은 양 끝을 살려 고르게 고른다. 값이 2개 미만이면 고정 구간을 그대로 쓴다.
 */
export function withQuantileSteps(metric: AreaMetric, items: AreaItem[]): AreaMetric {
  const values = items
    .filter((a) => !a.low_sample)
    .map(metric.value)
    .filter((v): v is number => typeof v === 'number')
    .sort((a, b) => a - b)
  if (values.length < 2) return metric
  const colors = metric.steps.map(([, c]) => c)
  const n = colors.length
  // breaks[i] = i번째 구간의 하한. 남은 값(마지막 하한 이상)을 남은 구간 수로 나눠 다음 하한을 고른다.
  const breaks = [values[0]]
  while (breaks.length < n) {
    const last = breaks[breaks.length - 1]
    const rest = values.filter((v) => v >= last)
    const above = rest.find((v) => v > last)
    if (above === undefined) break
    const next = rest[Math.round(rest.length / (n - breaks.length + 1))]
    breaks.push(next > last ? next : above)
  }
  const k = breaks.length
  const pick = (i: number) => colors[k === 1 ? 0 : Math.round((i * (n - 1)) / (k - 1))]
  const max = values[values.length - 1]
  return {
    ...metric,
    steps: breaks.map((b, i) => [b, pick(i)]),
    scale: [metric.fmt(values[0]), metric.fmt(max)],
    // 마지막 구간이 한 값(예: 100%)뿐이면 끝 글자를 겹쳐 쓰지 않는다
    legendStops: [...breaks.map((v) => metric.fmt(v)), max > breaks[breaks.length - 1] ? metric.fmt(max) : ''],
  }
}

/**
 * v2 읍면동 응답을 화면 공통 형태(AreasResponse)로 바꾼다. 지표는 ADD_METRIC 으로 읽는다.
 * v1 전용 값(짧음 비율·후보 수)은 없으므로 null·0 으로 둔다.
 */
export function v2AsAreas(v2: AreasV2Response): AreasResponse {
  return {
    _sample: v2._sample,
    speed: 0.8,
    radius_m: v2.radius_m,
    min_sample: v2.min_sample,
    target: v2.target,
    thresholds: { short_ratio_median: 0, ratio_65plus_median: v2.thresholds.ratio_65plus_median, mean_add_s_median: v2.thresholds.mean_add_s_median },
    items: v2.items.map((a) => ({
      ...a,
      n_short: a.n_add2,
      short_ratio: null,
      mean_gap_s: null,
      n_candidate: a.n_add2,
    })),
  }
}
