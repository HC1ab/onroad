import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'
import { loadInputs, saveInputs, type GreenInput, type Measurement, type UserInputs } from '../lib/userInputs'

interface Ctx {
  inputs: UserInputs
  setGreen: (g: GreenInput) => void
  removeGreen: (cwId: string) => void
  addMeasurement: (m: Omit<Measurement, 'id' | 'saved_at'>) => void
  removeMeasurement: (id: string) => void
  clearAll: () => void
}

const UserInputsCtx = createContext<Ctx | null>(null)

const storage = () => {
  try {
    return window.localStorage
  } catch {
    return null
  }
}

/** 사용자 입력(브라우저 저장). 지도 정보 카드와 검증 V1 카드가 함께 쓴다. */
export function UserInputsProvider({ children }: { children: ReactNode }) {
  const [inputs, setInputs] = useState<UserInputs>(() => loadInputs(storage()))
  const update = useCallback((fn: (v: UserInputs) => UserInputs) => {
    setInputs((v) => {
      const next = fn(v)
      saveInputs(storage(), next)
      return next
    })
  }, [])
  const value = useMemo<Ctx>(
    () => ({
      inputs,
      setGreen: (g) => update((v) => ({ ...v, greens: { ...v.greens, [g.cw_id]: g } })),
      removeGreen: (cwId) => update((v) => {
        const greens = { ...v.greens }
        delete greens[cwId]
        return { ...v, greens }
      }),
      addMeasurement: (m) => update((v) => ({
        ...v,
        measurements: [...v.measurements, { ...m, id: `${m.cw_id}-${Date.now()}`, saved_at: new Date().toISOString() }],
      })),
      removeMeasurement: (id) => update((v) => ({ ...v, measurements: v.measurements.filter((m) => m.id !== id) })),
      clearAll: () => update(() => ({ greens: {}, measurements: [] })),
    }),
    [inputs, update],
  )
  return <UserInputsCtx.Provider value={value}>{children}</UserInputsCtx.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useUserInputs(): Ctx {
  const v = useContext(UserInputsCtx)
  if (!v) throw new Error('useUserInputs 는 UserInputsProvider 안에서만 쓸 수 있습니다.')
  return v
}
