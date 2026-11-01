import { useMemo, useState } from 'react'
import { api, API_MODE } from './api/client'
import { staticManifest } from './api/static'
import { AreaDetail } from './components/AreaDetail'
import { Legend } from './components/Legend'
import { LoadState } from './components/LoadState'
import { MapView, type Bbox } from './components/MapView'
import { PointCard } from './components/PointCard'
import { RegionFilter } from './components/RegionFilter'
import { QuadrantChart } from './components/QuadrantChart'
import { BasisSelector } from './components/BasisSelector'
import { Tabs } from './components/Tabs'
import { TopList } from './components/TopList'
import { useApi } from './hooks/useApi'
import { ADD_METRIC, RATIO_METRIC, v2AsAreas } from './lib/areaMetric'
import { countPoints, filterPoints } from './lib/points'
import { filterAreas } from './lib/region'
import { useRoute } from './lib/route'
import { AboutPage } from './pages/AboutPage'
import { ValidationPage } from './pages/ValidationPage'
import { AppStateProvider, useAppState } from './state/AppState'
import { UserInputsProvider, useUserInputs } from './state/UserInputs'

function Main() {
  const { basis, target, speed, layers, selectedAdmCd, region, radius, point, pointFilter } = useAppState()
  const { inputs } = useUserInputs()
  const route = useRoute()
  const onMap = route === 'map'
  const [bbox, setBbox] = useState<Bbox | null>(null)
  const boundaries = useApi((s) => api.boundaries(s), [])
  // 기준 전환(#80): 기록값은 속도별(v1), 3단계 기준은 목표 커버리지별(v2) 결과를 읽는다.
  const isV2 = basis === 'v2'
  const areas = useApi(
    (s) => (isV2 ? api.areasV2(target, radius, s).then(v2AsAreas) : api.areas(speed, radius, s)),
    [isV2, target, speed, radius],
  )
  const metric = isV2 ? ADD_METRIC : RATIO_METRIC
  // 횡단보도 점은 켜져 있고 지도 범위를 알 때만 요청한다. 지도를 움직이거나 속도·반경을 바꾸면 다시 요청.
  const bboxKey = bbox?.join(',') ?? ''
  const points = useApi(
    (s) => (layers.points && bbox ? (isV2 ? api.pointsV2(target, radius, bbox, s) : api.points(speed, radius, bbox, s)) : Promise.resolve(null)),
    [isV2, target, speed, radius, bboxKey, layers.points],
  )
  const meta = useApi((s) => api.meta(s), [])
  const bundle = useApi(() => (API_MODE === 'static' ? staticManifest() : Promise.resolve(null)), [])

  const selectedArea = areas.data?.items.find((a) => a.adm_cd === selectedAdmCd) ?? null
  // 지역 필터: 지도 색은 전국 그대로, 목록·사분면만 지역 안으로 좁힌다. 경계선은 전국 중앙값 유지.
  const scoped = useMemo(
    () => (areas.data ? { ...areas.data, items: filterAreas(areas.data.items, region) } : null),
    [areas.data, region],
  )
  // 점 필터(범위·짧은 초·분석 제외). 클러스터 개수와 범례 개수도 이 결과로 센다.
  const shownPoints = useMemo(() => (points.data ? filterPoints(points.data, pointFilter, isV2) : null), [points.data, pointFilter, isV2])
  const shownCount = useMemo(() => (shownPoints ? countPoints(shownPoints, isV2) : null), [shownPoints, isV2])
  // 서버에 전체 점이 없으면 후보 점으로 대신 그린다(연장이 없는 점만 있음).
  const candidatesOnly = !!points.data?.features.length && points.data.features.every((f) => f.properties.length_m === null)
  const myInputIds = useMemo(
    () => [...new Set([...Object.keys(inputs.greens), ...inputs.measurements.map((m) => m.cw_id)])],
    [inputs],
  )
  const minSample = areas.data?.min_sample ?? null
  const pointArea = point ? areas.data?.items.find((a) => a.adm_cd === point.props.adm_cd) : null

  // mock 이거나, 서버가 샘플을 적재해 내려준 경우(_sample) 모두 샘플임을 표시한다.
  const isSample = API_MODE === 'mock' || !!areas.data?._sample || !!meta.data?._sample || !!bundle.data?._sample

  const error = boundaries.error ?? areas.error ?? points.error
  const retry = () => {
    if (boundaries.error) boundaries.reload()
    if (areas.error) areas.reload()
    if (points.error) points.reload()
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
        {onMap && <BasisSelector />}
        <div className="badges">
          {API_MODE === 'static' && (
            <span className="badge offline" title="서버 없이 정적 묶음으로 보는 화면">
              오프라인 묶음{bundle.data ? ` · ${bundle.data.built_at.slice(0, 10)} 내보냄` : ''}
            </span>
          )}
          {isSample && (
            <span className="badge">{API_MODE === 'mock' ? '샘플 데이터 (mock)' : '샘플 데이터'} · 실제 분석 결과 아님</span>
          )}
        </div>
      </header>

      {/* 검증·About 화면에서도 지도는 지우지 않고 숨긴다(돌아왔을 때 위치·선택 유지). */}
      <main className={selectedArea ? 'body wide' : 'body'} hidden={!onMap}>
        <section className="map-wrap">
          <MapView
            boundaries={boundaries.data}
            areas={areas.data?.items ?? null}
            metric={metric}
            v2={isV2}
            minSample={minSample}
            points={layers.points ? shownPoints : null}
            myInputIds={myInputIds}
            onBoundsChange={setBbox}
            visible={onMap}
          />
          <Legend metric={metric} minSample={minSample} shown={shownCount} candidatesOnly={candidatesOnly} />
          {point && <PointCard key={point.cwId} areaName={pointArea ? `${pointArea.sigungu} ${pointArea.adm_name}` : null} />}
          <LoadState loading={boundaries.loading || areas.loading} error={error} onRetry={retry} />
        </section>
        {/* 지역을 고르면 오른쪽 패널을 넓혀 상세를 보여주고, 닫으면 사분면·상위 N 으로 돌아간다. */}
        <aside className="side">
          {selectedArea ? (
            <AreaDetail key={selectedArea.adm_cd} area={selectedArea} thresholdsData={areas.data} metric={metric} />
          ) : (
            <>
              {areas.error ? (
                <section className="card">
                  <h3>읍면동 결과 없음</h3>
                  <p className="muted">선택한 기준·반경의 결과를 불러오지 못했습니다. 지도 위 안내에서 다시 시도할 수 있습니다.</p>
                </section>
              ) : (
                <>
                  <QuadrantChart data={scoped} metric={metric} />
                  <TopList data={scoped} />
                </>
              )}
            </>
          )}
        </aside>
      </main>

      {route === 'validation' && (
        <main className="body-page">
          <ValidationPage meta={meta.data} />
        </main>
      )}
      {route === 'about' && (
        <main className="body-page">
          <AboutPage meta={meta.data} minSample={minSample} />
        </main>
      )}
    </div>
  )
}

export default function App() {
  return (
    <AppStateProvider>
      <UserInputsProvider>
        <Main />
      </UserInputsProvider>
    </AppStateProvider>
  )
}
