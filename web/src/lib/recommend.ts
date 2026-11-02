import type { ExposureFlags, Target, Tier } from '../api/types'

// 결정 009 의 3단계 기준 계산. 실제 값은 파이프라인이 config.yaml 로 계산해 보낸다.
// 여기 함수는 mock 데이터 생성과 화면 설명(민감도 등)에만 쓴다.

/** config.yaml v2 키와 같은 값 (mock 전용 사본) */
export const V2_COEF = {
  entryS: 7,
  speedBounds: [0.7, 1.0] as [number, number],
  formulaToleranceS: 0.5,
  general: { mean: 1.29, p15: 1.01 },
  elderly: { mean: 1.13, p15: 0.85 },
  elderlyP15Sensitivity: 0.76,
  tier1Speed: 0.7,
  marketUplift: 0.137,
  marketUpliftRange: [0.063, 0.157] as [number, number],
  addSecondsThreshold: 2,
}

/** 15퍼센타일의 표준정규 z */
const Z15 = 1.0364

const sd = (d: { mean: number; p15: number }) => (d.mean - d.p15) / Z15

/** 표준정규 누적분포 (Abramowitz–Stegun 7.1.26) */
export function normCdf(x: number): number {
  const t = 1 / (1 + 0.3275911 * Math.abs(x) / Math.SQRT2)
  const y = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-(x * x) / 2)
  return x >= 0 ? (1 + y) / 2 : (1 - y) / 2
}

export function tierOf(flags: ExposureFlags | null): Tier {
  if (flags?.protect_zone) return 1
  if (flags?.market) return 2
  return 3
}

/** 단계별 이용자 고령 비율 p. 1단계는 고령자 기준(1) */
export function userElderlyRatio(tier: Tier, resident: number, uplift = V2_COEF.marketUplift): number {
  if (tier === 1) return 1
  if (tier === 2) return Math.min(1, resident + uplift)
  return resident
}

/** 일반·고령 분포를 p 로 섞었을 때 느린 쪽 (1 − target) 이 걸리는 속도 */
export function mixtureSpeed(p: number, target: Target, elderlyP15 = V2_COEF.elderly.p15): number {
  const g = V2_COEF.general
  const e = { mean: V2_COEF.elderly.mean, sd: (V2_COEF.elderly.mean - elderlyP15) / Z15 }
  const cdf = (v: number) => (1 - p) * normCdf((v - g.mean) / sd(g)) + p * normCdf((v - e.mean) / e.sd)
  const want = 1 - target
  let lo = 0
  let hi = 3
  for (let i = 0; i < 60; i++) {
    const mid = (lo + hi) / 2
    if (cdf(mid) < want) lo = mid
    else hi = mid
  }
  return (lo + hi) / 2
}

export function appliedSpeed(tier: Tier, p: number, target: Target, elderlyP15?: number): number {
  if (tier === 1) return V2_COEF.tier1Speed
  const [min, max] = V2_COEF.speedBounds
  return Math.min(max, Math.max(min, mixtureSpeed(p, target, elderlyP15)))
}

const r1 = (v: number) => Math.round(v * 10) / 10
const r3 = (v: number) => Math.round(v * 1000) / 1000

/** 필요 시간 = max(기록값, 7 + L/v). 기록값보다 줄이지 않는다 */
export function requiredSeconds(green_s: number, length_m: number, v: number): number {
  return r1(Math.max(green_s, V2_COEF.entryS + length_m / v))
}

/** 고령 보행자 중 t 초 안에 L m 를 건너는 비율 (진입 시간 제외). 정답 확률이 아니다 */
export function elderlyCoverage(length_m: number, t: number, elderlyP15 = V2_COEF.elderly.p15): number {
  const walk = t - V2_COEF.entryS
  if (walk <= 0) return 0
  const need = length_m / walk
  const s = (V2_COEF.elderly.mean - elderlyP15) / Z15
  return r3(1 - normCdf((need - V2_COEF.elderly.mean) / s))
}

/** 기록값이 1.0·0.8·0.7 기준식 중 어느 것과 같은지 (허용오차 안) */
export function formulaClass(green_s: number, length_m: number): '1.0' | '0.8' | '0.7' | 'other' {
  for (const v of ['1.0', '0.8', '0.7'] as const) {
    if (Math.abs(green_s - (V2_COEF.entryS + length_m / Number(v))) <= V2_COEF.formulaToleranceS) return v
  }
  return 'other'
}

/** 일반 기준식(1.0m/s)보다 허용오차 넘게 짧으면 기록 방식 확인 대상 */
export function needsDataCheck(green_s: number, length_m: number): boolean {
  return green_s < V2_COEF.entryS + length_m / V2_COEF.speedBounds[1] - V2_COEF.formulaToleranceS
}

export const TIER_LABEL: Record<Tier, string> = {
  1: '1단계 노인보호구역',
  2: '2단계 대형 전통시장',
  3: '3단계 주민 고령 비율',
}

export const fmtPct = (v: number | null | undefined) => (v === null || v === undefined ? '—' : `${Math.round(v * 100)}%`)
