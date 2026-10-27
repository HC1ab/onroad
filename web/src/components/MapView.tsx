import { useEffect, useRef } from 'react'
import maplibregl, { type ExpressionSpecification, type LngLatBoundsLike } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import type { AreaItem, BoundariesResponse, CandidatesResponse } from '../api/types'
import { regionBounds } from '../lib/region'
import { useAppState } from '../state/AppState'
import {
  CANDIDATE_COLOR,
  CANDIDATE_STROKE,
  HATCH_LINE_COLOR,
  LOW_SAMPLE_COLOR,
  NO_VALUE_COLOR,
  RATIO_STEPS,
} from './mapStyle'

// 배경 지도: OpenFreeMap(키 없음). 출처 표기는 스타일이 자동으로 넣는다.
const BASEMAP_STYLE = import.meta.env.VITE_BASEMAP_STYLE || 'https://tiles.openfreemap.org/styles/positron'
const AREAS = 'areas'
const CANDIDATES = 'candidates'
const HATCH = 'hatch'

export type Bbox = [number, number, number, number]

// 표본 부족은 회색(+빗금 레이어), 값 없음은 연회색, 나머지는 짧음 비율 단계 색
const FILL_COLOR: ExpressionSpecification = [
  'case',
  ['boolean', ['feature-state', 'low_sample'], false],
  LOW_SAMPLE_COLOR,
  ['==', ['feature-state', 'short_ratio'], null],
  NO_VALUE_COLOR,
  ['step', ['to-number', ['coalesce', ['feature-state', 'short_ratio'], 0]], RATIO_STEPS[0][1], ...RATIO_STEPS.slice(1).flat()],
]

const EMPTY: GeoJSON.FeatureCollection = { type: 'FeatureCollection', features: [] }

