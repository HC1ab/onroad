import { useEffect, useRef } from 'react'
import maplibregl, { type ExpressionSpecification, type LngLatBoundsLike } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import type { AreaItem, BoundariesResponse, PointsResponse } from '../api/types'
import type { AreaMetric } from '../lib/areaMetric'
import { regionBounds } from '../lib/region'
import { useAppState } from '../state/AppState'
import {
  CANDIDATE_STROKE,
  CLUSTER_STROKE,
  EXCLUDED_STROKE,
  GAP_STOPS,
  HATCH_LINE_COLOR,
  LOW_SAMPLE_COLOR,
  MY_INPUT_STROKE,
  NO_VALUE_COLOR,
  ADD_SIZE,
  POINT_STROKE,
  POINT_ADD_STEPS,
} from './mapStyle'

// 배경 지도: OpenFreeMap(키 없음). 출처 표기는 스타일이 자동으로 넣는다.
const BASEMAP_STYLE = import.meta.env.VITE_BASEMAP_STYLE || 'https://tiles.openfreemap.org/styles/positron'
const AREAS = 'areas'
const POINTS = 'points'
const HATCH = 'hatch'
// 하단 바 대신 지도 출처 표시에 데이터 출처를 남긴다(CC BY 4.0 표기 조건). 자세한 출처는 About.
const DATA_ATTRIBUTION = '읍면동 경계: admdongkor (CC BY 4.0) · 자료: 전국횡단보도표준데이터 외 · <a href="#/about">출처·한계</a>'
// 이 줌보다 가까우면 점을 묶지 않는다(상세 표에서 고른 점은 이보다 가깝게 이동)
const CLUSTER_MAX_ZOOM = 14

export type Bbox = [number, number, number, number]

// 표본 부족은 회색(+빗금 레이어), 값 없음은 연회색, 나머지는 지표(짧음 비율 또는 평균 추가 초) 단계 색
const fillColor = (steps: [number, string][]): ExpressionSpecification => [
  'case',
  ['boolean', ['feature-state', 'low_sample'], false],
  LOW_SAMPLE_COLOR,
  ['!=', ['typeof', ['feature-state', 'value']], 'number'],
  NO_VALUE_COLOR,
  ['step', ['number', ['feature-state', 'value'], 0], steps[0][1], ...steps.slice(1).flat()],
]

const gapColor = (value: ExpressionSpecification): ExpressionSpecification =>
  ['interpolate', ['linear'], value, ...GAP_STOPS.flat()] as ExpressionSpecification

const MINE: ExpressionSpecification = ['boolean', ['get', 'mine'], false]

/** 점 색·크기·테두리. 일괄 속도 비교: 짧은 초 발산 색, 후보 굵은 테두리. 상황별 기준: 추가 초 순차 색·크기 */
function pointPaint(v2: boolean): Record<string, unknown> {
  if (!v2) {
    const cand: ExpressionSpecification = ['boolean', ['get', 'is_candidate'], false]
    return {
      'circle-color': gapColor(['to-number', ['get', 'gap_s']]),
      'circle-radius': ['case', cand, 6, 4.5],
      'circle-stroke-color': ['case', MINE, MY_INPUT_STROKE, cand, CANDIDATE_STROKE, POINT_STROKE],
      'circle-stroke-width': ['case', ['any', MINE, cand], 2, 0.8],
    }
  }
  const add: ExpressionSpecification = ['to-number', ['coalesce', ['get', 'add_s'], 0]]
  const big: ExpressionSpecification = ['>=', add, 2]
  return {
    'circle-color': ['step', add, POINT_ADD_STEPS[0][1], ...POINT_ADD_STEPS.slice(1).flat()],
    'circle-radius': ['interpolate', ['linear'], add, 0, ADD_SIZE.min, ADD_SIZE.maxS, ADD_SIZE.max],
    // 연한 점이 연한 주황 채색 위에서도 보이게 기본 테두리를 회색으로
    'circle-stroke-color': ['case', MINE, MY_INPUT_STROKE, big, CANDIDATE_STROKE, POINT_STROKE],
    'circle-stroke-width': ['case', ['any', MINE, big], 1.8, 0.8],
  }
}

