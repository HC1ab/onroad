// 화면 숫자 표시를 한곳에 모은다.

/** 0~1 비율 → "12.3%". 값이 없으면 "—" */
export const pct1 = (v: number | null | undefined): string => (typeof v === 'number' ? `${(v * 100).toFixed(1)}%` : '—')

/** 0~1 비율 → "12%" (축 눈금처럼 짧게) */
export const pct0 = (v: number): string => `${Math.round(v * 100)}%`

/** 초 → "3.2초". 값이 없으면 "—" */
export const sec1 = (v: number | null | undefined): string => (typeof v === 'number' ? `${v.toFixed(1)}초` : '—')

/** 짧은 초(gap) → "+3.2초" / "−1.0초". 양수가 기준식보다 짧은 쪽 */
export const gap1 = (v: number): string => `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v).toFixed(1)}초`

/** 미터 → "24m" */
export const meter = (v: number): string => `${Math.round(v)}m`
