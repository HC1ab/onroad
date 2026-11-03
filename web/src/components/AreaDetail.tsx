import { useState } from 'react'
import { api } from '../api/client'
import type { AreaItem, AreasResponse, CrosswalkItem, ExposureFlags, PointProps } from '../api/types'
import type { AreaMetric } from '../lib/areaMetric'
import { useApi } from '../hooks/useApi'
import { gap1, meter, pct1, sec1 } from '../lib/format'
import { classify, effectiveThresholds } from '../lib/quadrant'
import { sortCrosswalks } from '../lib/ranking'
import { fmtPct, TIER_LABEL } from '../lib/recommend'
import { useAppState } from '../state/AppState'

const FLAGS: { key: keyof ExposureFlags; short: string; label: string }[] = [
  { key: 'senior_center', short: '경', label: '경로당' },
  { key: 'market', short: '시', label: '전통시장' },
  { key: 'protect_zone', short: '보', label: '노인·장애인 보호구역' },
  { key: 'crash_zone_past', short: '사', label: '노인 보행사고 다발지역(과거 연도)' },
]

const quadrantLabel = (q: 'high_high' | 'high_low' | 'low_high' | 'low_low', x: string) =>
  ({
    high_high: `${x}·고령 비율 모두 높음 (점검 우선순위 후보)`,
    high_low: `${x} 높음 · 고령 비율 낮음`,
    low_high: `${x} 낮음 · 고령 비율 높음`,
    low_low: `${x}·고령 비율 모두 낮음`,
  })[q]

interface Props {
  area: AreaItem
  thresholdsData: { min_sample?: number; thresholds: AreasResponse['thresholds'] } | null
  metric: AreaMetric
}

