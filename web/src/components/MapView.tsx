import { useEffect, useRef } from 'react'
import maplibregl, { type ExpressionSpecification, type LngLatBoundsLike } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import type { AreaItem, BoundariesResponse } from '../api/types'
import { useAppState } from '../state/AppState'
import { LOW_SAMPLE_COLOR, NO_VALUE_COLOR, RATIO_STEPS } from './mapStyle'

// 배경 지도: OpenFreeMap(키 없음). 출처 표기는 스타일이 자동으로 넣는다.
const BASEMAP_STYLE = import.meta.env.VITE_BASEMAP_STYLE || 'https://tiles.openfreemap.org/styles/positron'
const SOURCE = 'areas'

// 표본 부족은 회색, 값 없음은 연회색, 나머지는 짧음 비율 단계 색
const FILL_COLOR: ExpressionSpecification = [
  'case',
  ['boolean', ['feature-state', 'low_sample'], false],
  LOW_SAMPLE_COLOR,
  ['==', ['feature-state', 'short_ratio'], null],
  NO_VALUE_COLOR,
  ['step', ['to-number', ['coalesce', ['feature-state', 'short_ratio'], 0]], RATIO_STEPS[0][1], ...RATIO_STEPS.slice(1).flat()],
]

interface Props {
  boundaries: BoundariesResponse | null
  areas: AreaItem[] | null
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

export function MapView({ boundaries, areas }: Props) {
  const container = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const readyRef = useRef(false)
  const { selectedAdmCd, setSelectedAdmCd } = useAppState()

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
      readyRef.current = true
      map.fire('onroad:ready')
    })
    mapRef.current = map
    return () => {
      readyRef.current = false
      map.remove()
      mapRef.current = null
    }
  }, [])

  // 경계 레이어
  useEffect(() => {
    const map = mapRef.current
    if (!map || !boundaries) return
    const add = () => {
      if (map.getSource(SOURCE)) return
      map.addSource(SOURCE, { type: 'geojson', data: boundaries, promoteId: 'adm_cd' })
      map.addLayer({ id: 'areas-fill', type: 'fill', source: SOURCE, paint: { 'fill-color': FILL_COLOR, 'fill-opacity': 0.8 } })
      map.addLayer({ id: 'areas-line', type: 'line', source: SOURCE, paint: { 'line-color': '#ffffff', 'line-width': 1 } })
      map.addLayer({
        id: 'areas-selected', type: 'line', source: SOURCE,
        filter: ['==', ['get', 'adm_cd'], ''],
        paint: { 'line-color': '#111827', 'line-width': 3 },
      })
      map.on('click', 'areas-fill', (e) => {
        const adm = e.features?.[0]?.properties?.adm_cd as string | undefined
        if (adm) setSelectedAdmCd(adm)
      })
      map.on('mouseenter', 'areas-fill', () => { map.getCanvas().style.cursor = 'pointer' })
      map.on('mouseleave', 'areas-fill', () => { map.getCanvas().style.cursor = '' })
      map.fitBounds(boundsOf(boundaries), { padding: 40, duration: 0 })
      map.fire('onroad:layers')
    }
    if (readyRef.current) add()
    else map.once('onroad:ready', add)
  }, [boundaries, setSelectedAdmCd])

  // 값 → feature-state (속도를 바꾸면 경계는 그대로 두고 값만 바꾼다)
  useEffect(() => {
    const map = mapRef.current
    if (!map || !areas) return
    const apply = () => {
      if (!map.getSource(SOURCE)) return
      map.removeFeatureState({ source: SOURCE })
      for (const a of areas) {
        map.setFeatureState({ source: SOURCE, id: a.adm_cd }, { short_ratio: a.short_ratio, low_sample: a.low_sample })
      }
    }
    if (map.getSource(SOURCE)) apply()
    else map.once('onroad:layers', apply)
  }, [areas])

  // 선택 강조
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    const apply = () => map.getLayer('areas-selected') && map.setFilter('areas-selected', ['==', ['get', 'adm_cd'], selectedAdmCd ?? ''])
    if (map.getLayer('areas-selected')) apply()
    else map.once('onroad:layers', apply)
  }, [selectedAdmCd])

  return <div ref={container} className="map" aria-label="읍면동 지도" />
}
