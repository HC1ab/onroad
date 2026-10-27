import { useCallback, useEffect, useState } from 'react'

export interface ApiState<T> {
  data: T | null
  error: Error | null
  loading: boolean
  reload: () => void
}

/**
 * 비동기 요청 상태(로딩·오류·데이터)를 관리한다.
 * deps 가 바뀌면 이전 요청을 취소하고 마지막 요청의 응답만 반영한다(속도 슬라이더 연속 조작 대비).
 */
export function useApi<T>(load: (signal: AbortSignal) => Promise<T>, deps: readonly unknown[]): ApiState<T> {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<Error | null>(null)
  const [loading, setLoading] = useState(true)
  const [nonce, setNonce] = useState(0)

  const reload = useCallback(() => setNonce((n) => n + 1), [])

  useEffect(() => {
    const ctrl = new AbortController()
    setLoading(true)
    setError(null)
    load(ctrl.signal)
      .then((d) => {
        if (!ctrl.signal.aborted) setData(d)
      })
      .catch((e: unknown) => {
        if (ctrl.signal.aborted || (e instanceof DOMException && e.name === 'AbortError')) return
        // 실패한 조건(예: 적재되지 않은 속도)에서 이전 조건의 값이 그대로 보이지 않게 비운다.
        setData(null)
        setError(e instanceof Error ? e : new Error(String(e)))
      })
      .finally(() => {
        if (!ctrl.signal.aborted) setLoading(false)
      })
    return () => ctrl.abort()
    // load 는 호출할 때마다 새 함수라 deps 로 갱신 시점을 정한다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce])

  return { data, error, loading, reload }
}
