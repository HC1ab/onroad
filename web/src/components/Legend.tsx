import { useState } from 'react'
import { RADII } from '../api/types'
import type { AreaMetric } from '../lib/areaMetric'
import { ADD_THRESHOLD_S, type PointFilter } from '../lib/points'
import { TIER_LABEL, V2_COEF } from '../lib/recommend'
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
  /** 채색 지표 (기록값: 짧음 비율, 3단계 기준: 평균 추가 초) */
  metric: AreaMetric
  /** 표본 하한(응답의 min_sample). 없으면 null */
  minSample: number | null
  /** 필터를 적용한 뒤 지도에 보이는 점 수 */
  shown: { analyzed: number; candidates: number; excluded: number } | null
  /** 서버에 전체 점이 아직 없어 후보 점만 그리는 중 */
  candidatesOnly: boolean
}

const GAP_GRADIENT = `linear-gradient(to right, ${GAP_STOPS.map(([v, c]) => `${c} ${((v + GAP_RANGE_S) / (2 * GAP_RANGE_S)) * 100}%`).join(', ')})`

/** 범례와 레이어 켜기/끄기 (F5), 점 필터(피드백 2번), 노출 반경 (F11). 3단계 기준 화면은 단계 색·추가 초(#80·#81) */
export function Legend({ metric, minSample, shown, candidatesOnly }: Props) {
  const { basis, target, layers, toggleLayer, radius, setRadius, pointFilter: f, setPointFilter } = useAppState()
  const set = (patch: Partial<PointFilter>) => setPointFilter({ ...f, ...patch })
  const v2 = basis === 'v2'
  // 범례가 길어 지도를 가리므로 접을 수 있게 한다.
  const [open, setOpen] = useState(true)

  if (!open) {
    return (
      <div className="legend collapsed">
        <button type="button" className="legend-fold" aria-expanded={false} onClick={() => setOpen(true)}>범례·필터 펼치기 ▴</button>
      </div>
    )
  }

  const count = (n: number | undefined) => (shown && layers.points && n !== undefined ? ` ${n}곳` : '')

  return (
    <div className="legend" aria-label="범례와 레이어">
      <button type="button" className="legend-fold" aria-expanded onClick={() => setOpen(false)}>접기 ▾</button>
      <label className="legend-toggle">
        <input type="checkbox" checked={layers.choropleth} onChange={() => toggleLayer('choropleth')} />
        읍면동 채색
      </label>
      <div className="legend-title">
        {metric.legendTitle}
        {v2 && ` (목표 커버리지 ${Math.round(target * 100)}%)`}
      </div>
      <div className="legend-bar">
        {metric.steps.map(([v, c]) => (
          <span key={v} style={{ background: c }} title={`${metric.tick(v)} 이상`} />
        ))}
      </div>
      <div className="legend-scale">
        <span>{metric.scale[0]}</span>
        <span>{metric.scale[1]}</span>
      </div>
      <div className="legend-row">
        <i className="sw hatch" style={{ backgroundColor: LOW_SAMPLE_COLOR }} />
        표본 부족 (분석 횡단보도 {minSample ? `${minSample}곳 미만` : '표본 하한 미만'}, 순위 제외)
      </div>
      <div className="legend-row">
        <i className="sw" style={{ background: NO_VALUE_COLOR }} /> 값 없음
      </div>

      <label className="legend-toggle sep">
        <input type="checkbox" checked={layers.points} onChange={() => toggleLayer('points')} />
        횡단보도 점{count(shown?.analyzed)}
      </label>
      {v2 ? (
        <>
          <div className="legend-title">색: 적용 속도를 정한 단계</div>
          {([1, 2, 3] as const).map((t) => (
            <div key={t} className="legend-row">
              <i className="dot" style={{ background: TIER_COLORS[t] }} /> {TIER_LABEL[t]}
              {t === 1 && ' (0.7m/s)'}
            </div>
          ))}
          <div className="legend-row">
            <span className="legend-sizes" aria-hidden>
              <i className="dot" style={{ width: ADD_SIZE.min * 2, height: ADD_SIZE.min * 2 }} />
              <i className="dot" style={{ width: ADD_SIZE.max * 2, height: ADD_SIZE.max * 2 }} />
            </span>
            크기: 기준 적용 시 추가 초 (0초 → {ADD_SIZE.maxS}초 이상)
          </div>
          <div className="legend-row">
            <i className="dot ring" /> 굵은 테두리: {ADD_THRESHOLD_S}초 이상 추가{count(shown?.candidates)}
          </div>
        </>
      ) : (
        <>
          <div className="legend-title">짧은 초 (기준식 필요 시간 − 기록값)</div>
          <div className="legend-gradient" style={{ background: GAP_GRADIENT }} />
          <div className="legend-scale">
            <span>여유 {GAP_RANGE_S}초+</span>
            <span>0</span>
            <span>짧음 {GAP_RANGE_S}초+</span>
          </div>
          <div className="legend-row">
            <i className="dot ring" /> 굵은 테두리: 점검 우선순위 후보{count(shown?.candidates)}
          </div>
        </>
      )}
      <div className="legend-row">
        <i className="dot ring" style={{ borderColor: MY_INPUT_STROKE }} /> 보라 테두리: 내 입력(검토 전)
      </div>
      <div className="legend-note">
        숫자 원은 겹친 점 묶음(누르면 확대). 보행시간 정의(점멸 포함 여부) 확정 전 값입니다.
        {v2 && ` 2단계 시장 보정은 +${V2_COEF.marketUplift} (범위 ${V2_COEF.marketUpliftRange.join('~')}) 가정입니다.`}
      </div>
      {candidatesOnly && <div className="legend-note warn">전체 횡단보도 점이 아직 적재되지 않아 후보만 표시합니다.</div>}

      <div className="legend-filter" role="group" aria-label="횡단보도 점 필터">
        <div className="seg small" role="radiogroup" aria-label="점 범위">
          {(['all', 'candidates'] as const).map((s) => (
            <button key={s} type="button" role="radio" aria-checked={f.scope === s} className={f.scope === s ? 'seg-btn on' : 'seg-btn'} onClick={() => set({ scope: s })}>
              {s === 'all' ? '전체' : v2 ? `${ADD_THRESHOLD_S}초 이상 추가만` : '후보만'}
            </button>
          ))}
        </div>
        <label className="legend-gap">
          {v2 ? '추가 초' : '짧은 초'}
          <input
            type="number"
            step={1}
            value={f.gapValue}
            aria-label={v2 ? '추가 초 기준값' : '짧은 초 기준값'}
            onChange={(e) => set({ gapValue: Number(e.target.value) })}
          />
          초
          <select value={f.gapOp ?? ''} aria-label="조건" onChange={(e) => set({ gapOp: (e.target.value || null) as PointFilter['gapOp'] })}>
            <option value="">조건 없음</option>
            <option value="gte">이상</option>
            <option value="lte">이하</option>
          </select>
        </label>
        <label className="legend-toggle">
          <input type="checkbox" checked={f.showExcluded} onChange={() => set({ showExcluded: !f.showExcluded })} />
          <i className="dot ring" style={{ borderColor: EXCLUDED_STROKE }} />
          {v2 ? '분석 제외·기록 확인 점' : '분석 제외 점'}
          {f.showExcluded ? count(shown?.excluded) : ''}
        </label>
        <div className="legend-note">
          녹색신호시간·연장 기록이 없거나 정제 범위 밖이라 기준식과 비교하지 못한 횡단보도
          {v2 && '. 기록 확인: 기록값이 일반 기준식(1.0m/s)보다 짧아 기록 방식을 확인 중인 곳'}
        </div>
      </div>

      <div className="legend-title sep-title">노출 반경</div>
      <div className="seg" role="radiogroup" aria-label="노출 반경">
        {RADII.map((r) => (
          <button key={r} type="button" role="radio" aria-checked={r === radius} className={r === radius ? 'seg-btn on' : 'seg-btn'} onClick={() => setRadius(r)}>
            {r}m
          </button>
        ))}
      </div>
      <details className="legend-help">
        <summary>노출 반경이란?</summary>
        {v2 ? (
          <>
            <p>
              각 횡단보도에서 이 거리 안에 노인보호구역이 있으면 1단계(0.7m/s), 대형 전통시장(점포 200개 이상)이 있으면 2단계,
              둘 다 없으면 반경 안 주민 고령 비율로 3단계 속도를 정합니다.
            </p>
            <p>기본 300m는 보호구역을 시설 주 출입문 300m 안으로 지정하는 기준을 따랐습니다.</p>
            <p>반경을 바꾸면 단계·적용 속도·추가 초가 바뀝니다. 65세 이상 비율(세로축)은 그대로입니다.</p>
          </>
        ) : (
          <>
            <p>
              각 횡단보도에서 이 거리 안에 경로당·마을회관, 전통시장, 노인·장애인 보호구역, 노인 보행사고 다발지역(과거 연도)이
              하나라도 있으면 "노출"로 봅니다. 기록값이 기준식보다 짧으면서 노출이 있으면 점검 우선순위 후보입니다.
            </p>
            <p>
              기본 300m는 노인보호구역을 시설 출입문에서 300m(필요하면 500m) 안으로 지정하는 법령 기준을 따랐고, 200m는 범위를 좁혔을 때 결과가 얼마나 바뀌는지 보는 값입니다.
            </p>
            <p>반경을 바꾸면 후보 수·후보 표시·노출 플래그만 바뀝니다. 읍면동 채색과 사분면 두 축은 그대로입니다.</p>
          </>
        )}
      </details>
    </div>
  )
}
