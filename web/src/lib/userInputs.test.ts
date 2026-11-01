import { describe, expect, it } from 'vitest'
import { checkSeconds, loadInputs, measurementsCsv, myV1, saveInputs, type Measurement } from './userInputs'

const m = (cw_id: string, recorded: number | null, green: number, flash = 0): Measurement => ({
  id: `${cw_id}-${green}`, cw_id, adm_cd: '21090730', lon: 129.1, lat: 35.1, length_m: 20,
  recorded_green_s: recorded, measured_green_s: green, measured_flash_s: flash,
  measured_at: '2026-11-01T10:00', saved_at: '2026-11-01T10:01:00Z',
})

describe('내 실측 → V1 (피드백 14·15번)', () => {
  it('차이 = 기록 − 실측, 같은 곳을 여러 번 재면 평균', () => {
    const { v1 } = myV1([m('A', 30, 26), m('A', 30, 28), m('B', 20, 21)])
    expect(v1?.n).toBe(2)
    const a = v1!.points.find((p) => p.cw_id === 'A')!
    expect(a.measured_green_s).toBe(27)
    expect(a.diff_s).toBe(3)
    expect(v1!.mean_diff_s).toBe(1) // (3 + -1) / 2
  })

  it('기록값이 점등 + 점멸에 더 가까우면 점멸 포함으로 센다', () => {
    const { v1 } = myV1([m('A', 30, 25, 5), m('B', 30, 30, 5)])
    expect(v1?.flash_included_n).toBe(1)
  })

  it('기록값이 없는 곳은 빼고 그 수를 알려준다', () => {
    expect(myV1([m('A', null, 25)])).toEqual({ v1: null, skipped: 1 })
    expect(myV1([m('A', null, 25), m('B', 30, 28)]).skipped).toBe(1)
  })
})

describe('입력 검사', () => {
  it('0 이하·상한 초과·숫자 아님을 막는다', () => {
    expect(checkSeconds(0, 200, '녹색')).not.toBeNull()
    expect(checkSeconds(201, 200, '녹색')).not.toBeNull()
    expect(checkSeconds(Number.NaN, 200, '녹색')).not.toBeNull()
    expect(checkSeconds(0, 60, '점멸', true)).toBeNull()
    expect(checkSeconds(32.5, 200, '녹색')).toBeNull()
  })
})

describe('저장과 CSV', () => {
  it('브라우저 저장소에 저장했다가 다시 읽는다. 깨진 값은 비운다', () => {
    const store = new Map<string, string>()
    const storage = { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, v) }
    saveInputs(storage, { greens: {}, measurements: [m('A', 30, 26)] })
    expect(loadInputs(storage).measurements).toHaveLength(1)
    store.set('onroad.userInputs.v1', '{broken')
    expect(loadInputs(storage)).toEqual({ greens: {}, measurements: [] })
    expect(loadInputs(null)).toEqual({ greens: {}, measurements: [] })
  })

  it('CSV 는 BOM + 머리글 + 값', () => {
    const text = measurementsCsv([m('A', null, 26)])
    expect(text.startsWith('﻿cw_id,adm_cd')).toBe(true)
    expect(text).toContain('A,21090730,129.1,35.1,20,,26,0,')
  })
})