interface Props {
  boundaries: BoundariesResponse | null
  areas: AreaItem[] | null
  candidates: CandidatesResponse | null
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

const pct = (v: unknown) => (typeof v === 'number' ? `${(v * 100).toFixed(1)}%` : '값 없음')
const esc = (s: string) => s.replace(/[&<>"]/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[ch]!)

function currentBbox(map: maplibregl.Map): Bbox {
  const b = map.getBounds()
  const r = (v: number) => Math.round(v * 1000) / 1000
  return [r(b.getWest()), r(b.getSouth()), r(b.getEast()), r(b.getNorth())]
}

export function MapView({ boundaries, areas, candidates, onBoundsChange, visible }: Props) {
  const container = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const readyRef = useRef(false)
  const pointPopup = useRef<maplibregl.Popup | null>(null)
  const focusPopup = useRef<maplibregl.Popup | null>(null)
  const boundsCb = useRef(onBoundsChange)
  boundsCb.current = onBoundsChange
  const { selection, select, layers, focus, region } = useAppState()
  const regionInit = useRef(true)

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
      attributionControl: { customAttribution: '읍면동 경계: admdongkor (CC BY 4.0)' },
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

  // 경계·후보 점 레이어 (경계를 받은 뒤 한 번)
  useEffect(() => {
    const map = mapRef.current
    if (!map || !boundaries) return
    const add = () => {
      if (map.getSource(AREAS)) return
      map.addSource(AREAS, { type: 'geojson', data: boundaries, promoteId: 'adm_cd' })
      map.addLayer({ id: 'areas-fill', type: 'fill', source: AREAS, paint: { 'fill-color': FILL_COLOR, 'fill-opacity': 0.8 } })
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

      map.addSource(CANDIDATES, { type: 'geojson', data: EMPTY })
      map.addLayer({
        id: 'candidates-pt', type: 'circle', source: CANDIDATES,
        paint: {
          'circle-color': CANDIDATE_COLOR,
          'circle-stroke-color': CANDIDATE_STROKE,
          'circle-stroke-width': 1.5,
          // 노출 개수가 많을수록 조금 크게
          'circle-radius': ['interpolate', ['linear'], ['get', 'exposure_cnt'], 1, 4, 4, 7],
        },
      })

      // 읍면동: 클릭 선택, 마우스 올림 안내
      const hover = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 12, className: 'map-tip' })
      map.on('click', 'areas-fill', (e) => {
        const adm = e.features?.[0]?.properties?.adm_cd as string | undefined
        if (adm) select(adm, 'map')
      })
      map.on('mousemove', 'areas-fill', (e) => {
        const f = e.features?.[0]
        if (!f) return
        map.getCanvas().style.cursor = 'pointer'
        const name = esc(String(f.properties?.adm_name ?? ''))
        const st = f.state as { short_ratio?: number | null; low_sample?: boolean }
        const value = st.low_sample ? '표본 부족 (순위 제외)' : `기준식보다 짧음 ${pct(st.short_ratio)}`
        hover.setLngLat(e.lngLat).setHTML(`<b>${name}</b><br>${value}`).addTo(map)
      })
      map.on('mouseleave', 'areas-fill', () => {
        map.getCanvas().style.cursor = ''
        hover.remove()
      })

      // 후보 점: 클릭하면 짧은 초와 노출 개수
      map.on('click', 'candidates-pt', (e) => {
        const p = e.features?.[0]?.properties as { gap_s?: number; exposure_cnt?: number } | undefined
        if (!p) return
        pointPopup.current?.remove()
        pointPopup.current = new maplibregl.Popup({ offset: 8, className: 'map-tip' })
          .setLngLat(e.lngLat)
          .setHTML(`<b>점검 우선순위 후보</b><br>기준식보다 ${Number(p.gap_s).toFixed(1)}초 짧음<br>노출 ${p.exposure_cnt}개`)
          .addTo(map)
      })
      map.on('mouseenter', 'candidates-pt', () => { map.getCanvas().style.cursor = 'pointer' })
      map.on('mouseleave', 'candidates-pt', () => { map.getCanvas().style.cursor = '' })

      map.fitBounds(boundsOf(boundaries), { padding: 40, duration: 0 })
      boundsCb.current(currentBbox(map))
      map.fire('onroad:layers')
    }
    if (readyRef.current) add()
    else map.once('onroad:ready', add)
  }, [boundaries, select])

  // 값 → feature-state (속도를 바꾸면 경계는 그대로 두고 값만 바꾼다)
  // 표본 부족 빗금은 패턴이 feature-state 를 못 쓰므로 adm_cd 목록 필터로 건다.
  useEffect(() => {
    if (!areas) return
    whenLayers((map) => {
      map.removeFeatureState({ source: AREAS })
      for (const a of areas) {
        map.setFeatureState({ source: AREAS, id: a.adm_cd }, { short_ratio: a.short_ratio, low_sample: a.low_sample })
      }
      const low = areas.filter((a) => a.low_sample).map((a) => a.adm_cd)
      map.setFilter('areas-hatch', ['in', ['get', 'adm_cd'], ['literal', low]])
    })
  }, [areas])

  // 후보 점 데이터
  useEffect(() => {
    whenLayers((map) => (map.getSource(CANDIDATES) as maplibregl.GeoJSONSource).setData(candidates ?? EMPTY))
  }, [candidates])

  // 레이어 켜기/끄기
  useEffect(() => {
    whenLayers((map) => {
      const vis = (on: boolean) => (on ? 'visible' : 'none')
      map.setLayoutProperty('areas-fill', 'visibility', vis(layers.choropleth))
      map.setLayoutProperty('areas-hatch', 'visibility', vis(layers.choropleth))
      map.setLayoutProperty('candidates-pt', 'visibility', vis(layers.candidates))
      if (!layers.candidates) pointPopup.current?.remove()
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

  // 상세 표에서 고른 횡단보도로 이동해 표시한다.
  useEffect(() => {
    focusPopup.current?.remove()
    focusPopup.current = null
    if (!focus) return
    whenLayers((map) => {
      map.flyTo({ center: [focus.lon, focus.lat], zoom: Math.max(map.getZoom(), 16), duration: 600 })
      focusPopup.current = new maplibregl.Popup({ offset: 10, className: 'map-tip', closeOnClick: false })
        .setLngLat([focus.lon, focus.lat])
        .setHTML(`<b>선택한 횡단보도</b><br>${esc(focus.label)}`)
        .addTo(map)
    })
  }, [focus])

  return <div ref={container} className="map" aria-label="읍면동 지도" />
}
