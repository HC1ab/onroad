import { useState, type FormEvent } from 'react'
import type { ExposureFlags } from '../api/types'
import { meter, sec1 } from '../lib/format'
import { EXCLUDE_REASON_LABEL, gapWithGreen, needSeconds } from '../lib/points'
import { averageByCrosswalk, checkSeconds, INPUT_LIMITS } from '../lib/userInputs'
import { useAppState } from '../state/AppState'
import { useUserInputs } from '../state/UserInputs'

const FLAG_LABEL: { key: keyof ExposureFlags; label: string }[] = [
  { key: 'senior_center', label: '경로당·마을회관' },
  { key: 'market', label: '전통시장' },
  { key: 'protect_zone', label: '노인·장애인 보호구역' },
  { key: 'crash_zone_past', label: '노인 보행사고 다발지역(과거 연도)' },
]

/** 기록값과 기준식 비교 문구. 양수면 기록값이 기준식보다 짧다. */
function gapText(gap: number) {
  if (gap > 0) return `기록값이 기준식보다 ${gap.toFixed(1)}초 짧음`
  if (gap < 0) return `기록값이 기준식보다 ${Math.abs(gap).toFixed(1)}초 여유`
  return '기록값이 기준식과 같음'
}

const nowLocal = () => {
  const d = new Date()
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset())
  return d.toISOString().slice(0, 16)
}

/** 선택한 횡단보도 정보(피드백 11번)와 사용자 입력(13~15번). 지도 위에 띄운다. */
export function PointCard({ areaName }: { areaName: string | null }) {
  const { point, setPoint, speed } = useAppState()
  const { inputs, setGreen, removeGreen, addMeasurement, removeMeasurement } = useUserInputs()
  const [greenText, setGreenText] = useState('')
  const [measured, setMeasured] = useState({ green: '', flash: '0', at: nowLocal() })
  const [error, setError] = useState<string | null>(null)
  if (!point) return null
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
    <section className="point-card" aria-label="선택한 횡단보도">
      <div className="point-card-head">
        <h3>횡단보도 정보</h3>
        <button type="button" className="close-btn" aria-label="횡단보도 정보 닫기" onClick={() => setPoint(null)}>✕</button>
      </div>
      <p className="muted small">{areaName ?? p.adm_cd} · {p.status === 'excluded' ? '분석 제외' : p.is_candidate ? '점검 우선순위 후보' : '분석함'}</p>

      {p.status === 'excluded' ? (
        <p className="note warn">분석 제외 · {p.exclude_reason ? EXCLUDE_REASON_LABEL[p.exclude_reason] : '사유 미상'}</p>
      ) : p.gap_s !== null && <p className={p.gap_s > 0 ? 'point-gap pos' : 'point-gap'}>{gapText(p.gap_s)}</p>}

      <dl className="point-stats">
        <div><dt>연장</dt><dd>{p.length_m !== null ? meter(p.length_m) : '—'}</dd></div>
        <div><dt>기록 녹색신호시간</dt><dd>{sec1(p.green_s)}</dd></div>
        <div>
          <dt>기준식 필요 시간</dt>
          <dd>{sec1(p.t_need_s ?? (p.length_m !== null ? needSeconds(p.length_m, speed) : null))}</dd>
        </div>
        <div><dt>노출</dt><dd>{p.flags ? `${p.exposure_cnt}개` : p.status === 'excluded' ? '—' : `${p.exposure_cnt}개`}</dd></div>
      </dl>
      <p className="muted small">필요 시간 = 7초 + 연장 ÷ {speed.toFixed(1)} m/s (선택한 보행 속도). 녹색신호시간 정의(점멸 포함 여부) 확정 전.</p>
      {p.flags ? (
        <ul className="point-flags">
          {FLAG_LABEL.map((f) => (
            <li key={f.key} className={p.flags?.[f.key] ? 'on' : undefined}>{p.flags?.[f.key] ? '●' : '○'} {f.label}</li>
          ))}
        </ul>
      ) : p.status === 'analyzed' && p.length_m === null ? (
        <p className="muted small">전체 횡단보도 점이 적재되면 연장·기록값·노출 종류가 표시됩니다.</p>
      ) : null}

      <div className="point-input">
        <h4>내 입력 <span className="muted small">(이 브라우저에만 저장 · 검토 전)</span></h4>

        {canInputGreen && (
          <form onSubmit={saveGreen} className="point-form">
            <label>
              녹색신호시간
              <input type="number" step="0.1" min="0" value={greenText} onChange={(e) => setGreenText(e.target.value)} placeholder="초" />
            </label>
            <button type="submit">저장</button>
          </form>
        )}
        {myGreen && p.length_m !== null && (
          <p className="point-mine">
            입력 {sec1(myGreen.green_s)} → {gapText(gapWithGreen(p.length_m, myGreen.green_s, speed).gap_s)} (내 입력 기준)
            <button type="button" className="link-btn" onClick={() => removeGreen(p.cw_id)}>삭제</button>
          </p>
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
          <label className="wide">
            측정 일시
            <input type="datetime-local" value={measured.at} onChange={(e) => setMeasured({ ...measured, at: e.target.value })} />
          </label>
          <button type="submit">실측 저장</button>
        </form>
        {error && <p className="download-error" role="alert">{error}</p>}

        {myMeasures.length > 0 && (
          <>
            {avg && avg.recorded_green_s !== null && (
              <p className="point-mine">
                실측 평균 점등 {sec1(avg.measured_green_s)} · 점멸 {sec1(avg.measured_flash_s)} ({avg.count}회) →
                기록값이 실측보다 {Math.abs(avg.recorded_green_s - avg.measured_green_s).toFixed(1)}초 {avg.recorded_green_s >= avg.measured_green_s ? '김' : '짧음'}
              </p>
            )}
            <ul className="point-measures">
              {myMeasures.map((m) => (
                <li key={m.id}>
                  {m.measured_at.replace('T', ' ')} · 점등 {sec1(m.measured_green_s)} · 점멸 {sec1(m.measured_flash_s)}
                  <button type="button" className="link-btn" onClick={() => removeMeasurement(m.id)}>삭제</button>
                </li>
              ))}
            </ul>
          </>
        )}
        <p className="muted small">실측은 검증 화면 V1의 "내 입력"에 바로 반영되고, 그곳에서 CSV로 내보낼 수 있습니다. 사진은 받지 않습니다.</p>
      </div>
    </section>
  )
}
