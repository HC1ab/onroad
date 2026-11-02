import { useState } from 'react'
import type { V1Result } from '../../api/types'
import { saveBlob } from '../../api/download'
import { meter, sec1 } from '../../lib/format'
import { greensCsv, measurementsCsv, myV1 } from '../../lib/userInputs'
import { useUserInputs } from '../../state/UserInputs'
import { Metric, ValidationCard } from './ValidationCard'
import { BASIS } from './basis'

const W = 420
const H = 170
const PAD = { left: 36, right: 10, top: 10, bottom: 26 }

const MINE_PENDING = '아직 입력한 실측이 없습니다. 지도에서 횡단보도를 누르고 실측 점등·점멸 시간을 입력하면 여기에 바로 반영됩니다.'

/** V1 현장 실측: 기록된 녹색신호시간과 실제(점등 + 점멸)의 차이. 공식 결과와 내 입력(검토 전)을 전환해 본다. */
export function V1Card({ v1: official }: { v1: V1Result | null }) {
  const [open, setOpen] = useState(false)
  const [mode, setMode] = useState<'official' | 'mine'>('official')
  const { inputs } = useUserInputs()
  const mine = myV1(inputs.measurements)
  const v1 = mode === 'official' ? official : mine.v1
  const download = (name: string, text: string) => saveBlob(new Blob([text], { type: 'text/csv;charset=utf-8' }), name)

  const tools = (
    <div className="seg small" role="radiogroup" aria-label="V1 결과 선택">
      {(['official', 'mine'] as const).map((m) => (
        <button key={m} type="button" role="radio" aria-checked={mode === m} className={mode === m ? 'seg-btn on' : 'seg-btn'} onClick={() => setMode(m)}>
          {m === 'official' ? '공식' : `내 입력 ${inputs.measurements.length}`}
        </button>
      ))}
    </div>
  )

  return (
    <ValidationCard
      id="v1"
      basis={BASIS.v1}
      tools={tools}
      title="V1 현장 실측"
      question="기록된 녹색신호시간이 실제와 맞는가, 점멸 시간이 포함되는가"
      caution={mode === 'official'
        ? '차이가 크면 녹색신호시간 필드의 의미가 달라져 전체 해석이 바뀝니다. 측정은 인도에서만 했습니다.'
        : '내 입력은 이 브라우저에만 저장된 검토 전 값이라 공식 결과가 아닙니다. CSV로 내보내 팀 검토를 거친 뒤 공식 V1에 반영합니다.'}
      ready={!!v1}
      pendingText={mode === 'mine' ? MINE_PENDING : undefined}
      notice={mode === 'mine' && (
        <div className="v-mine">
          <span className="badge mine">내 입력 · 검토 전</span>
          {mine.skipped > 0 && <span className="muted small">기록값이 없는 {mine.skipped}곳은 차이를 낼 수 없어 뺐습니다.</span>}
          <span className="v-mine-actions">
            <button type="button" className="link-btn" disabled={!inputs.measurements.length} onClick={() => download('my_measurements.csv', measurementsCsv(inputs.measurements))}>실측 CSV</button>
            <button type="button" className="link-btn" disabled={!Object.keys(inputs.greens).length} onClick={() => download('my_green_inputs.csv', greensCsv(inputs.greens))}>녹색시간 입력 CSV</button>
          </span>
        </div>
      )}
      metrics={v1 && (
        <>
          <Metric label="측정한 횡단보도" value={`${v1.n}곳`} />
          <Metric label="평균 차이 (기록 − 실측)" value={`${v1.mean_diff_s >= 0 ? '+' : '−'}${Math.abs(v1.mean_diff_s).toFixed(1)}초`} />
          <Metric label="기록값이 점멸 포함으로 보이는 곳" value={`${v1.flash_included_n} / ${v1.n}곳`} />
        </>
      )}
    >
      {v1 && <V1Figure v1={v1} />}
      {v1 && (
        <details className="v-details" open={open} onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}>
          <summary>측정 목록 {v1.points.length}건</summary>
          <table className="v-table">
            <thead><tr><th>연장</th><th>기록</th><th>실측 점등</th><th>실측 점멸</th><th>차이</th></tr></thead>
            <tbody>
              {v1.points.map((p) => (
                <tr key={p.cw_id}>
                  <td>{meter(p.length_m)}</td><td>{sec1(p.recorded_green_s)}</td><td>{sec1(p.measured_green_s)}</td>
                  <td>{sec1(p.measured_flash_s)}</td><td>{p.diff_s >= 0 ? '+' : '−'}{Math.abs(p.diff_s).toFixed(1)}초</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      )}
    </ValidationCard>
  )
}

function V1Figure({ v1 }: { v1: V1Result }) {
  const xs = v1.points.map((p) => p.length_m)
  const ds = v1.points.map((p) => p.diff_s)
  const xMax = Math.max(10, Math.ceil(Math.max(...xs, 0) / 10) * 10)
  const dAbs = Math.max(2, Math.ceil(Math.max(...ds.map(Math.abs), 0)))
  const sx = (v: number) => PAD.left + (v / xMax) * (W - PAD.left - PAD.right)
  const sy = (v: number) => PAD.top + ((dAbs - v) / (2 * dAbs)) * (H - PAD.top - PAD.bottom)
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="v-svg" role="img" aria-label={`연장별 기록값과 실측값 차이 산점도, ${v1.n}곳`}>
      <line x1={PAD.left} y1={sy(0)} x2={W - PAD.right} y2={sy(0)} className="v-zero" />
      <line x1={PAD.left} y1={PAD.top} x2={PAD.left} y2={H - PAD.bottom} className="q-axis" />
      <text x={PAD.left - 4} y={sy(dAbs) + 8} textAnchor="end" className="q-tick">+{dAbs}초</text>
      <text x={PAD.left - 4} y={sy(0) + 3} textAnchor="end" className="q-tick">0</text>
      <text x={PAD.left - 4} y={sy(-dAbs)} textAnchor="end" className="q-tick">−{dAbs}초</text>
      <text x={W - PAD.right} y={H - 6} textAnchor="end" className="q-label">연장(m) → 최대 {xMax}m</text>
      {v1.points.map((p) => (
        <circle key={p.cw_id} cx={sx(p.length_m)} cy={sy(p.diff_s)} r={4} className="v-dot">
          <title>{`${meter(p.length_m)} · 차이 ${p.diff_s.toFixed(1)}초`}</title>
        </circle>
      ))}
    </svg>
  )
}