/** 묶음 색: 묶인 점 중 가장 큰 값(기록값: 짧은 초, 3단계: 추가 초) */
const clusterColor = (v2: boolean): ExpressionSpecification =>
  v2
    ? ['case', ['==', ['get', 'n_analyzed'], 0], 'rgba(255,255,255,0.6)', ['step', ['get', 'max_add'], POINT_ADD_STEPS[0][1], ...POINT_ADD_STEPS.slice(1).flat()]] as ExpressionSpecification
    : ['case', ['==', ['get', 'n_analyzed'], 0], 'rgba(255,255,255,0.6)', gapColor(['get', 'max_gap'])]

const EMPTY: GeoJSON.FeatureCollection = { type: 'FeatureCollection', features: [] }

interface Props {
  boundaries: BoundariesResponse | null
  areas: AreaItem[] | null
  /** 채색 지표 (기록값: 짧음 비율, 3단계 기준: 평균 추가 초) */
  metric: AreaMetric
  /** 3단계 기준 화면이면 점을 단계 색·추가 초 크기로 그린다 */
  v2: boolean
  /** 표본 하한(응답의 min_sample). 없으면 null */
  minSample: number | null
  /** 필터를 적용한 횡단보도 점 */
  points: PointsResponse | null
  /** 내가 실측·녹색시간을 입력한 횡단보도 */
  myInputIds: string[]
  onBoundsChange: (bbox: Bbox) => void
  /** 숨겨졌다가 다시 보일 때 지도 크기를 다시 맞춘다 */
  visible: boolean
}

function boundsOf(fc: BoundariesResponse): LngLatBoundsLike {
  let [minX, minY, maxX, maxY] = [180, 90, -180, -90]
  const visit = (c: unknown): void => {
    if (Array.isArray(c) && typeof c[0] === 'number') {
      const [x, y] = c as number[]
      minX = Math.min(minX, x); minY = Math.min(minY, y); maxX = Math.max(maxX, x); maxY = Math.max(maxY, y)
    } else if (Array.isArray(c)) c.forEach(visit)
  }
  fc.features.forEach((f) => visit(f.geometry.coordinates))
  return [[minX, minY], [maxX, maxY]]
}

/** 대각선 빗금 무늬(표본 부족 표시). 외부 이미지 없이 캔버스로 만든다. */
function hatchImage(size = 8): ImageData {
  const c = document.createElement('canvas')
  c.width = c.height = size
  const g = c.getContext('2d')!
  g.strokeStyle = HATCH_LINE_COLOR
  g.lineWidth = 1.5
  g.beginPath()
  g.moveTo(0, size); g.lineTo(size, 0)
  g.moveTo(-size / 2, size / 2); g.lineTo(size / 2, -size / 2)
  g.moveTo(size / 2, size * 1.5); g.lineTo(size * 1.5, size / 2)
  g.stroke()
  return g.getImageData(0, 0, size, size)
}

