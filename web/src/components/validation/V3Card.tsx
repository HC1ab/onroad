import type { V3Result } from '../../api/types'
import { pct1 } from '../../lib/format'
import { histogram, pValue } from '../../lib/validation'
import { Metric, ValidationCard } from './ValidationCard'

const W = 420
const H = 170
const PAD = { left: 10, right: 10, top: 18, bottom: 26 }

/** V3 사고다발지역 연관성(연도 분할): 후보가 최근 노인 보행사고 다발지역과 겹치는가 */
export function V3Card({ v3 }: { v3: V3Result | null }) {
  return (
    <ValidationCard
      id="v3"
      title="V3 사고다발지역 연관성 (연도 분할)"
      question="점검 우선순위 후보가 최근 연도 노인 보행사고 다발지역과 겹치는가"
      caution="겹침이 높아도 인과는 아닙니다(보행량·도로 규모 등). 낮게 나와도 그대로 보고합니다."
      ready={!!v3}
      metrics={v3 && (
        <>
          <Metric label="겹침 비율" value={pct1(v3.overlap_ratio)} sub={`최근 연도 ${v3.recent_years.join('·')}`} />
          <Metric label="무작위 대비" value={`${v3.ratio_vs_random.toFixed(1)}배`} sub={`무작위 ${v3.n_permutations.toLocaleString()}회`} />
          <Metric label="p값" value={pValue(v3.p_value)} sub={`속도 기준 ${v3.speed.toFixed(1)} m/s`} />
        </>
      )}
    >
      {v3 && <V3Figure v3={v3} />}
    </ValidationCard>
  )
}

function V3Figure({ v3 }: { v3: V3Result }) {
  const bins = histogram(v3.random_distribution, 12, v3.overlap_ratio)
  if (bins.length === 0) return null
  const lo = bins[0].x0
  const hi = bins[bins.length - 1].x1
  const maxC = Math.max(...bins.map((b) => b.count), 1)
  const pw = W - PAD.left - PAD.right
  const ph = H - PAD.top - PAD.bottom
  const sx = (v: number) => PAD.left + ((v - lo) / (hi - lo)) * pw
  const ox = sx(v3.overlap_ratio)
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="v-svg" role="img" aria-label={`무작위 추출 겹침 비율 분포와 관측 겹침 ${pct1(v3.overlap_ratio)}`}>
      {bins.map((b, i) => {
        const h = (b.count / maxC) * ph
        return <rect key={i} x={sx(b.x0) + 1} y={PAD.top + ph - h} width={Math.max(1, sx(b.x1) - sx(b.x0) - 2)} height={h} className="v-bar" />
      })}
      <line x1={PAD.left} y1={PAD.top + ph} x2={W - PAD.right} y2={PAD.top + ph} className="q-axis" />
      <line x1={ox} y1={PAD.top - 6} x2={ox} y2={PAD.top + ph} className="v-observed" />
      <text x={ox} y={PAD.top - 8} textAnchor={ox > W - 80 ? 'end' : 'middle'} className="v-observed-label">관측 {pct1(v3.overlap_ratio)}</text>
      <text x={PAD.left} y={H - 6} className="q-tick">{pct1(lo)}</text>
      <text x={W - PAD.right} y={H - 6} textAnchor="end" className="q-tick">{pct1(hi)}</text>
      <text x={W / 2} y={H - 6} textAnchor="middle" className="q-label">무작위 추출 겹침 비율 (같은 시군구·연장 구간)</text>
    </svg>
  )
}
