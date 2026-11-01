import type { V2Result } from '../../api/types'
import { rho } from '../../lib/validation'
import { ValidationCard } from './ValidationCard'
import { BASIS } from './basis'

/** V2 속도 민감도: 속도 가정을 바꾸면 읍면동 순위가 얼마나 흔들리는가 */
export function V2Card({ v2 }: { v2: V2Result | null }) {
  return (
    <ValidationCard
      id="v2"
      basis={BASIS.v2}
      title="V2 속도 민감도"
      question="보행 속도 가정(1.0 / 0.8 / 0.7 m/s)을 바꾸면 우선순위가 흔들리는가"
      caution="한계: 속도 3종을 모든 횡단보도에 똑같이 적용한 비교입니다. 지도 화면의 3단계 기준은 횡단보도마다 속도를 다르게 정합니다(결정 009). 상위 지역 중복이 낮으면 우선순위가 속도 가정에 크게 의존한다는 뜻입니다."
      notice={<p className="muted small">속도 3종 일괄 비교 지도는 상단 기준을 &quot;기록값&quot;으로 바꾸고 속도를 골라 볼 수 있습니다.</p>}
      ready={!!v2}
    >
      {v2 && (
        <table className="v-table v2">
          <thead>
            <tr><th>비교</th><th>순위 상관 (Spearman)</th><th>상위 {v2.top_n}곳 중복</th></tr>
          </thead>
          <tbody>
            {v2.pairs.map((p) => (
              <tr key={`${p.a}-${p.b}`}>
                <td>{p.a.toFixed(1)} ↔ {p.b.toFixed(1)} m/s</td>
                <td><b>{rho(p.spearman)}</b></td>
                <td>
                  <span className="v-overlap"><span style={{ width: `${(p.top_n_overlap / v2.top_n) * 100}%` }} /></span>
                  <b>{p.top_n_overlap}</b> / {v2.top_n}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </ValidationCard>
  )
}
