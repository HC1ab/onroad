import { useMemo } from 'react'
import type { PointsResponse } from '../api/types'
import { ADD_THRESHOLD_S } from '../lib/points'
import { useAppState } from '../state/AppState'

/** 오른쪽 패널 기본 상태 맨 위: 핵심 수치 3개와 사용 안내. 횡단보도를 고르면 상세(CrosswalkDetail)로 바뀐다. */
export function Overview({ points }: { points: PointsResponse | null }) {
  const { basis, target } = useAppState()
  const s = useMemo(() => {
    if (!points) return null
    const analyzed = points.features.filter((f) => f.properties.status === 'analyzed' && f.properties.add_s != null)
    const added = analyzed.filter((f) => (f.properties.add_s ?? 0) > 0)
    return {
      analyzed: analyzed.length,
      over: analyzed.filter((f) => (f.properties.add_s ?? 0) >= ADD_THRESHOLD_S).length,
      meanAdd: added.length ? added.reduce((a, f) => a + (f.properties.add_s ?? 0), 0) / added.length : 0,
    }
  }, [points])

  return (
    <section className="overview" aria-label="개요">
      <p className="ov-hint">지도에서 횡단보도를 누르면 여기에 상세 수치와 분석 요약이 나옵니다.</p>
      {basis === 'v2' && s && (
        <dl className="tiles three">
          <div className="tile"><dt>분석 횡단보도</dt><dd>{s.analyzed.toLocaleString()}<small>곳</small></dd></div>
          <div className="tile"><dt>{ADD_THRESHOLD_S}초 이상 추가</dt><dd>{s.over.toLocaleString()}<small>곳</small></dd></div>
          <div className="tile"><dt title="추가 시간이 생기는 곳의 평균">평균 추가</dt><dd>{s.meanAdd.toFixed(1)}<small>초</small></dd></div>
        </dl>
      )}
      {basis === 'v2' && <p className="muted small">목표 커버리지 {Math.round(target * 100)}% 기준 · 보행시간 정의(점멸 포함 여부) 확정 전</p>}
    </section>
  )
}
