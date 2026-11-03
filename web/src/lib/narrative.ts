import type { PointProps, Radius, Speed, Target } from '../api/types'
import { EXCLUDE_REASON_LABEL } from './points'
import { V2_COEF } from './recommend'

// 선택한 횡단보도의 분석 요약 문장. 내보낸 값만 조합하는 규칙 기반 문장이라 숫자가 화면 수치와 항상 같다.
// 표현 원칙(PRD 3장): 조건형으로 쓰고 판정하지 않는다. 금지 표현 검사는 wording.test.ts.

const pct = (v: number) => `${Math.round(v * 100)}%`
const s1 = (v: number) => `${v.toFixed(1)}초`
const m0 = (v: number) => `${Math.round(v)}m`

const FORMULA_TEXT: Record<string, string> = {
  '1.0': '일반 기준식(1.0m/s)',
  '0.8': '보행약자 기준식(0.8m/s)',
  '0.7': '노인 기준식(0.7m/s)',
}

export interface Narrative {
  /** 문단 제목과 본문 */
  paragraphs: { title: string; text: string }[]
  /** 맨 아래 한계 고지 한 줄 */
  caveat: string
}

const CAVEAT = '보행시간 정의(점멸 포함 여부) 확정 전 값입니다. 점검 우선순위를 정하기 위한 후보이며 판정이 아닙니다.'

/** 3단계 기준(v2) 횡단보도 요약 */
export function v2Narrative(p: PointProps, target: Target, radius: Radius): Narrative {
  if (p.status === 'excluded') {
    const why = p.exclude_reason ? EXCLUDE_REASON_LABEL[p.exclude_reason] : '기록 확인이 필요한 값'
    return { paragraphs: [{ title: '분석 제외', text: `${why}이라 기준식과 비교하지 않았습니다.` }], caveat: CAVEAT }
  }
  if (p.status === 'data_check') {
    return {
      paragraphs: [{ title: '기록 방식 확인 중', text: p.check_reason ?? '기록 방식을 확인하기 전까지 집계에서 뺍니다.' }],
      caveat: CAVEAT,
    }
  }
  const out: Narrative['paragraphs'] = []
  const v = p.v_applied_mps
  const parts = p.reason_parts
  if (p.tier === 1) {
    const d = parts?.protect_zone_m != null ? `노인보호구역에서 ${m0(parts.protect_zone_m)} 거리라 ` : ''
    out.push({ title: '적용 속도', text: `${d}보호구역 기준을 적용했습니다. 보호구역 보행속도 ${V2_COEF.tier1Speed}m/s를 적용합니다.` })
  } else if (p.tier === 2 && v != null) {
    const where = !parts?.market_name ? '' : parts.market_m != null ? `${parts.market_name}에서 ${m0(parts.market_m)} 거리라 ` : `${parts.market_name} 근처라 `
    const users = p.resident_elderly_ratio != null && p.user_elderly_ratio != null
      ? `반경 주민 고령 비율 ${pct(p.resident_elderly_ratio)}에 시장 이용 보정을 더해 이용자 고령 비율을 ${pct(p.user_elderly_ratio)}로 보고, `
      : ''
    out.push({ title: '적용 속도', text: `${where}시장 기준을 적용했습니다. ${users}이용자 ${pct(target)}가 건널 수 있는 속도 ${v.toFixed(2)}m/s를 적용합니다.` })
  } else if (v != null) {
    const res = p.resident_elderly_ratio != null ? `반경 ${radius}m 안 주민 고령 비율 ${pct(p.resident_elderly_ratio)}로 이용자 구성을 보고, ` : ''
    out.push({ title: '적용 속도', text: `${res}이용자 ${pct(target)}가 건널 수 있는 속도 ${v.toFixed(2)}m/s를 적용합니다(주민 기준).` })
  }

  if (p.t_required_s != null && p.green_s != null && p.length_m != null) {
    const add = p.add_s ?? 0
    out.push({
      title: '기준 적용 시간',
      text: add > 0
        ? `연장 ${m0(p.length_m)}를 이 속도로 건너려면 진입 ${V2_COEF.entryS}초를 더해 ${s1(p.t_required_s)}가 필요합니다. 현재 기록 ${s1(p.green_s)}보다 ${s1(add)} 깁니다.`
        : `현재 기록 ${s1(p.green_s)}가 기준 적용 시간 ${s1(p.t_required_s)} 이상이라 더할 시간이 없습니다.`,
    })
  }

  if (p.coverage_now != null && p.coverage_required != null) {
    const same = Math.round(p.coverage_now * 100) === Math.round(p.coverage_required * 100)
    out.push({
      title: '고령 보행자 커버리지',
      text: same
        ? `고령 보행자 중 현재 시간 안에 건널 수 있는 비율은 ${pct(p.coverage_now)}입니다.`
        : `고령 보행자 중 시간 안에 건널 수 있는 비율이 현재 ${pct(p.coverage_now)}에서 기준 적용 시 ${pct(p.coverage_required)}가 됩니다. 정답 확률이 아니라 속도 분포로 계산한 값입니다.`,
    })
  }

  if (p.formula_class) {
    out.push({
      title: '현재 기록의 기준식',
      text: p.formula_class === 'other'
        ? '현재 기록은 세 기준식(1.0·0.8·0.7m/s) 어느 것과도 같지 않습니다.'
        : `현재 기록은 ${FORMULA_TEXT[p.formula_class]}으로 계산한 값과 같습니다.`,
    })
  }
  return { paragraphs: out, caveat: CAVEAT }
}

/** 기록값 기준(v1) 횡단보도 요약 */
export function v1Narrative(p: PointProps, speed: Speed): Narrative {
  if (p.status === 'excluded') return v2Narrative(p, 0.85, 300)
  const out: Narrative['paragraphs'] = []
  if (p.gap_s != null && p.t_need_s != null && p.green_s != null) {
    const g = p.gap_s
    out.push({
      title: '기준식 비교',
      text: g > 0
        ? `보행 속도 ${speed.toFixed(1)}m/s 기준식으로는 ${s1(p.t_need_s)}가 필요한데 기록은 ${s1(p.green_s)}라 ${s1(g)} 짧습니다.`
        : `보행 속도 ${speed.toFixed(1)}m/s 기준식 ${s1(p.t_need_s)}보다 기록 ${s1(p.green_s)}가 ${s1(Math.abs(g))} 여유 있습니다.`,
    })
  }
  out.push({
    title: '노출',
    text: p.exposure_cnt > 0
      ? `반경 안에 고령자 목적지 ${p.exposure_cnt}종이 있습니다.${p.is_candidate ? ' 기록이 기준식보다 짧으면서 노출이 있어 점검 우선순위 후보입니다.' : ''}`
      : '반경 안에 고령자 목적지가 없습니다.',
  })
  return { paragraphs: out, caveat: CAVEAT }
}
