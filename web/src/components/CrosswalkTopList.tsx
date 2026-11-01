import { useMemo, useState } from 'react'
import type { AreaItem, PointProps, PointsResponse } from '../api/types'
import { meter, sec1 } from '../lib/format'
import { TOP_N_OPTIONS } from '../lib/ranking'
import { fmtPct, TIER_LABEL } from '../lib/recommend'
import { regionLabel } from '../lib/region'
import { useAppState } from '../state/AppState'
import { TIER_COLORS } from './mapStyle'

interface Props {
  /** 3단계 기준 횡단보도 점(지도 범위와 관계없이 전체) */
  points: PointsResponse | null
  /** 지역 필터를 적용한 읍면동. 이 안의 횡단보도만 순위에 올린다 */
  areas: AreaItem[] | null
  error: Error | null
  onRetry: () => void
}

/** 횡단보도 우선순위(#82): 기준 적용 시 추가 초 큰 순, 같으면 단계 1 → 2 → 3. 행을 누르면 지도 이동과 정보 카드 */
export function CrosswalkTopList({ points, areas, error, onRetry }: Props) {
  const { select, setPoint, region, point } = useAppState()
  const [n, setN] = useState<number>(TOP_N_OPTIONS[0])

  const rows = useMemo(() => {
    if (!points || !areas) return null
    const names = new Map(areas.map((a) => [a.adm_cd, a]))
    return points.features
      .filter((f) => f.properties.status === 'analyzed' && (f.properties.add_s ?? 0) > 0 && names.has(f.properties.adm_cd))
      .sort((a, b) => (b.properties.add_s ?? 0) - (a.properties.add_s ?? 0) || (a.properties.tier ?? 9) - (b.properties.tier ?? 9))
      .slice(0, n)
      .map((f) => ({ f, area: names.get(f.properties.adm_cd)! }))
  }, [points, areas, n])

  const open = (f: GeoJSON.Feature<GeoJSON.Point, PointProps>) => {
    const [lon, lat] = f.geometry.coordinates
    select(f.properties.adm_cd, 'list')
    setPoint({ cwId: f.properties.cw_id, lon, lat, props: f.properties, source: 'list' })
  }

  return (
    <section className="card toplist">
      <div className="card-head">
        <h3>{regionLabel(region)} 횡단보도 우선순위 {n}곳</h3>
        <label className="toplist-controls">
          N
          <select value={n} onChange={(e) => setN(Number(e.target.value))}>
            {TOP_N_OPTIONS.map((v) => <option key={v} value={v}>{v}</option>)}
          </select>
        </label>
      </div>
      {error ? (
        <div className="load-inline error" role="alert">
          {error.message}
          <button type="button" onClick={onRetry}>다시 시도</button>
        </div>
      ) : !rows ? (
        <p className="muted">불러오는 중…</p>
      ) : rows.length === 0 ? (
        <p className="muted">기준 적용 시 시간이 추가되는 횡단보도가 없습니다.</p>
      ) : (
        <ol className="toplist-rows">
          {rows.map(({ f, area }, i) => {
            const p = f.properties
            return (
              <li key={p.cw_id}>
                <button type="button" className={point?.cwId === p.cw_id ? 'toplist-row cw on' : 'toplist-row cw'} onClick={() => open(f)}>
                  <span className="rank">{i + 1}</span>
                  <span className="name">
                    <b>{area.adm_name}</b>
                    <small className="muted">
                      {p.tier && <i className="dot" style={{ background: TIER_COLORS[p.tier] }} title={TIER_LABEL[p.tier]} />} {p.tier}단계 ·{' '}
                      {p.length_m !== null ? meter(p.length_m) : '—'} · 고령 {fmtPct(p.coverage_now)} → {fmtPct(p.coverage_required)}
                    </small>
                  </span>
                  <span className="num">{sec1(p.green_s)} → {sec1(p.t_required_s)}</span>
                  <span className="cand" title="기준 적용 시 추가 초">+{(p.add_s ?? 0).toFixed(1)}</span>
                </button>
              </li>
            )
          })}
        </ol>
      )}
      <p className="toplist-foot muted">
        기준 적용 시 추가 초 큰 순, 같으면 단계 1(노인보호구역) → 2(대형 시장) → 3. 오른쪽 숫자: 추가 초. 보행시간 정의 확정 전 값입니다.
      </p>
    </section>
  )
}
