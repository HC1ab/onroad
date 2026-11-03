import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'
import { API_MODE } from '../api/client'
import type { PointProps, Radius, Speed, Target } from '../api/types'
import { DEFAULT_POINT_FILTER, type PointFilter } from '../lib/points'
import type { Thresholds } from '../lib/quadrant'
import type { Region } from '../lib/region'

export interface LayerVisibility {
  choropleth: boolean
  /** 횡단보도 점(분석한 점, 후보 포함) */
  points: boolean
}

/** 어디서 선택했는지. 지도 밖(사분면·목록)에서 선택하면 지도가 그 지역으로 이동한다. */
export type SelectionSource = 'map' | 'chart' | 'list'

export interface Selection {
  admCd: string
  source: SelectionSource
}

/** 선택한 횡단보도. 지도 점이나 상세 표에서 고른다. 정보 카드와 표 강조가 함께 쓴다. */
export interface PointSelection {
  cwId: string
  lon: number
  lat: number
  props: PointProps
  /** 상세 표에서 고르면 지도가 그 위치로 이동한다(지도에서 고르면 그대로) */
  source: 'map' | 'list'
}

/** 화면 기준. recorded: 기록값을 속도별 기준식과 비교(v1), v2: 3단계 기준 적용(결정 009) */
export type Basis = 'recorded' | 'v2'

// 화면 전체가 함께 쓰는 선택 상태. 지도·사분면·목록·상세가 같은 값을 보고 동시에 바뀐다.
interface AppState {
  basis: Basis
  setBasis: (b: Basis) => void
  /** v2 목표 커버리지 */
  target: Target
  setTarget: (t: Target) => void
  speed: Speed
  setSpeed: (s: Speed) => void
  selection: Selection | null
  selectedAdmCd: string | null
  select: (admCd: string | null, source: SelectionSource) => void
  layers: LayerVisibility
  toggleLayer: (key: keyof LayerVisibility) => void
  /** 사용자가 옮긴 사분면 경계선. null 이면 API 기본값(중앙값) */
  customThresholds: Thresholds | null
  setCustomThresholds: (t: Thresholds | null) => void
  point: PointSelection | null
  setPoint: (p: PointSelection | null) => void
  pointFilter: PointFilter
  setPointFilter: (f: PointFilter) => void
  /** 지역 필터. null 이면 전국 */
  region: Region | null
  setRegion: (r: Region | null) => void
  /** 목적지 노출 반경(m) */
  radius: Radius
  setRadius: (r: Radius) => void
}

const Ctx = createContext<AppState | null>(null)

export const DEFAULT_SPEED: Speed = 0.8
export const DEFAULT_RADIUS: Radius = 300
export const DEFAULT_TARGET: Target = 0.85
/** 서버(B7)와 mock 은 v2 를 내보내므로 v2 가 기본이다. 정적 묶음은 v2 를 아직 못 읽어(#105) 기록값으로 연다. */
const DEFAULT_BASIS: Basis = API_MODE === 'static' ? 'recorded' : 'v2'

export function AppStateProvider({ children }: { children: ReactNode }) {
  const [basis, setBasisState] = useState<Basis>(DEFAULT_BASIS)
  const [target, setTarget] = useState<Target>(DEFAULT_TARGET)
  const [speed, setSpeed] = useState<Speed>(DEFAULT_SPEED)
  const [selection, setSelection] = useState<Selection | null>(null)
  const [layers, setLayers] = useState<LayerVisibility>({ choropleth: true, points: true })
  const [customThresholds, setCustomThresholds] = useState<Thresholds | null>(null)
  const [point, setPoint] = useState<PointSelection | null>(null)
  const [pointFilter, setPointFilter] = useState<PointFilter>(DEFAULT_POINT_FILTER)
  const [region, setRegion] = useState<Region | null>(null)
  const [radius, setRadius] = useState<Radius>(DEFAULT_RADIUS)
  const select = useCallback((admCd: string | null, source: SelectionSource) => {
    setSelection(admCd ? { admCd, source } : null)
    // 다른 동을 고르면 그 동 밖의 횡단보도 선택은 푼다.
    setPoint((p) => (p && p.props.adm_cd === admCd ? p : null))
  }, [])
  // 기준을 바꾸면 가로축 단위(비율 ↔ 초)가 달라지므로 직접 옮긴 경계선과 점 선택을 푼다.
  const setBasis = useCallback((b: Basis) => {
    setBasisState(b)
    setCustomThresholds(null)
    setPoint(null)
  }, [])
  const toggleLayer = useCallback((key: keyof LayerVisibility) => setLayers((l) => ({ ...l, [key]: !l[key] })), [])
  const value = useMemo(
    () => ({
      basis, setBasis,
      target, setTarget,
      speed, setSpeed,
      selection, selectedAdmCd: selection?.admCd ?? null, select,
      layers, toggleLayer,
      customThresholds, setCustomThresholds,
      point, setPoint,
      pointFilter, setPointFilter,
      region, setRegion,
      radius, setRadius,
    }),
    [basis, setBasis, target, speed, selection, select, layers, toggleLayer, customThresholds, point, pointFilter, region, radius],
  )
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAppState(): AppState {
  const v = useContext(Ctx)
  if (!v) throw new Error('useAppState 는 AppStateProvider 안에서만 쓸 수 있습니다.')
  return v
}
