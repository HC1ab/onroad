import type { V6Result } from '../../api/types'
import { ValidationCard } from './ValidationCard'
import { BASIS } from './basis'

/** V6 지하철 무임 비율: 대형 시장 근처 이용자가 주민보다 고령인가 (2단계 보정 근거) */
export function V6Card({ v6 }: { v6: V6Result | null | undefined }) {
  return (
    <ValidationCard
      id="v6"
      basis={BASIS.v6}
      title="V6 지하철 무임 비율"
      question="대형 전통시장 근처 역은 주민 고령 비율을 감안해도 무임 승차가 많은가"
      caution="한계: 무임에는 장애인·국가유공자가 섞여 있고, 역 근처만 볼 수 있으며 대형 시장 근처 역이 몇 곳뿐입니다."
      ready={!!v6}
    >
      {v6 && (
        <dl className="v-metrics">
          <div><dt>잔차 차이</dt><dd><b>+{v6.diff_pp.toFixed(2)}%p</b></dd></div>
          <div><dt>단측 p (순열 {v6.n_permutations.toLocaleString()}회, 시드 {v6.seed})</dt><dd><b>{v6.p_value}</b></dd></div>
          <div><dt>역 수</dt><dd>전체 {v6.n_stations} · 대형 시장 300m 안 {v6.n_market_stations}</dd></div>
          <div><dt>시장 기준 보정 (고령 비율)</dt><dd>+{v6.uplift} (민감도 {v6.uplift_range.join('~')})</dd></div>
        </dl>
      )}
    </ValidationCard>
  )
}
