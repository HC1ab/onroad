import { SPEEDS, type Speed } from '../api/types'
import { useAppState } from '../state/AppState'

const LABEL: Record<Speed, string> = { 0.7: '노인', 0.8: '보행약자', 1.0: '일반' }

export function SpeedSelector() {
  const { speed, setSpeed } = useAppState()
  return (
    <div className="speed" role="radiogroup" aria-label="보행 속도 기준">
      <span className="speed-title">속도 기준</span>
      {SPEEDS.map((s) => (
        <button
          key={s}
          type="button"
          role="radio"
          aria-checked={s === speed}
          className={s === speed ? 'speed-btn on' : 'speed-btn'}
          onClick={() => setSpeed(s)}
        >
          <b>{s.toFixed(1)} m/s</b>
          <small>{LABEL[s]}</small>
        </button>
      ))}
    </div>
  )
}
