import { LOW_SAMPLE_COLOR, RATIO_STEPS } from './mapStyle'

export function Legend() {
  return (
    <div className="legend" aria-label="범례">
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
      <div className="legend-row"><i className="sw" style={{ background: LOW_SAMPLE_COLOR }} /> 표본 부족 (순위 제외)</div>
    </div>
  )
}
