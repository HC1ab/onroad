import { useState } from 'react'
import { api, API_MODE } from './api/client'
import { AreaDetail } from './components/AreaDetail'
import { Footer } from './components/Footer'
import { Legend } from './components/Legend'
import { LoadState } from './components/LoadState'
import { MapView, type Bbox } from './components/MapView'
import { QuadrantChart } from './components/QuadrantChart'
import { SpeedSelector } from './components/SpeedSelector'
import { TopList } from './components/TopList'
import { useApi } from './hooks/useApi'
import { AppStateProvider, useAppState } from './state/AppState'

function Main() {
  const { speed, layers, selectedAdmCd } = useAppState()
  const [bbox, setBbox] = useState<Bbox | null>(null)
  const boundaries = useApi((s) => api.boundaries(s), [])
  const areas = useApi((s) => api.areas(speed, s), [speed])
  // 후보 점은 켜져 있고 지도 범위를 알 때만 요청한다. 지도를 움직이거나 속도를 바꾸면 다시 요청.
  const bboxKey = bbox?.join(',') ?? ''
  const candidates = useApi(
    (s) => (layers.candidates && bbox ? api.candidates(speed, bbox, s) : Promise.resolve(null)),
    [speed, bboxKey, layers.candidates],
  )
  const meta = useApi((s) => api.meta(s), [])

  const selectedArea = areas.data?.items.find((a) => a.adm_cd === selectedAdmCd) ?? null

  const error = boundaries.error ?? areas.error ?? candidates.error
  const retry = () => {
    if (boundaries.error) boundaries.reload()
    if (areas.error) areas.reload()
    if (candidates.error) candidates.reload()
  }

  return (
    <div className="app">
      <header className="header">
        <div className="brand">
          <h1>한 박자</h1>
          <span className="muted">점검 우선순위 후보 지도</span>
        </div>
        <SpeedSelector />
        {API_MODE === 'mock' && <span className="badge">샘플 데이터 (mock) · 실제 분석 결과 아님</span>}
      </header>

      <main className={selectedArea ? "body wide" : "body"}>
        <section className="map-wrap">
          <MapView
            boundaries={boundaries.data}
            areas={areas.data?.items ?? null}
            candidates={layers.candidates ? candidates.data : null}
            onBoundsChange={setBbox}
          />
          <Legend candidateCount={candidates.data?.features.length ?? null} />
          <LoadState loading={boundaries.loading || areas.loading} error={error} onRetry={retry} />
        </section>
        {/* 지역을 고르면 오른쪽 패널을 넓혀 상세를 보여주고, 닫으면 사분면·상위 N 으로 돌아간다. */}
        <aside className="side">
          {selectedArea ? (
            <AreaDetail key={selectedArea.adm_cd} area={selectedArea} thresholdsData={areas.data} />
          ) : (
            <>
              <QuadrantChart data={areas.data} />
              <TopList data={areas.data} />
            </>
          )}
        </aside>
      </main>

      <Footer meta={meta.data} />
    </div>
  )
}

export default function App() {
  return (
    <AppStateProvider>
      <Main />
    </AppStateProvider>
  )
}