/** 지역 상세 패널 (F7). 오른쪽 패널을 넓혀서 보여준다. */
export function AreaDetail({ area, thresholdsData, metric }: Props) {
  const { basis, target, speed, radius, select, customThresholds, point, setPoint } = useAppState()
  const v2 = basis === 'v2'
  const [onlyShort, setOnlyShort] = useState(true)
  const cws = useApi((s) => (v2 ? Promise.resolve(null) : api.areaCrosswalks(area.adm_cd, speed, radius, s)), [v2, area.adm_cd, speed, radius])

  const t = effectiveThresholds(thresholdsData, customThresholds, metric.median)
  const x = metric.value(area)
  const quadrant = t && x !== null && area.ratio_65plus !== null ? classify(x, area.ratio_65plus, t) : null
  const rows = cws.data ? sortCrosswalks(cws.data.items, onlyShort) : []

  const onRow = (c: CrosswalkItem) =>
    // 표에서 고르면 지도가 그 횡단보도로 이동하고 정보 카드가 열린다(지도에서 고르면 이 행이 강조된다).
    setPoint({
      cwId: c.cw_id, lat: c.lat, lon: c.lon, source: 'list',
      props: { ...c, adm_cd: area.adm_cd, status: 'analyzed', exclude_reason: null },
    })

  return (
    <section className="detail" aria-label={`${area.adm_name} 상세`}>
      <div className="detail-head">
        <button type="button" className="link-btn" onClick={() => select(null, 'list')}>← 목록으로</button>
        <button type="button" className="close-btn" aria-label="상세 닫기" onClick={() => select(null, 'list')}>✕</button>
      </div>
      <h2>{area.adm_name}</h2>
      <p className="muted">
        {area.sido} {area.sigungu} · {v2 ? `상황별 기준 · 목표 커버리지 ${Math.round(target * 100)}%` : `속도 기준 ${speed.toFixed(1)} m/s`} · 노출 반경 {radius}m
      </p>

      <dl className="stats">
        <div><dt>65세 이상 비율</dt><dd>{pct1(area.ratio_65plus)}</dd></div>
        <div><dt>분석 횡단보도</dt><dd>{area.n_analyzed}곳</dd></div>
        {v2 ? (
          <>
            <div><dt>기준 적용 시 평균 추가</dt><dd>{sec1(area.mean_add_s)}</dd></div>
            <div><dt>2초 이상 추가</dt><dd>{area.n_add2 ?? 0}곳</dd></div>
            <div><dt>고령 커버리지(평균)</dt><dd>{fmtPct(area.coverage_now_mean)} → {fmtPct(area.coverage_required_mean)}</dd></div>
          </>
        ) : (
          <>
            <div><dt>기준식보다 짧음</dt><dd>{area.n_short}곳 · {pct1(area.short_ratio)}</dd></div>
            <div><dt>평균 짧은 초</dt><dd>{sec1(area.mean_gap_s)}</dd></div>
            <div><dt>점검 우선순위 후보</dt><dd>{area.n_candidate}곳</dd></div>
          </>
        )}
        <div><dt>사분면</dt><dd className="small">{area.low_sample ? '표본 부족 (순위 제외)' : quadrant ? quadrantLabel(quadrant, metric.short) : '—'}</dd></div>
      </dl>

      <div className="notes">
        {area.low_sample && (
          <p className="note warn">
            분석 횡단보도가 {area.n_analyzed}곳으로 표본 하한{thresholdsData?.min_sample ? `(${thresholdsData.min_sample}곳)` : ''} 미만입니다. 지도에서 회색으로 표시하고 순위에서 뺍니다.
          </p>
        )}
        <p className="note">읍면동 평균은 그 동의 개별 횡단보도 이용자 구성을 뜻하지 않습니다.</p>
      </div>

      {v2 ? (
        <CrosswalksV2 admCd={area.adm_cd} />
      ) : (
      <>
      <div className="cw-head">
        <h3>횡단보도 목록</h3>
        <label className="check">
          <input type="checkbox" checked={onlyShort} onChange={() => setOnlyShort((v) => !v)} />
          기준식보다 짧은 곳만
        </label>
      </div>

      {cws.error ? (
        <div className="load-inline error" role="alert">
          {cws.error.message}
          <button type="button" onClick={cws.reload}>다시 시도</button>
        </div>
      ) : cws.loading && !cws.data ? (
        <p className="muted">불러오는 중…</p>
      ) : rows.length === 0 ? (
        <p className="muted">{onlyShort ? '기준식보다 짧은 횡단보도가 없습니다.' : '분석한 횡단보도가 없습니다.'}</p>
      ) : (
        <table className="cw-table">
          <thead>
            <tr><th>연장</th><th>기록</th><th>필요</th><th>짧은 초</th><th>노출</th></tr>
          </thead>
          <tbody>
            {rows.map((c) => (
              <tr
                key={c.cw_id}
                className={point?.cwId === c.cw_id ? 'on' : undefined}
                tabIndex={0}
                onClick={() => onRow(c)}
                onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && onRow(c)}
              >
                <td>{meter(c.length_m)}</td>
                <td>{sec1(c.green_s)}</td>
                <td>{sec1(c.t_need_s)}</td>
                <td className={c.gap_s > 0 ? 'gap pos' : 'gap'}>{gap1(c.gap_s)}</td>
                <td className="flags">
                  {FLAGS.map((f) => (
                    <span key={f.key} className={c.flags[f.key] ? 'flag on' : 'flag'} title={f.label}>{f.short}</span>
                  ))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="muted small">
        {FLAGS.map((f) => `${f.short} ${f.label}`).join(' · ')}. 짧은 초가 양수면 기록된 녹색신호시간이 기준식보다 짧습니다. 행을 누르면 지도에서 위치를 보여줍니다.
      </p>
      </>
      )}
    </section>
  )
}

/** 3단계 기준 화면의 횡단보도 목록(#81): 추가 초 큰 순, 같으면 단계 1 → 2 → 3 */
function CrosswalksV2({ admCd }: { admCd: string }) {
  const { target, radius, point, setPoint } = useAppState()
  const [onlyAdd, setOnlyAdd] = useState(true)
  const pts = useApi((s) => api.pointsV2(target, radius, undefined, s), [target, radius])
  const all = (pts.data?.features ?? []).filter((f) => f.properties.adm_cd === admCd && f.properties.status !== 'excluded')
  const rows = all
    .filter((f) => !onlyAdd || (f.properties.add_s ?? 0) > 0)
    .sort((a, b) => (b.properties.add_s ?? -1) - (a.properties.add_s ?? -1) || (a.properties.tier ?? 9) - (b.properties.tier ?? 9))
  const onRow = (f: GeoJSON.Feature<GeoJSON.Point, PointProps>) => {
    const [lon, lat] = f.geometry.coordinates
    setPoint({ cwId: f.properties.cw_id, lon, lat, props: f.properties, source: 'list' })
  }
  return (
    <>
      <div className="cw-head">
        <h3>횡단보도 목록</h3>
        <label className="check">
          <input type="checkbox" checked={onlyAdd} onChange={() => setOnlyAdd((v) => !v)} />
          기준 적용 시 추가되는 곳만
        </label>
      </div>
      {pts.error ? (
        <div className="load-inline error" role="alert">
          {pts.error.message}
          <button type="button" onClick={pts.reload}>다시 시도</button>
        </div>
      ) : pts.loading && !pts.data ? (
        <p className="muted">불러오는 중…</p>
      ) : rows.length === 0 ? (
        <p className="muted">{onlyAdd ? '기준 적용 시 추가되는 횡단보도가 없습니다.' : '분석한 횡단보도가 없습니다.'}</p>
      ) : (
        <table className="cw-table">
          <thead>
            <tr><th>적용 기준</th><th>연장</th><th>기록</th><th>기준 적용</th><th>고령 커버리지</th></tr>
          </thead>
          <tbody>
            {rows.map((f) => {
              const p = f.properties
              return (
                <tr
                  key={p.cw_id}
                  className={point?.cwId === p.cw_id ? 'on' : undefined}
                  tabIndex={0}
                  onClick={() => onRow(f)}
                  onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && onRow(f)}
                >
                  <td>
                    {p.tier ? TIER_LABEL[p.tier] : '—'}
                  </td>
                  <td>{p.length_m === null ? '—' : meter(p.length_m)}</td>
                  <td>{sec1(p.green_s)}</td>
                  {p.status === 'data_check' ? (
                    <td colSpan={2} className="muted small">기록 확인 중</td>
                  ) : (
                    <>
                      <td className={(p.add_s ?? 0) > 0 ? 'gap pos' : 'gap'}>{sec1(p.t_required_s)} (+{(p.add_s ?? 0).toFixed(1)})</td>
                      <td>{fmtPct(p.coverage_now)} → {fmtPct(p.coverage_required)}</td>
                    </>
                  )}
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
      <p className="muted small">
        적용 기준: 보호구역(반경 안 노인보호구역, 0.7m/s) → 시장(대형 전통시장) → 주민(그 외, 주민 고령 비율) 순으로 먼저 걸리는 하나. 기준 적용 = max(기록값, 7 + 연장/적용 속도). 고령 커버리지는 고령 보행자 중 그 시간 안에 건너는 비율로, 정답 확률이 아닙니다. 행을 누르면 지도에서 위치를 보여줍니다.
      </p>
    </>
  )
}
