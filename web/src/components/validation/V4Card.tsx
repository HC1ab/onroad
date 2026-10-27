import type { FacilityKind, V4Result } from '../../api/types'
import { pct1 } from '../../lib/format'
import { rho } from '../../lib/validation'
import { Metric, ValidationCard } from './ValidationCard'

const FACILITY: Record<FacilityKind, string> = {
  senior_center: '경로당',
  market: '전통시장',
  protect_zone: '보호구역',
}

/** V4 축 독립성 · 이미 조정됐는가 */
export function V4Card({ v4 }: { v4: V4Result | null }) {
  const max = v4 ? Math.max(0.01, ...v4.inside_outside.flatMap((r) => [r.inside_short_ratio, r.outside_short_ratio])) : 1
  return (
    <ValidationCard
      id="v4"
      title="V4 축 독립성 · 이미 조정됐는가"
      question="짧음 비율이 고령 거주 비율·목적지 노출과 어떤 관계인가"
      caution="음의 상관은 이미 조정됐을 가능성, 양의 상관은 지역 효과가 섞였을 가능성을 뜻합니다. 사분면 오른쪽 위 칸이 비어 있어도 그 자체가 결과입니다."
      ready={!!v4}
      metrics={v4 && (
        <Metric label="짧음 비율 × 65세 이상 비율 순위 상관" value={rho(v4.spearman)} sub={`속도 기준 ${v4.speed.toFixed(1)} m/s`} />
      )}
    >
      {v4 && (
        <div className="v4">
          <div className="v4-bars" role="img" aria-label="시설 반경 안과 밖의 짧음 비율 비교">
            <div className="v4-legend muted"><i className="in" /> 반경 안 <i className="out" /> 반경 밖</div>
            {v4.inside_outside.map((r) => (
              <div key={r.facility} className="v4-row">
                <span className="v4-name">{FACILITY[r.facility]}</span>
                <span className="v4-pair">
                  <span className="v4-bar in" style={{ width: `${(r.inside_short_ratio / max) * 100}%` }}>{pct1(r.inside_short_ratio)}</span>
                  <span className="v4-bar out" style={{ width: `${(r.outside_short_ratio / max) * 100}%` }}>{pct1(r.outside_short_ratio)}</span>
                </span>
              </div>
            ))}
          </div>
          <table className="v-table">
            <thead><tr><th>구분</th><th>순위 상관</th><th>읍면동 수</th></tr></thead>
            <tbody>
              {v4.by_group.map((g) => (
                <tr key={g.group}><td>{g.group}</td><td>{rho(g.spearman)}</td><td>{g.n.toLocaleString()}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </ValidationCard>
  )
}
