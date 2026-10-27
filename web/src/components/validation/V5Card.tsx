import type { V5Result } from '../../api/types'
import { ValidationCard } from './ValidationCard'

const n2 = (v: number) => `${v < 0 ? '−' : ''}${Math.abs(v).toFixed(2)}`

/** V5 (선택) 보정 연관성: 로지스틱 회귀 */
export function V5Card({ v5 }: { v5: V5Result | null }) {
  return (
    <ValidationCard
      id="v5"
      title="V5 (선택) 보정 연관성 · 로지스틱 회귀"
      question="다른 요인(65세 이상 비율, 평균 연장, 시도)을 통제해도 짧음 비율과 사고다발지역이 함께 움직이는가"
      caution="통제한 연관성까지입니다. 보행량 데이터가 없어 인과는 아닙니다."
      ready={!!v5}
      pendingText="선택 항목이며 아직 수행하지 않았습니다."
    >
      {v5 && (
        <table className="v-table">
          <thead><tr><th>변수</th><th>계수</th><th>95% 신뢰구간</th></tr></thead>
          <tbody>
            {v5.coefficients.map((c) => (
              <tr key={c.term}><td>{c.term}</td><td>{n2(c.estimate)}</td><td>{n2(c.ci_low)} ~ {n2(c.ci_high)}</td></tr>
            ))}
          </tbody>
        </table>
      )}
    </ValidationCard>
  )
}
