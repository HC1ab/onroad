import type { AreaItem } from '../api/types'
import { useAppState } from '../state/AppState'

const pct = (v: number | null) => (v === null ? '—' : `${(v * 100).toFixed(1)}%`)

/** 선택한 읍면동의 요약. 상세 패널(F7)은 W5(#21)에서 이 자리를 확장한다. */
export function AreaSummary({ areas }: { areas: AreaItem[] | null }) {
  const { selectedAdmCd } = useAppState()
  const a = areas?.find((x) => x.adm_cd === selectedAdmCd)
  if (!a) return <p className="muted">지도에서 읍면동을 누르면 요약이 여기에 나옵니다.</p>
  return (
    <div className="summary">
      <h2>{a.adm_name}</h2>
      <p className="muted">{a.sido} {a.sigungu}</p>
      <dl>
        <dt>분석 횡단보도</dt><dd>{a.n_analyzed}곳</dd>
        <dt>기준식보다 짧음</dt><dd>{a.n_short}곳 · {pct(a.short_ratio)}</dd>
        <dt>65세 이상 비율</dt><dd>{pct(a.ratio_65plus)}</dd>
        <dt>점검 우선순위 후보</dt><dd>{a.n_candidate}곳</dd>
      </dl>
      {a.low_sample && <p className="note">표본이 적어 순위에서 제외되는 지역입니다.</p>}
    </div>
  )
}
