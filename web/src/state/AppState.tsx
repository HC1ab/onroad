import { createContext, useContext, useMemo, useState, type ReactNode } from 'react'
import type { Speed } from '../api/types'

// 화면 전체가 함께 쓰는 선택 상태. 지도·사분면·목록이 같은 값을 보고 동시에 바뀐다.
interface AppState {
  speed: Speed
  setSpeed: (s: Speed) => void
  selectedAdmCd: string | null
  setSelectedAdmCd: (adm: string | null) => void
}

const Ctx = createContext<AppState | null>(null)

export const DEFAULT_SPEED: Speed = 0.8

export function AppStateProvider({ children }: { children: ReactNode }) {
  const [speed, setSpeed] = useState<Speed>(DEFAULT_SPEED)
  const [selectedAdmCd, setSelectedAdmCd] = useState<string | null>(null)
  const value = useMemo(() => ({ speed, setSpeed, selectedAdmCd, setSelectedAdmCd }), [speed, selectedAdmCd])
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAppState(): AppState {
  const v = useContext(Ctx)
  if (!v) throw new Error('useAppState 는 AppStateProvider 안에서만 쓸 수 있습니다.')
  return v
}
