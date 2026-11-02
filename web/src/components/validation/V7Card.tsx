import type { V7Result } from '../../api/types'
import { pct1 } from '../../lib/format'
import { ValidationCard } from './ValidationCard'
import { BASIS } from './basis'

const GROUP_LABEL = { child_zone: '어린이보호구역', senior_zone: '노인보호구역', outside: '둘 다 밖' } as const

/** V7 0.7식 적용률: 보호구역별로 기록값이 0.7m/s 기준식과 같은 비율 */
export function V7Card({ v7 }: { v7: V7Result | null | undefined }) {
  const max = v7 ? Math.max(0.01, ...v7.groups.map((g) => (g.n ? g.n_formula_07 / g.n : 0))) : 1
  return (
    <ValidationCard
      id="v7"
      basis={BASIS.v7}
      title="V7 0.7식 적용률"
      question="보호구역 안 횡단보도는 이미 0.7m/s 기준식으로 맞춰져 있는가"
      caution="한계: 허용오차 안에서 같은 값만 셉니다. 기록 보행시간 정의(점멸 포함 여부) 확정 전이라 비율이 달라질 수 있습니다."
      ready={!!v7}
    >
      {v7 && (
        <table className="v-table">
          <thead>
            <tr><th>구역</th><th>0.7식 비율</th><th>대상</th></tr>
          </thead>
          <tbody>
            {v7.groups.map((g) => {
              const r = g.n ? g.n_formula_07 / g.n : 0
              return (
                <tr key={g.group}>
                  <td>{GROUP_LABEL[g.group]}{g.radius_m ? ` ${g.radius_m}m` : ''}</td>
                  <td>
                    <span className="v-overlap"><span style={{ width: `${(r / max) * 100}%` }} /></span>
                    <b>{pct1(r)}</b>
                  </td>
                  <td>{g.n_formula_07.toLocaleString()} / {g.n.toLocaleString()}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
    </ValidationCard>
  )
}
