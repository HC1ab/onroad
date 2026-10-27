import { useState } from 'react'
import { api } from '../api/client'
import type { AreaItem, CrosswalkItem, ExposureFlags } from '../api/types'
import { useApi } from '../hooks/useApi'
import { gap1, meter, pct1, sec1 } from '../lib/format'
import { classify, effectiveThresholds } from '../lib/quadrant'
import { sortCrosswalks } from '../lib/ranking'
import { useAppState } from '../state/AppState'

const FLAGS: { key: keyof ExposureFlags; short: string; label: string }[] = [
  { key: 'senior_center', short: '경', label: '경로당' },
  { key: 'market', short: '시', label: '전통시장' },
  { key: 'protect_zone', short: '보', label: '노인·장애인 보호구역' },
  { key: 'crash_zone_past', short: '사', label: '노인 보행사고 다발지역(과거 연도)' },
]

const QUADRANT_LABEL = {
  high_high: '짧음 비율·고령 비율 모두 높음 (점검 우선순위 후보)',
  high_low: '짧음 비율 높음 · 고령 비율 낮음',
  low_high: '짧음 비율 낮음 · 고령 비율 높음',
  low_low: '짧음 비율·고령 비율 모두 낮음',
} as const

interface Props {
  area: AreaItem
  thresholdsData: { thresholds: { short_ratio_median: number; ratio_65plus_median: number } } | null
}

/** 지역 상세 패널 (F7). 오른쪽 패널을 넓혀서 보여준다. */
export function AreaDetail({ area, thresholdsData }: Props) {
  const { speed, select, customThresholds, focus, setFocus } = useAppState()
  const [onlyShort, setOnlyShort] = useState(true)
  const cws = useApi((s) => api.areaCrosswalks(area.adm_cd, speed, s), [area.adm_cd, speed])

  const t = effectiveThresholds(thresholdsData, customThresholds)
  const quadrant = t && area.short_ratio !== null && area.ratio_65plus !== null ? classify(area.short_ratio, area.ratio_65plus, t) : null
  const rows = cws.data ? sortCrosswalks(cws.data.items, onlyShort) : []

  const onRow = (c: CrosswalkItem) =>
    setFocus({ cwId: c.cw_id, lat: c.lat, lon: c.lon, label: `${meter(c.length_m)} · 기록 ${sec1(c.green_s)} · ${c.gap_s > 0 ? `기준식보다 ${sec1(c.gap_s)} 짧음` : '기준식 이상'}` })

  return (
    <section className="detail" aria-label={`${area.adm_name} 상세`}>
      <div className="detail-head">
        <button type="button" className="link-btn" onClick={() => select(null, 'list')}>← 목록으로</button>
        <button type="button" className="close-btn" aria-label="상세 닫기" onClick={() => select(null, 'list')}>✕</button>
      </div>
      <h2>{area.adm_name}</h2>
      <p className="muted">{area.sido} {area.sigungu} · 속도 기준 {speed.toFixed(1)} m/s</p>

      <dl className="stats">
        <div><dt>65세 이상 비율</dt><dd>{pct1(area.ratio_65plus)}</dd></div>
        <div><dt>분석 횡단보도</dt><dd>{area.n_analyzed}곳</dd></div>
        <div><dt>기준식보다 짧음</dt><dd>{area.n_short}곳 · {pct1(area.short_ratio)}</dd></div>
        <div><dt>평균 짧은 초</dt><dd>{sec1(area.mean_gap_s)}</dd></div>
        <div><dt>점검 우선순위 후보</dt><dd>{area.n_candidate}곳</dd></div>
        <div><dt>사분면</dt><dd className="small">{area.low_sample ? '표본 부족 (순위 제외)' : quadrant ? QUADRANT_LABEL[quadrant] : '—'}</dd></div>
      </dl>

      <div className="notes">
        {area.low_sample && (
          <p className="note warn">
            분석 횡단보도가 {area.n_analyzed}곳으로 표본 하한 미만입니다. 지도에서 회색으로 표시하고 순위에서 뺍니다.
          </p>
        )}
        <p className="note">읍면동 평균은 그 동의 개별 횡단보도 이용자 구성을 뜻하지 않습니다.</p>
      </div>

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
                className={focus?.cwId === c.cw_id ? 'on' : undefined}
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
    </section>
  )
}
