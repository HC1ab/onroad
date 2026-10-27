import { useAppState } from '../state/AppState'
import { CANDIDATE_COLOR, LOW_SAMPLE_COLOR, NO_VALUE_COLOR, RATIO_STEPS } from './mapStyle'

/** 범례와 레이어 켜기/끄기 (F5) */
export function Legend({ candidateCount }: { candidateCount: number | null }) {
  const { layers, toggleLayer } = useAppState()
  return (
    <div className="legend" aria-label="범례와 레이어">
      <label className="legend-toggle">
        <input type="checkbox" checked={layers.choropleth} onChange={() => toggleLayer('choropleth')} />
        읍면동 채색
      </label>
      <div className="legend-title">기준식보다 짧은 횡단보도 비율</div>
      <div className="legend-bar">
        {RATIO_STEPS.map(([v, c]) => (
          <span key={v} style={{ background: c }} title={`${Math.round(v * 100)}% 이상`} />
        ))}
      </div>
      <div className="legend-scale">
        <span>0%</span>
        <span>40% 이상</span>
      </div>
      <div className="legend-row">
        <i className="sw hatch" style={{ backgroundColor: LOW_SAMPLE_COLOR }} /> 표본 부족 (순위 제외)
      </div>
      <div className="legend-row">
        <i className="sw" style={{ background: NO_VALUE_COLOR }} /> 값 없음
      </div>

      <label className="legend-toggle sep">
        <input type="checkbox" checked={layers.candidates} onChange={() => toggleLayer('candidates')} />
        <i className="dot" style={{ background: CANDIDATE_COLOR }} />
        후보 횡단보도{candidateCount !== null && layers.candidates ? ` ${candidateCount}곳` : ''}
      </label>
      <div className="legend-note">기준식보다 짧고 노출(경로당·시장·보호구역·사고다발)이 1개 이상</div>
    </div>
  )
}
