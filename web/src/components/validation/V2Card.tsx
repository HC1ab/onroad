import type { V2Result } from '../../api/types'
import { rho } from '../../lib/validation'
import { ValidationCard } from './ValidationCard'

/** V2 속도 민감도: 속도 가정을 바꾸면 읍면동 순위가 얼마나 흔들리는가 */
export function V2Card({ v2 }: { v2: V2Result | null }) {
  return (
    <ValidationCard
      id="v2"
      title="V2 속도 민감도"
      question="보행 속도 가정(1.0 / 0.8 / 0.7 m/s)을 바꾸면 우선순위가 흔들리는가"
      caution="상위 지역 중복이 낮으면 우선순위가 속도 가정에 크게 의존한다는 뜻입니다."
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
