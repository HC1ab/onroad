import { useMemo, useState } from 'react'
import { api, API_MODE } from './api/client'
import { AreaDetail } from './components/AreaDetail'
import { Footer } from './components/Footer'
import { Legend } from './components/Legend'
import { LoadState } from './components/LoadState'
import { MapView, type Bbox } from './components/MapView'
import { RegionFilter } from './components/RegionFilter'
import { QuadrantChart } from './components/QuadrantChart'
import { SpeedSelector } from './components/SpeedSelector'
import { Tabs } from './components/Tabs'
import { TopList } from './components/TopList'
import { useApi } from './hooks/useApi'
import { filterAreas } from './lib/region'
import { useRoute } from './lib/route'
import { ValidationPage } from './pages/ValidationPage'
import { AppStateProvider, useAppState } from './state/AppState'

function Main() {
  const { speed, layers, selectedAdmCd, region, radius } = useAppState()
  const route = useRoute()
  const onMap = route === 'map'
  const [bbox, setBbox] = useState<Bbox | null>(null)
  const boundaries = useApi((s) => api.boundaries(s), [])
  const areas = useApi((s) => api.areas(speed, radius, s), [speed, radius])
  // 후보 점은 켜져 있고 지도 범위를 알 때만 요청한다. 지도를 움직이거나 속도를 바꾸면 다시 요청.
  const bboxKey = bbox?.join(',') ?? ''
  const candidates = useApi(
    (s) => (layers.candidates && bbox ? api.candidates(speed, radius, bbox, s) : Promise.resolve(null)),
    [speed, radius, bboxKey, layers.candidates],
  )
  const meta = useApi((s) => api.meta(s), [])

  const selectedArea = areas.data?.items.find((a) => a.adm_cd === selectedAdmCd) ?? null
  // 지역 필터: 지도 색은 전국 그대로, 목록·사분면만 지역 안으로 좁힌다. 경계선은 전국 중앙값 유지.
  const scoped = useMemo(
    () => (areas.data ? { ...areas.data, items: filterAreas(areas.data.items, region) } : null),
    [areas.data, region],
  )

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
        <Tabs route={route} />
        {onMap && <RegionFilter boundaries={boundaries.data} />}
        {onMap && <SpeedSelector />}
        {API_MODE === 'mock' && <span className="badge">샘플 데이터 (mock) · 실제 분석 결과 아님</span>}
      </header>

      {/* 검증 화면에서도 지도는 지우지 않고 숨긴다(돌아왔을 때 위치·선택 유지). */}
      <main className={selectedArea ? "body wide" : "body"} hidden={!onMap}>
        <section className="map-wrap">
          <MapView
            boundaries={boundaries.data}
            areas={areas.data?.items ?? null}
            candidates={layers.candidates ? candidates.data : null}
            onBoundsChange={setBbox}
            visible={onMap}
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
              <QuadrantChart data={scoped} />
              <TopList data={scoped} />
            </>
          )}
        </aside>
      </main>

      {!onMap && (
        <main className="body-page">
          <ValidationPage meta={meta.data} />
        </main>
      )}

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
