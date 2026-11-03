import { describe, expect, it } from 'vitest'
import type { PointProps } from '../api/types'
import { v1Narrative, v2Narrative } from './narrative'

const base: PointProps = {
  cw_id: 'busan-00001', adm_cd: '2635053000', status: 'analyzed', length_m: 35, green_s: 42, t_need_s: 50.75, gap_s: 8.75,
  flags: null, exposure_cnt: 1, is_candidate: true, exclude_reason: null,
  tier: 1, formula_class: '1.0', resident_elderly_ratio: 0.31, user_elderly_ratio: 1, v_applied_mps: 0.7,
  t_required_s: 57, add_s: 15, coverage_now: 0.69, coverage_required: 0.94,
  reason_parts: { protect_zone_m: 120, market_name: null, market_m: null },
}

describe('분석 요약 문장', () => {
  it('보호구역 기준: 보호구역 거리·속도·시간·커버리지·기준식이 내보낸 값 그대로 들어간다', () => {
    const n = v2Narrative(base, 0.85, 300)
    const text = n.paragraphs.map((p) => p.text).join(' ')
    expect(n.paragraphs.map((p) => p.title)).toEqual(['적용 속도', '기준 적용 시간', '고령 보행자 커버리지', '현재 기록의 기준식'])
    expect(text).toContain('노인보호구역에서 120m')
    expect(text).toContain('57.0초가 필요')
    expect(text).toContain('15.0초 깁니다')
    expect(text).toContain('69%에서 기준 적용 시 94%')
    expect(text).toContain('일반 기준식(1.0m/s)')
  })

  it('추가 시간이 없으면 더할 시간이 없다고 쓴다', () => {
    const n = v2Narrative({ ...base, tier: 3, t_required_s: 42, add_s: 0, coverage_required: 0.69 }, 0.85, 300)
    const text = n.paragraphs.map((p) => p.text).join(' ')
    expect(text).toContain('더할 시간이 없습니다')
    expect(text).not.toContain('기준 적용 시 69%')
  })

  it('기록 확인·분석 제외 점은 사유만 쓴다', () => {
    expect(v2Narrative({ ...base, status: 'data_check', check_reason: '기록 방식 확인' }, 0.85, 300).paragraphs).toHaveLength(1)
    const ex = v2Narrative({ ...base, status: 'excluded', exclude_reason: 'green_missing' }, 0.85, 300)
    expect(ex.paragraphs[0].text).toContain('녹색신호시간 기록 없음')
  })

  it('기록값 기준: 짧은 초와 후보 여부', () => {
    const text = v1Narrative(base, 0.8).paragraphs.map((p) => p.text).join(' ')
    expect(text).toContain('8.8초 짧습니다')
    expect(text).toContain('점검 우선순위 후보')
  })
})
