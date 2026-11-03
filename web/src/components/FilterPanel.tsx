import { RADII, type BoundariesResponse } from '../api/types'
import { ADD_THRESHOLD_S, type PointFilter } from '../lib/points'
import { useAppState } from '../state/AppState'
import { RegionFilter } from './RegionFilter'

interface Props {
  /** 접혀 있으면 펼치기 버튼만 있는 얇은 막대로 그린다 */
  open: boolean
  onToggle: () => void
  boundaries: BoundariesResponse | null
  /** 필터를 적용한 뒤 지도에 보이는 점 수 */
  shown: { analyzed: number; candidates: number; excluded: number } | null
}

/** 왼쪽 패널: 지도에 무엇을 그릴지만 고른다(지역·레이어·점 필터·반경). 의미 설명은 지도 위 범례(MapLegend)에 둔다. */
export function FilterPanel({ open, onToggle, boundaries, shown }: Props) {
  const { basis, layers, toggleLayer, radius, setRadius, pointFilter: f, setPointFilter } = useAppState()
  const set = (patch: Partial<PointFilter>) => setPointFilter({ ...f, ...patch })
  const v2 = basis === 'v2'
  const n = (v: number | undefined) => (shown && layers.points && v !== undefined ? v.toLocaleString() : null)

  if (!open) {
    return (
      <aside className="filters collapsed" aria-label="지도 필터 (접힘)">
        <button type="button" className="f-fold" aria-expanded={false} aria-label="필터 펼치기" title="필터 펼치기" onClick={onToggle}>
          <span aria-hidden>»</span>
          <span className="f-fold-text">필터</span>
        </button>
      </aside>
    )
  }

  return (
    <aside className="filters" aria-label="지도 필터">
      <div className="f-head">
        <span>필터</span>
        <button type="button" className="icon-btn small" aria-expanded aria-label="필터 접기" title="필터 접기" onClick={onToggle}>«</button>
      </div>
      <section className="f-section">
        <h2 className="f-title">지역</h2>
        <RegionFilter boundaries={boundaries} />
      </section>

      <section className="f-section">
        <h2 className="f-title">레이어</h2>
        <Toggle checked={layers.choropleth} onChange={() => toggleLayer('choropleth')} label="읍면동 채색" />
        <Toggle checked={layers.points} onChange={() => toggleLayer('points')} label="횡단보도 점" count={n(shown?.analyzed)} />
      </section>

      <section className="f-section" aria-disabled={!layers.points}>
        <h2 className="f-title">횡단보도</h2>
        <div className="seg" role="radiogroup" aria-label="점 범위">
          {(['all', 'candidates'] as const).map((s) => (
            <button key={s} type="button" role="radio" aria-checked={f.scope === s} disabled={!layers.points}
              className={f.scope === s ? 'seg-btn on' : 'seg-btn'} onClick={() => set({ scope: s })}>
              {s === 'all' ? '전체' : v2 ? `${ADD_THRESHOLD_S}초+ 추가` : '후보만'}
            </button>
          ))}
        </div>
        <label className="f-row">
          <span>{v2 ? '추가 초' : '짧은 초'}</span>
          <span className="f-inline">
            <input type="number" step={1} value={f.gapValue} disabled={!layers.points}
              aria-label={v2 ? '추가 초 기준값' : '짧은 초 기준값'} onChange={(e) => set({ gapValue: Number(e.target.value) })} />
            <select value={f.gapOp ?? ''} aria-label="조건" disabled={!layers.points}
              onChange={(e) => set({ gapOp: (e.target.value || null) as PointFilter['gapOp'] })}>
              <option value="">조건 없음</option>
              <option value="gte">이상</option>
              <option value="lte">이하</option>
            </select>
          </span>
        </label>
        <Toggle checked={f.showExcluded} onChange={() => set({ showExcluded: !f.showExcluded })} disabled={!layers.points}
          label={v2 ? '분석 제외·기록 확인 점' : '분석 제외 점'} count={f.showExcluded ? n(shown?.excluded) : null} />
      </section>

      <section className="f-section">
        <h2 className="f-title" title="이 거리 안의 노인보호구역·대형 시장·주민 고령 비율로 적용 기준을 정합니다. 기본 300m는 보호구역 지정 범위를 따랐습니다">
          노출 반경
        </h2>
        <div className="seg" role="radiogroup" aria-label="노출 반경">
          {RADII.map((r) => (
            <button key={r} type="button" role="radio" aria-checked={r === radius}
              className={r === radius ? 'seg-btn on' : 'seg-btn'} onClick={() => setRadius(r)}>
              {r}m
            </button>
          ))}
        </div>
      </section>
    </aside>
  )
}

function Toggle({ checked, onChange, label, count, disabled }: {
  checked: boolean; onChange: () => void; label: string; count?: string | null; disabled?: boolean
}) {
  return (
    <label className={disabled ? 'toggle off' : 'toggle'}>
      <input type="checkbox" role="switch" checked={checked} onChange={onChange} disabled={disabled} />
      <span className="toggle-track" aria-hidden><span className="toggle-thumb" /></span>
      <span className="toggle-label">{label}</span>
      {count && <span className="toggle-count">{count}</span>}
    </label>
  )
}
