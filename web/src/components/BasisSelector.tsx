import { TARGETS } from '../api/types'
import { useAppState } from '../state/AppState'
import { SpeedSelector } from './SpeedSelector'

/** 상단 기준 전환(#80): 기록값(속도별 기준식) / 3단계 기준(목표 커버리지) */
export function BasisSelector() {
  const { basis, setBasis, target, setTarget } = useAppState()
  return (
    <div className="basis">
      <div className="seg" role="radiogroup" aria-label="화면 기준">
        <button type="button" role="radio" aria-checked={basis === 'recorded'} className={basis === 'recorded' ? 'seg-btn on' : 'seg-btn'} onClick={() => setBasis('recorded')}>
          일괄 속도 비교
        </button>
        <button type="button" role="radio" aria-checked={basis === 'v2'} className={basis === 'v2' ? 'seg-btn on' : 'seg-btn'} onClick={() => setBasis('v2')}>
          상황별 기준
        </button>
      </div>
      {basis === 'recorded' ? (
        <SpeedSelector />
      ) : (
        <div className="speed" role="radiogroup" aria-label="목표 커버리지">
          <span className="speed-title" title="고령 보행자 중 이 비율이 시간 안에 건너도록 맞춘 기준 (정답 확률 아님)">목표 커버리지</span>
          <span className="seg-group">
          {TARGETS.map((t) => (
            <button key={t} type="button" role="radio" aria-checked={t === target} className={t === target ? 'speed-btn on' : 'speed-btn'} onClick={() => setTarget(t)}>
              <b>{Math.round(t * 100)}%</b>
              <small>{t === 0.85 ? '기본' : '민감도'}</small>
            </button>
          ))}
          </span>
        </div>
      )}
    </div>
  )
}
