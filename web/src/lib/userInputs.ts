import type { V1Result } from '../api/types'

/**
 * 사용자 입력(피드백 13~15번): 녹색신호시간 직접 입력과 현장 실측.
 * 그 브라우저에만 저장하고(서버로 보내지 않음) CSV로 내보낸다. 화면에서는 "내 입력(검토 전)"으로 공식 결과와 나눈다.
 */

/** 녹색신호시간이 없는 횡단보도에 사용자가 넣은 값 */
export interface GreenInput {
  cw_id: string
  adm_cd: string
  length_m: number | null
  green_s: number
  saved_at: string
}

/** 현장 실측 한 번 */
export interface Measurement {
  id: string
  cw_id: string
  adm_cd: string
  lon: number
  lat: number
  length_m: number | null
  /** 공공데이터에 기록된 녹색신호시간. 없으면 null (그러면 V1 차이 계산에서 빠진다) */
  recorded_green_s: number | null
  measured_green_s: number
  measured_flash_s: number
  measured_at: string
  saved_at: string
}

export interface UserInputs {
  greens: Record<string, GreenInput>
  measurements: Measurement[]
}

export const EMPTY_INPUTS: UserInputs = { greens: {}, measurements: [] }

// 입력 범위. 녹색신호시간 정제 상한은 config.yaml(outlier.max_green_s)과 같게 둔다.
export const INPUT_LIMITS = { greenMax: 200, flashMax: 60 }

/** 입력값 검사. 문제가 없으면 null, 있으면 화면에 보여줄 문구 */
export function checkSeconds(value: number, max: number, label: string, allowZero = false): string | null {
  if (!Number.isFinite(value)) return `${label}을(를) 숫자로 입력하세요.`
  if (allowZero ? value < 0 : value <= 0) return `${label}은(는) ${allowZero ? '0 이상' : '0보다 큰 값'}이어야 합니다.`
  if (value > max) return `${label}은(는) ${max}초 이하여야 합니다.`
  return null
}

const r1 = (v: number) => Math.round(v * 10) / 10

/** 한 횡단보도를 여러 번 재면 평균을 쓴다. */
export function averageByCrosswalk(ms: Measurement[]) {
  const by = new Map<string, Measurement[]>()
  for (const m of ms) by.set(m.cw_id, [...(by.get(m.cw_id) ?? []), m])
  return [...by.values()].map((list) => {
    const avg = (k: 'measured_green_s' | 'measured_flash_s') => r1(list.reduce((s, m) => s + m[k], 0) / list.length)
    return { ...list[list.length - 1], measured_green_s: avg('measured_green_s'), measured_flash_s: avg('measured_flash_s'), count: list.length }
  })
}

/**
 * 내 실측으로 V1 결과를 계산한다(공식 V1과 같은 형태).
 * 차이 = 기록 − 실측 점등. 기록값이 "점등 + 점멸"에 더 가까우면 점멸 포함으로 본다.
 * 기록값이 없는 횡단보도는 차이를 낼 수 없어 뺀다.
 */
export function myV1(ms: Measurement[]): { v1: V1Result | null; skipped: number } {
  const avg = averageByCrosswalk(ms)
  const usable = avg.filter((m) => m.recorded_green_s !== null)
  if (usable.length === 0) return { v1: null, skipped: avg.length }
  const points = usable.map((m) => ({
    cw_id: m.cw_id,
    length_m: m.length_m ?? 0,
    recorded_green_s: m.recorded_green_s as number,
    measured_green_s: m.measured_green_s,
    measured_flash_s: m.measured_flash_s,
    diff_s: r1((m.recorded_green_s as number) - m.measured_green_s),
  }))
  const flash_included_n = points.filter(
    (p) => Math.abs(p.recorded_green_s - (p.measured_green_s + p.measured_flash_s)) < Math.abs(p.recorded_green_s - p.measured_green_s),
  ).length
  return {
    v1: { n: points.length, mean_diff_s: r1(points.reduce((s, p) => s + p.diff_s, 0) / points.length), flash_included_n, points },
    skipped: avg.length - usable.length,
  }
}

const csvCell = (v: unknown) => {
  if (v === null || v === undefined) return ''
  const s = String(v)
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}

function csv(columns: string[], rows: Record<string, unknown>[]) {
  return '﻿' + [columns.join(','), ...rows.map((r) => columns.map((c) => csvCell(r[c])).join(','))].join('\r\n') + '\r\n'
}

export const MEASUREMENT_COLUMNS = ['cw_id', 'adm_cd', 'lon', 'lat', 'length_m', 'recorded_green_s', 'measured_green_s', 'measured_flash_s', 'measured_at', 'saved_at'] as const
export const GREEN_COLUMNS = ['cw_id', 'adm_cd', 'length_m', 'green_s', 'saved_at'] as const

/** 팀 검토용 CSV (UTF-8 BOM). 현장 실측은 validation/ 담당에게 넘긴다. */
export function measurementsCsv(ms: Measurement[]) {
  return csv([...MEASUREMENT_COLUMNS], ms as unknown as Record<string, unknown>[])
}
export function greensCsv(g: Record<string, GreenInput>) {
  return csv([...GREEN_COLUMNS], Object.values(g) as unknown as Record<string, unknown>[])
}

const KEY = 'onroad.userInputs.v1'

export function loadInputs(storage: Pick<Storage, 'getItem'> | null): UserInputs {
  try {
    const raw = storage?.getItem(KEY)
    if (!raw) return EMPTY_INPUTS
    const v = JSON.parse(raw) as Partial<UserInputs>
    return { greens: v.greens ?? {}, measurements: Array.isArray(v.measurements) ? v.measurements : [] }
  } catch {
    return EMPTY_INPUTS
  }
}

export function saveInputs(storage: Pick<Storage, 'setItem'> | null, v: UserInputs) {
  try {
    storage?.setItem(KEY, JSON.stringify(v))
  } catch {
    // 저장소를 쓸 수 없으면(사생활 보호 모드 등) 이번 화면에서만 유지한다.
  }
}
