import { useState } from 'react'
import type { AreaMetric } from '../lib/areaMetric'
import { ADD_THRESHOLD_S } from '../lib/points'
import { TIER_LABEL } from '../lib/recommend'
import { useAppState } from '../state/AppState'
import {
  ADD_SIZE,
  EXCLUDED_STROKE,
  GAP_RANGE_S,
  GAP_STOPS,
  LOW_SAMPLE_COLOR,
  MY_INPUT_STROKE,
  NO_VALUE_COLOR,
  TIER_COLORS,
} from './mapStyle'

interface Props {
  metric: AreaMetric
  minSample: number | null
  /** 서버에 전체 점이 아직 없어 후보 점만 그리는 중 */
  candidatesOnly: boolean
}

const GAP_GRADIENT = `linear-gradient(to right, ${GAP_STOPS.map(([v, c]) => `${c} ${((v + GAP_RANGE_S) / (2 * GAP_RANGE_S)) * 100}%`).join(', ')})`

/**
 * 지도 오른쪽 아래 고정 범례. 켜고 끄는 조작은 왼쪽 필터 패널에 두고, 여기는 색·모양의 뜻만 읽는다.
 * 단계 색은 색약 구분이 경계값(ΔE 7.6)이라 항상 글자 라벨과 함께 쓴다(dataviz 검증).
 */
export function MapLegend({ metric, minSample, candidatesOnly }: Props) {
  const { basis, target, layers } = useAppState()
  const v2 = basis === 'v2'
  // 좁은 화면에서는 지도를 가리지 않게 접힌 채로 시작한다
  const [open, setOpen] = useState(() => typeof window === 'undefined' || window.innerWidth > 900)

  return (
    <div className={open ? 'map-legend' : 'map-legend closed'} aria-label="범례">
      <button type="button" className="ml-head" aria-expanded={open} onClick={() => setOpen(!open)}>
        <span>범례</span>
        <span aria-hidden>{open ? '▾' : '▴'}</span>
      </button>
      {open && (
        <div className="ml-body">
          {layers.choropleth && (
            <section className="ml-section">
              <h3>읍면동 · {metric.legendTitle}{v2 && ` (목표 ${Math.round(target * 100)}%)`}</h3>
              <div className="ml-ramp">
                {metric.steps.map(([v, c]) => <span key={v} style={{ background: c }} title={`${metric.tick(v)} 이상`} />)}
              </div>
              <div className="ml-scale"><span>{metric.scale[0]}</span><span>{metric.scale[1]}</span></div>
              <div className="ml-row"><i className="sw hatch" style={{ backgroundColor: LOW_SAMPLE_COLOR }} />
                표본 부족 ({minSample ? `분석 ${minSample}곳 미만` : '표본 하한 미만'}, 순위 제외)</div>
              <div className="ml-row"><i className="sw" style={{ background: NO_VALUE_COLOR }} />값 없음</div>
            </section>
          )}

          {layers.points && (
            <section className="ml-section">
              {v2 ? (
                <>
                  <h3>횡단보도 · 적용 속도 단계</h3>
                  {([1, 2, 3] as const).map((t) => (
                    <div key={t} className="ml-row"><i className="dot" style={{ background: TIER_COLORS[t] }} />
                      {TIER_LABEL[t]}{t === 1 && ' · 0.7m/s'}</div>
                  ))}
                  <div className="ml-row">
                    <span className="ml-sizes" aria-hidden>
                      <i className="dot" style={{ width: ADD_SIZE.min * 2, height: ADD_SIZE.min * 2 }} />
                      <i className="dot" style={{ width: ADD_SIZE.max * 2, height: ADD_SIZE.max * 2 }} />
                    </span>
                    크기: 추가 초 (0 → {ADD_SIZE.maxS}초+)
                  </div>
                </>
              ) : (
                <>
                  <h3>횡단보도 · 짧은 초</h3>
                  <div className="ml-ramp" style={{ background: GAP_GRADIENT }} />
                  <div className="ml-scale"><span>여유 {GAP_RANGE_S}초+</span><span>0</span><span>짧음 {GAP_RANGE_S}초+</span></div>
                </>
              )}
            </section>
          )}

          {layers.points && (
            <section className="ml-section">
              <h3>테두리</h3>
              <div className="ml-row"><i className="dot ring" />굵은 테두리: {v2 ? `${ADD_THRESHOLD_S}초 이상 추가` : '점검 우선순위 후보'}</div>
              <div className="ml-row"><i className="dot ring" style={{ borderColor: MY_INPUT_STROKE }} />보라 테두리: 내 실측 입력(검토 전)</div>
              <div className="ml-row"><i className="dot ring hollow" style={{ borderColor: EXCLUDED_STROKE }} />속 빈 회색: 분석 제외{v2 && '·기록 확인'}</div>
              <p className="ml-note">숫자 원은 겹친 점 묶음(누르면 확대)</p>
            </section>
          )}
          {candidatesOnly && <p className="ml-note warn">전체 횡단보도 점이 아직 적재되지 않아 후보만 표시합니다.</p>}
        </div>
      )}
    </div>
  )
}
