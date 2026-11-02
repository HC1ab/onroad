import { useState, type FormEvent } from 'react'
import { meter, sec1 } from '../../lib/format'
import { gapWithGreen } from '../../lib/points'
import { ROUTE_HASH } from '../../lib/route'
import { averageByCrosswalk, checkSeconds, INPUT_LIMITS } from '../../lib/userInputs'
import { useAppState } from '../../state/AppState'
import { useUserInputs } from '../../state/UserInputs'

const nowLocal = () => {
  const d = new Date()
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset())
  return d.toISOString().slice(0, 16)
}

/**
 * 현장 실측·녹색신호시간 입력(피드백 13~15번). 지도 화면에서 분리해 검증 탭에 둔다.
 * 지도에서 고른 횡단보도(AppState.point)를 대상으로 하고, 결과는 아래 V1 "내 입력"에 바로 반영된다.
 */
export function MeasureInput() {
  const { point, speed } = useAppState()
  const { inputs, setGreen, removeGreen, addMeasurement, removeMeasurement } = useUserInputs()
  const [greenText, setGreenText] = useState('')
  const [measured, setMeasured] = useState({ green: '', flash: '0', at: nowLocal() })
  const [error, setError] = useState<string | null>(null)

  if (!point) {
    return (
      <section className="card measure" aria-label="현장 실측 입력">
        <h3>현장 실측 입력</h3>
        <p className="muted">
          지도에서 횡단보도를 누른 뒤 이 탭으로 오면 그 횡단보도의 실측 점등·점멸 시간을 입력할 수 있습니다.{' '}
          <a href={ROUTE_HASH.map}>지도로 가기</a>
        </p>
      </section>
    )
  }

  const p = point.props
  const myGreen = inputs.greens[p.cw_id]
  const myMeasures = inputs.measurements.filter((m) => m.cw_id === p.cw_id)
  const avg = myMeasures.length ? averageByCrosswalk(myMeasures)[0] : null
  const canInputGreen = p.green_s === null && p.length_m !== null

  const saveGreen = (e: FormEvent) => {
    e.preventDefault()
    const v = Number(greenText)
    const err = checkSeconds(v, INPUT_LIMITS.greenMax, '녹색신호시간')
    setError(err)
    if (err || p.length_m === null) return
    setGreen({ cw_id: p.cw_id, adm_cd: p.adm_cd, length_m: p.length_m, green_s: v, saved_at: new Date().toISOString() })
    setGreenText('')
  }

  const saveMeasure = (e: FormEvent) => {
    e.preventDefault()
    const g = Number(measured.green)
    const fl = Number(measured.flash)
    const err = checkSeconds(g, INPUT_LIMITS.greenMax, '실측 점등 시간') ?? checkSeconds(fl, INPUT_LIMITS.flashMax, '실측 점멸 시간', true)
    setError(err)
    if (err) return
    addMeasurement({
      cw_id: p.cw_id, adm_cd: p.adm_cd, lon: point.lon, lat: point.lat, length_m: p.length_m,
      recorded_green_s: p.green_s ?? myGreen?.green_s ?? null,
      measured_green_s: g, measured_flash_s: fl, measured_at: measured.at,
    })
    setMeasured({ green: '', flash: '0', at: nowLocal() })
  }

  return (
    <section className="card measure" aria-label="현장 실측 입력">
      <div className="card-head">
        <h3>현장 실측 입력</h3>
        <span className="badge mine">이 브라우저에만 저장 · 검토 전</span>
      </div>
      <p className="muted small">
        대상: <b>{p.cw_id}</b>{p.length_m !== null && ` · 연장 ${meter(p.length_m)}`} · 기록 녹색신호시간 {sec1(p.green_s)}
      </p>

      <div className="measure-forms">
        {canInputGreen && (
          <form onSubmit={saveGreen} className="point-form">
            <label>
              녹색신호시간
              <input type="number" step="0.1" min="0" value={greenText} onChange={(e) => setGreenText(e.target.value)} placeholder="초" />
            </label>
            <button type="submit">저장</button>
          </form>
        )}
        <form onSubmit={saveMeasure} className="point-form">
          <label>
            실측 점등
            <input type="number" step="0.1" min="0" value={measured.green} onChange={(e) => setMeasured({ ...measured, green: e.target.value })} placeholder="초" />
          </label>
          <label>
            점멸
            <input type="number" step="0.1" min="0" value={measured.flash} onChange={(e) => setMeasured({ ...measured, flash: e.target.value })} />
          </label>
          <label>
            측정 일시
            <input type="datetime-local" value={measured.at} onChange={(e) => setMeasured({ ...measured, at: e.target.value })} />
          </label>
          <button type="submit">실측 저장</button>
        </form>
      </div>
      {error && <p className="download-error" role="alert">{error}</p>}

      {myGreen && p.length_m !== null && (
        <p className="point-mine">
          입력 녹색신호시간 {sec1(myGreen.green_s)} → 기준식({speed.toFixed(1)}m/s)보다 {gapWithGreen(p.length_m, myGreen.green_s, speed).gap_s.toFixed(1)}초
          <button type="button" className="link-btn" onClick={() => removeGreen(p.cw_id)}>삭제</button>
        </p>
      )}
      {avg && avg.recorded_green_s !== null && (
        <p className="point-mine">
          실측 평균 점등 {sec1(avg.measured_green_s)} · 점멸 {sec1(avg.measured_flash_s)} ({avg.count}회) →
          기록값이 실측보다 {Math.abs(avg.recorded_green_s - avg.measured_green_s).toFixed(1)}초 {avg.recorded_green_s >= avg.measured_green_s ? '김' : '짧음'}
        </p>
      )}
      {myMeasures.length > 0 && (
        <ul className="point-measures">
          {myMeasures.map((m) => (
            <li key={m.id}>
              {m.measured_at.replace('T', ' ')} · 점등 {sec1(m.measured_green_s)} · 점멸 {sec1(m.measured_flash_s)}
              <button type="button" className="link-btn" onClick={() => removeMeasurement(m.id)}>삭제</button>
            </li>
          ))}
        </ul>
      )}
      <p className="muted small">아래 V1 카드의 "내 입력"에 바로 반영되고, 그곳에서 CSV로 내보낼 수 있습니다. 사진은 받지 않습니다.</p>
    </section>
  )
}
