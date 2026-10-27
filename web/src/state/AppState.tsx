import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'
import type { Speed } from '../api/types'
import type { Thresholds } from '../lib/quadrant'

export interface LayerVisibility {
  choropleth: boolean
  candidates: boolean
}

/** 어디서 선택했는지. 지도 밖(사분면·목록)에서 선택하면 지도가 그 지역으로 이동한다. */
export type SelectionSource = 'map' | 'chart' | 'list'

export interface Selection {
  admCd: string
  source: SelectionSource
}

/** 상세 표에서 고른 횡단보도. 지도가 그 위치로 이동해 표시한다. */
export interface FocusPoint {
  cwId: string
  lat: number
  lon: number
  label: string
}

// 화면 전체가 함께 쓰는 선택 상태. 지도·사분면·목록·상세가 같은 값을 보고 동시에 바뀐다.
interface AppState {
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
  focus: FocusPoint | null
  setFocus: (f: FocusPoint | null) => void
}

const Ctx = createContext<AppState | null>(null)

export const DEFAULT_SPEED: Speed = 0.8

export function AppStateProvider({ children }: { children: ReactNode }) {
  const [speed, setSpeed] = useState<Speed>(DEFAULT_SPEED)
  const [selection, setSelection] = useState<Selection | null>(null)
  const [layers, setLayers] = useState<LayerVisibility>({ choropleth: true, candidates: true })
  const [customThresholds, setCustomThresholds] = useState<Thresholds | null>(null)
  const [focus, setFocus] = useState<FocusPoint | null>(null)
  const select = useCallback((admCd: string | null, source: SelectionSource) => {
    setSelection(admCd ? { admCd, source } : null)
    setFocus(null)
  }, [])
  const toggleLayer = useCallback((key: keyof LayerVisibility) => setLayers((l) => ({ ...l, [key]: !l[key] })), [])
  const value = useMemo(
    () => ({
      speed, setSpeed,
      selection, selectedAdmCd: selection?.admCd ?? null, select,
      layers, toggleLayer,
      customThresholds, setCustomThresholds,
      focus, setFocus,
    }),
    [speed, selection, select, layers, toggleLayer, customThresholds, focus],
  )
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAppState(): AppState {
  const v = useContext(Ctx)
  if (!v) throw new Error('useAppState 는 AppStateProvider 안에서만 쓸 수 있습니다.')
  return v
}
