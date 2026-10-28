import { useMemo } from 'react'
import type { BoundariesResponse } from '../api/types'
import { regionOptions } from '../lib/region'
import { useAppState } from '../state/AppState'

/** 시도·시군구 필터 (F10). 고르는 즉시 지도가 그 지역으로 이동하고, 목록·사분면이 그 지역으로 좁혀진다. */
export function RegionFilter({ boundaries }: { boundaries: BoundariesResponse | null }) {
  const { region, setRegion } = useAppState()
  const opts = useMemo(() => (boundaries ? regionOptions(boundaries) : null), [boundaries])
  if (!opts) return null
  const sigungus = region ? opts.sigungus[region.sido] ?? [] : []

  return (
    <div className="region" role="group" aria-label="지역 필터">
      <span className="speed-title">지역</span>
      <select
        aria-label="시도"
        value={region?.sido ?? ''}
        onChange={(e) => setRegion(e.target.value ? { sido: e.target.value, sigungu: null } : null)}
      >
        <option value="">전국</option>
        {opts.sidos.map((s) => <option key={s} value={s}>{s}</option>)}
      </select>
      <select
        aria-label="시군구"
        value={region?.sigungu ?? ''}
        disabled={!region}
        onChange={(e) => region && setRegion({ sido: region.sido, sigungu: e.target.value || null })}
      >
        <option value="">{region ? '시군구 전체' : '시군구'}</option>
        {sigungus.map((s) => <option key={s} value={s}>{s}</option>)}
      </select>
      {region && (
        <button type="button" className="link-btn" onClick={() => setRegion(null)}>전체</button>
      )}
    </div>
  )
}
