import { useMemo } from 'react'
import { api } from '../api/client'
import type { PointsResponse } from '../api/types'
import { useApi } from '../hooks/useApi'
import { computeFindings } from '../lib/findings'
import { pct0, pct1 } from '../lib/format'
import { ADD_THRESHOLD_S, DEFAULT_POINT_FILTER, type PointFilter } from '../lib/points'
import { pValue } from '../lib/validation'
import { useAppState } from '../state/AppState'

/**
 * 오른쪽 패널 기본 상태 맨 위: 이 분석으로 부산에서 찾은 것 세 가지.
 * 결론을 먼저 읽고, 카드를 눌러 지도에서 해당 횡단보도만 확인한다. 수치는 모두 내보낸 결과에서 센다(findings.ts).
 */
export function Findings({ points }: { points: PointsResponse | null }) {
  const { radius, pointFilter, setPointFilter, layers, toggleLayer } = useAppState()
  const validation = useApi((s) => api.validation(s), [])
  const f = useMemo(() => computeFindings(points, validation.data), [points, validation.data])
  if (!f.zone && !f.accident) return null

  const zoneFilter: PointFilter = { ...DEFAULT_POINT_FILTER, tier: 1 }
  const add2Filter: PointFilter = { ...DEFAULT_POINT_FILTER, scope: 'candidates' }
  const same = (a: PointFilter) => JSON.stringify(a) === JSON.stringify(pointFilter)
  const show = (next: PointFilter) => {
    setPointFilter(same(next) ? DEFAULT_POINT_FILTER : next)
    if (!layers.points) toggleLayer('points')
  }

  return (
    <section className="findings" aria-label="부산에서 찾은 것">
      <h2 className="fd-title">부산에서 찾은 것</h2>

      {f.zone && (
        <article className="finding">
          <p className="fd-eyebrow">노인보호구역 기준 반영</p>
          <p className="fd-value">{pct0(f.zone.n07 / f.zone.n)}</p>
          <p className="fd-text">
            노인보호구역 {radius}m 안 횡단보도 <b>{f.zone.n.toLocaleString()}곳</b> 중 기록값이 보호구역 기준식(0.7m/s)과 같은 곳은{' '}
            <b>{f.zone.n07.toLocaleString()}곳</b>입니다.
            {f.zone.childRatio != null && <> 어린이보호구역(150m)은 <b>{pct0(f.zone.childRatio)}</b>입니다.</>}
          </p>
          <FindingAction active={same(zoneFilter)} onClick={() => show(zoneFilter)} label={`지도에서 ${f.zone.n.toLocaleString()}곳 보기`} />
        </article>
      )}

      {f.focus && f.focus.nAdd2 > 0 && (
        <article className="finding">
          <p className="fd-eyebrow">{ADD_THRESHOLD_S}초 이상 추가되는 곳</p>
          <p className="fd-value">{pct0(f.focus.zoneAdd2 / f.focus.nAdd2)}<small>노인보호구역 주변</small></p>
          <p className="fd-text">
            {ADD_THRESHOLD_S}초 이상 추가되는 <b>{f.focus.nAdd2.toLocaleString()}곳</b> 중 <b>{f.focus.zoneAdd2.toLocaleString()}곳</b>이 노인보호구역 주변입니다.
            이곳들은 평균 <b>+{f.focus.zoneMeanAdd.toFixed(1)}초</b>, 고령 보행자 커버리지가 <b>{pct0(f.focus.zoneCovNow)} → {pct0(f.focus.zoneCovReq)}</b>가 됩니다.
            나머지 횡단보도는 추가가 생겨도 평균 +{f.focus.restMeanAdd.toFixed(1)}초입니다.
          </p>
          <FindingAction active={same(add2Filter)} onClick={() => show(add2Filter)} label={`지도에서 ${f.focus.nAdd2.toLocaleString()}곳 보기`} />
        </article>
      )}

      {f.accident && (
        <article className="finding">
          <p className="fd-eyebrow">노인 보행사고 다발지역과 겹침</p>
          <p className="fd-value">{f.accident.vsRandom.toFixed(1)}배<small>무작위 대비</small></p>
          <p className="fd-text">
            {f.accident.speed.toFixed(1)}m/s 기준식보다 짧은 점검 후보가 최근({f.accident.years[0]}–{f.accident.years[f.accident.years.length - 1]}) 노인 보행사고
            다발지역과 겹치는 비율은 <b>{pct1(f.accident.ratio)}</b>입니다(p = {pValue(f.accident.p)}). 연관이며 원인은 아닙니다.
          </p>
          <a className="fd-action" href="#/validation">검증 근거 보기 →</a>
        </article>
      )}

      <p className="fd-note">보행시간 정의(점멸 포함 여부) 확정 전 값 · 점검 우선순위 후보이며 판정이 아닙니다</p>
    </section>
  )
}

function FindingAction({ active, onClick, label }: { active: boolean; onClick: () => void; label: string }) {
  return (
    <button type="button" className={active ? 'fd-action on' : 'fd-action'} aria-pressed={active} onClick={onClick}>
      {active ? '지도에서 보는 중 · 전체로 돌아가기' : `${label} →`}
    </button>
  )
}