const esc = (s: string) => s.replace(/[&<>"]/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[ch]!)

function currentBbox(map: maplibregl.Map): Bbox {
  const b = map.getBounds()
  const r = (v: number) => Math.round(v * 1000) / 1000
  return [r(b.getWest()), r(b.getSouth()), r(b.getEast()), r(b.getNorth())]
}

export function MapView({ boundaries, areas, metric, v2, minSample, points, myInputIds, onBoundsChange, visible }: Props) {
  const container = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const readyRef = useRef(false)
  const boundsCb = useRef(onBoundsChange)
  boundsCb.current = onBoundsChange
  const minSampleRef = useRef(minSample)
  minSampleRef.current = minSample
  const v2Ref = useRef(v2)
  v2Ref.current = v2
  const metricRef = useRef(metric)
  metricRef.current = metric
  const { selection, select, layers, point, setPoint, region } = useAppState()
  const regionInit = useRef(true)
  // 지도 이벤트 안에서 최신 점 데이터를 찾는다(지도 속성은 중첩 객체를 문자열로 바꾸므로 원래 값을 쓴다).
  const pointsById = useRef(new Map<string, GeoJSON.Feature<GeoJSON.Point, PointsResponse['features'][number]['properties']>>())
  const actions = useRef({ select, setPoint })
  actions.current = { select, setPoint }

  // 레이어가 준비된 뒤 실행 (준비 전이면 준비 이벤트를 기다린다)
  const whenLayers = (fn: (map: maplibregl.Map) => void) => {
    const map = mapRef.current
    if (!map) return
    if (map.getSource(AREAS)) fn(map)
    else map.once('onroad:layers', () => fn(map))
  }

  // 지도 생성(한 번)
  useEffect(() => {
    if (!container.current) return
    const map = new maplibregl.Map({
      container: container.current,
      style: BASEMAP_STYLE,
      center: [129.13, 35.17],
      zoom: 11,
      attributionControl: { customAttribution: DATA_ATTRIBUTION, compact: false },
    })
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
    map.on('load', () => {
      if (!map.hasImage(HATCH)) map.addImage(HATCH, hatchImage())
      readyRef.current = true
      map.fire('onroad:ready')
    })
    map.on('moveend', () => boundsCb.current(currentBbox(map)))
    mapRef.current = map
    return () => {
      readyRef.current = false
      map.remove()
      mapRef.current = null
    }
  }, [])

  // 경계·횡단보도 점 레이어 (경계를 받은 뒤 한 번)
  useEffect(() => {
    const map = mapRef.current
    if (!map || !boundaries) return
    const add = () => {
      if (map.getSource(AREAS)) return
      map.addSource(AREAS, { type: 'geojson', data: boundaries, promoteId: 'adm_cd' })
      map.addLayer({ id: 'areas-fill', type: 'fill', source: AREAS, paint: { 'fill-color': fillColor(metricRef.current.steps), 'fill-opacity': 0.8 } })
      map.addLayer({
        id: 'areas-hatch', type: 'fill', source: AREAS,
        filter: ['in', ['get', 'adm_cd'], ['literal', []]],
        paint: { 'fill-pattern': HATCH, 'fill-opacity': 0.9 },
      })
      map.addLayer({ id: 'areas-line', type: 'line', source: AREAS, paint: { 'line-color': '#ffffff', 'line-width': 1 } })
      map.addLayer({
        id: 'areas-selected', type: 'line', source: AREAS,
        filter: ['==', ['get', 'adm_cd'], ''],
        paint: { 'line-color': '#111827', 'line-width': 3 },
      })

      // 횡단보도 점: 많이 겹치면 묶는다(피드백 3번). 묶음 색은 묶인 점 중 가장 짧은 쪽(최대 짧은 초).
      map.addSource(POINTS, {
        type: 'geojson',
        data: EMPTY,
        cluster: true,
        clusterMaxZoom: CLUSTER_MAX_ZOOM,
        clusterRadius: 36,
        clusterProperties: {
          max_gap: ['max', ['case', ['==', ['get', 'status'], 'analyzed'], ['to-number', ['get', 'gap_s']], -999]],
          max_add: ['max', ['case', ['==', ['get', 'status'], 'analyzed'], ['to-number', ['coalesce', ['get', 'add_s'], 0]], -999]],
          n_analyzed: ['+', ['case', ['==', ['get', 'status'], 'analyzed'], 1, 0]],
        },
      })
      map.addLayer({
        id: 'points-cluster', type: 'circle', source: POINTS,
        filter: ['has', 'point_count'],
        paint: {
          'circle-color': clusterColor(v2Ref.current),
          'circle-stroke-color': CLUSTER_STROKE,
          'circle-stroke-width': 2,
          'circle-radius': ['step', ['get', 'point_count'], 12, 10, 15, 50, 19, 200, 24],
          'circle-opacity': 0.9,
        },
      })
      map.addLayer({
        id: 'points-count', type: 'symbol', source: POINTS,
        filter: ['has', 'point_count'],
        layout: { 'text-field': ['get', 'point_count_abbreviated'], 'text-size': 11, 'text-font': ['Noto Sans Regular'] },
        paint: { 'text-color': '#111827', 'text-halo-color': '#ffffff', 'text-halo-width': 1.2 },
      })
      map.addLayer({
        id: 'points-excluded', type: 'circle', source: POINTS,
        filter: ['all', ['!', ['has', 'point_count']], ['!=', ['get', 'status'], 'analyzed']],
        paint: {
          'circle-color': 'rgba(0,0,0,0)',
          'circle-radius': 5,
          'circle-stroke-color': ['case', ['boolean', ['get', 'mine'], false], MY_INPUT_STROKE, EXCLUDED_STROKE],
          'circle-stroke-width': ['case', ['boolean', ['get', 'mine'], false], 2.5, 1.5],
        },
      })
      map.addLayer({
        id: 'points-analyzed', type: 'circle', source: POINTS,
        filter: ['all', ['!', ['has', 'point_count']], ['==', ['get', 'status'], 'analyzed']],
        paint: pointPaint(v2Ref.current) as maplibregl.CircleLayerSpecification['paint'],
      })
      map.addLayer({
        id: 'points-selected', type: 'circle', source: POINTS,
        filter: ['==', ['get', 'cw_id'], ''],
        paint: { 'circle-color': 'rgba(0,0,0,0)', 'circle-radius': 10, 'circle-stroke-color': '#111827', 'circle-stroke-width': 2.5 },
      })

      // 읍면동: 클릭 선택, 마우스 올림 안내
      const hover = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 12, className: 'map-tip' })
      map.on('click', 'areas-fill', (e) => {
        // 점을 누른 경우는 점 처리에 맡긴다.
        if (map.queryRenderedFeatures(e.point, { layers: ['points-analyzed', 'points-excluded', 'points-cluster'] }).length) return
        const adm = e.features?.[0]?.properties?.adm_cd as string | undefined
        if (adm) actions.current.select(adm, 'map')
      })
      map.on('mousemove', 'areas-fill', (e) => {
        const f = e.features?.[0]
        if (!f) return
        map.getCanvas().style.cursor = 'pointer'
        const name = esc(String(f.properties?.adm_name ?? ''))
        const st = f.state as { value?: number | null; n_add2?: number; low_sample?: boolean; n_analyzed?: number }
        const min = minSampleRef.current
        const value = st.low_sample
          ? `표본 부족 · 분석 ${st.n_analyzed ?? 0}곳${min ? ` (${min}곳 미만)` : ''} · 순위 제외`
          : metricRef.current.tooltip({ value: st.value ?? null, n_add2: st.n_add2 })
        hover.setLngLat(e.lngLat).setHTML(`<b>${name}</b><br>${value}`).addTo(map)
      })
      map.on('mouseleave', 'areas-fill', () => {
        map.getCanvas().style.cursor = ''
        hover.remove()
      })

      // 묶음: 누르면 풀리는 줌까지 확대
      map.on('click', 'points-cluster', async (e) => {
        const f = e.features?.[0]
        if (!f) return
        const zoom = await (map.getSource(POINTS) as maplibregl.GeoJSONSource).getClusterExpansionZoom(f.properties?.cluster_id as number)
        map.easeTo({ center: (f.geometry as GeoJSON.Point).coordinates as [number, number], zoom })
      })
      // 점: 누르면 정보 카드(피드백 11번)와 그 동의 상세를 연다.
      const onPoint = (e: maplibregl.MapLayerMouseEvent) => {
        const id = e.features?.[0]?.properties?.cw_id as string | undefined
        const f = id ? pointsById.current.get(id) : undefined
        if (!f) return
        const [lon, lat] = f.geometry.coordinates
        actions.current.select(f.properties.adm_cd, 'map')
        actions.current.setPoint({ cwId: f.properties.cw_id, lon, lat, props: f.properties, source: 'map' })
      }
      for (const id of ['points-analyzed', 'points-excluded', 'points-cluster']) {
        if (id !== 'points-cluster') map.on('click', id, onPoint)
        map.on('mouseenter', id, () => { map.getCanvas().style.cursor = 'pointer' })
        map.on('mouseleave', id, () => { map.getCanvas().style.cursor = '' })
      }

      map.fitBounds(boundsOf(boundaries), { padding: 40, duration: 0 })
      boundsCb.current(currentBbox(map))
      map.fire('onroad:layers')
    }
    if (readyRef.current) add()
    else map.once('onroad:ready', add)
  }, [boundaries])

  // 값 → feature-state (속도를 바꾸면 경계는 그대로 두고 값만 바꾼다)
  // 표본 부족 빗금은 패턴이 feature-state 를 못 쓰므로 adm_cd 목록 필터로 건다.
  useEffect(() => {
    whenLayers((map) => {
      map.removeFeatureState({ source: AREAS })
      // 값이 없으면(불러오기 실패 등) 이전 색을 남기지 않고 '값 없음'으로 둔다.
      if (!areas) {
        map.setFilter('areas-hatch', ['in', ['get', 'adm_cd'], ['literal', []]])
        return
      }
      for (const a of areas) {
        map.setFeatureState({ source: AREAS, id: a.adm_cd }, { value: metric.value(a), n_add2: a.n_add2, low_sample: a.low_sample, n_analyzed: a.n_analyzed })
      }
      const low = areas.filter((a) => a.low_sample).map((a) => a.adm_cd)
      map.setFilter('areas-hatch', ['in', ['get', 'adm_cd'], ['literal', low]])
      map.setPaintProperty('areas-fill', 'fill-color', fillColor(metric.steps))
    })
  }, [areas, metric])

  // 기준 전환: 점·묶음 색을 바꾼다
  useEffect(() => {
    whenLayers((map) => {
      for (const [k, v] of Object.entries(pointPaint(v2))) map.setPaintProperty('points-analyzed', k, v)
      map.setPaintProperty('points-cluster', 'circle-color', clusterColor(v2))
    })
  }, [v2])

  // 횡단보도 점 데이터 (내 입력 표시를 속성으로 붙인다)
  useEffect(() => {
    const mine = new Set(myInputIds)
    const byId = new Map<string, GeoJSON.Feature<GeoJSON.Point, PointsResponse['features'][number]['properties']>>()
    const data: GeoJSON.FeatureCollection = points
      ? {
          type: 'FeatureCollection',
          features: points.features.map((f) => {
            byId.set(f.properties.cw_id, f)
            return { ...f, properties: { ...f.properties, mine: mine.has(f.properties.cw_id) } }
          }),
        }
      : EMPTY
    pointsById.current = byId
    whenLayers((map) => (map.getSource(POINTS) as maplibregl.GeoJSONSource).setData(data))
  }, [points, myInputIds])

  // 레이어 켜기/끄기
  useEffect(() => {
    whenLayers((map) => {
      const vis = (on: boolean) => (on ? 'visible' : 'none')
      map.setLayoutProperty('areas-fill', 'visibility', vis(layers.choropleth))
      map.setLayoutProperty('areas-hatch', 'visibility', vis(layers.choropleth))
      for (const id of ['points-cluster', 'points-count', 'points-analyzed', 'points-excluded', 'points-selected']) {
        map.setLayoutProperty(id, 'visibility', vis(layers.points))
      }
    })
  }, [layers])

  // 선택 강조. 사분면·목록에서 고르면 그 읍면동으로 지도를 옮긴다(지도에서 고르면 그대로).
  useEffect(() => {
    whenLayers((map) => {
      map.setFilter('areas-selected', ['==', ['get', 'adm_cd'], selection?.admCd ?? ''])
      if (!selection || selection.source === 'map' || !boundaries) return
      const f = boundaries.features.find((x) => x.properties.adm_cd === selection.admCd)
      if (!f) return
      // 지도 영역이 작을 때(좁은 화면) 여백이 지도보다 커지지 않게 한다.
      const { clientWidth: w, clientHeight: h } = map.getContainer()
      const padding = Math.max(10, Math.min(80, w / 5, h / 5))
      map.fitBounds(boundsOf({ type: 'FeatureCollection', features: [f] }), { padding, maxZoom: 14, duration: 600 })
    })
  }, [selection, boundaries])

  // 지역 필터: 고르면 그 지역 전체가 보이게, 전국으로 돌리면 전체가 보이게 이동 (첫 렌더는 경계 추가 때 이미 맞춤)
  useEffect(() => {
    if (regionInit.current) {
      regionInit.current = false
      return
    }
    if (!boundaries) return
    whenLayers((map) => {
      const b = regionBounds(boundaries, region)
      if (!b) return
      const { clientWidth: w, clientHeight: h } = map.getContainer()
      map.fitBounds(b, { padding: Math.max(10, Math.min(60, w / 6, h / 6)), duration: 600 })
    })
  }, [region, boundaries])

  // 숨김(검증 화면)에서 돌아오면 크기를 다시 맞춘다. 숨겨진 동안 크기가 0이었기 때문.
  useEffect(() => {
    if (visible) mapRef.current?.resize()
  }, [visible])

  // 선택한 횡단보도: 강조하고, 상세 표에서 골랐으면 그 위치로 이동(묶음이 풀리는 줌까지)
  useEffect(() => {
    whenLayers((map) => {
      map.setFilter('points-selected', ['==', ['get', 'cw_id'], point?.cwId ?? ''])
      if (point?.source === 'list') {
        map.flyTo({ center: [point.lon, point.lat], zoom: Math.max(map.getZoom(), CLUSTER_MAX_ZOOM + 2), duration: 600 })
      }
    })
  }, [point])

  return <div ref={container} className="map" aria-label="읍면동 지도" />
}
