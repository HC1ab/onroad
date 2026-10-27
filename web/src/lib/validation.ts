// 검증 화면 계산(그림용). 값 자체는 파이프라인이 계산해 오고, 여기서는 보여주기 위한 가공만 한다.

export interface Bin {
  x0: number
  x1: number
  count: number
}

/**
 * 값들을 같은 폭 구간으로 나눈다(V3 무작위 분포 히스토그램).
 * include 를 주면 그 값이 범위 안에 들어오도록 범위를 넓힌다(관측값 선이 그림 밖으로 나가지 않게).
 */
export function histogram(values: number[], bins = 12, include?: number): Bin[] {
  const all = include === undefined ? values : [...values, include]
  if (all.length === 0) return []
  let lo = Math.min(...all)
  let hi = Math.max(...all)
  if (lo === hi) {
    lo -= 0.01
    hi += 0.01
  }
  const w = (hi - lo) / bins
  const out: Bin[] = Array.from({ length: bins }, (_, i) => ({ x0: lo + i * w, x1: lo + (i + 1) * w, count: 0 }))
  for (const v of values) {
    const i = Math.min(bins - 1, Math.floor((v - lo) / w))
    out[i].count++
  }
  return out
}

export function mean(values: number[]): number | null {
  return values.length ? values.reduce((a, b) => a + b, 0) / values.length : null
}

/** 상관계수 표시 "0.91" / "−0.12" */
export const rho = (v: number): string => `${v < 0 ? '−' : ''}${Math.abs(v).toFixed(2)}`

/** p값 표시: 0.001 미만은 "< 0.001" */
export const pValue = (v: number): string => (v < 0.001 ? '< 0.001' : v.toFixed(3).replace(/0+$/, '').replace(/\.$/, ''))
