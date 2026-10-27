import { useMemo, useState } from 'react'
import type { AreasResponse } from '../api/types'
import { pct1 } from '../lib/format'
import { classify, effectiveThresholds } from '../lib/quadrant'
import { rankAreas, SORT_LABEL, TOP_N_OPTIONS, type SortKey } from '../lib/ranking'
import { regionLabel } from '../lib/region'
import { useAppState } from '../state/AppState'

/** 상위 N 지역 목록 (F7). 행을 누르면 지도가 그 지역으로 이동하고 상세가 열린다. */
export function TopList({ data }: { data: AreasResponse | null }) {
  const { select, customThresholds, region } = useAppState()
  const [sortKey, setSortKey] = useState<SortKey>('short_ratio')
  const [n, setN] = useState<number>(TOP_N_OPTIONS[0])

  const t = effectiveThresholds(data, customThresholds)
  const result = useMemo(() => (data ? rankAreas(data.items, sortKey, n) : null), [data, sortKey, n])

  if (!data || !result) {
    return (
      <section className="card">
        <h3>상위 지역</h3>
        <p className="muted">불러오는 중…</p>
      </section>
    )
  }

  const maxRatio = Math.max(0.01, ...result.rows.map((r) => r.short_ratio ?? 0))

  return (
    <section className="card toplist">
      <div className="card-head">
        <h3>{regionLabel(region)} 상위 {n}개 지역</h3>
      </div>
      <div className="toplist-controls">
        <label>
          N
          <select value={n} onChange={(e) => setN(Number(e.target.value))}>
            {TOP_N_OPTIONS.map((v) => <option key={v} value={v}>{v}</option>)}
          </select>
        </label>
        <label>
          정렬
          <select value={sortKey} onChange={(e) => setSortKey(e.target.value as SortKey)}>
            {(Object.keys(SORT_LABEL) as SortKey[]).map((k) => <option key={k} value={k}>{SORT_LABEL[k]}</option>)}
          </select>
        </label>
      </div>

      {result.rows.length === 0 ? (
        <p className="muted">순위에 올릴 지역이 없습니다.</p>
      ) : (
        <ol className="toplist-rows">
          {result.rows.map((a, i) => {
            const priority = t && a.short_ratio !== null && a.ratio_65plus !== null && classify(a.short_ratio, a.ratio_65plus, t) === 'high_high'
            return (
              <li key={a.adm_cd}>
                <button type="button" className="toplist-row" onClick={() => select(a.adm_cd, 'list')}>
                  <span className="rank">{i + 1}</span>
                  <span className="name">
                    <b>{a.adm_name}</b>
                    <small className="muted">{a.sigungu}</small>
                    {priority && <span className="tag">후보 지역</span>}
                  </span>
                  <span className="ratio">
                    <span className="bar"><span style={{ width: `${((a.short_ratio ?? 0) / maxRatio) * 100}%` }} /></span>
                    <span className="num">{pct1(a.short_ratio)}</span>
                  </span>
                  <span className="cand" title="점검 우선순위 후보 횡단보도 수">{a.n_candidate}</span>
                </button>
              </li>
            )
          })}
        </ol>
      )}

      <p className="toplist-foot muted">
        막대: 기준식보다 짧은 비율 · 오른쪽 숫자: 후보 횡단보도 수
        {result.excludedLowSample > 0 && <><br />표본 부족 {result.excludedLowSample}곳은 순위에서 제외</>}
        {result.excludedNoValue > 0 && <><br />값 없음 {result.excludedNoValue}곳 제외</>}
      </p>
    </section>
  )
}
