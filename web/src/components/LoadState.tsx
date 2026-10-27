interface Props {
  loading: boolean
  error: Error | null
  onRetry: () => void
}

/** 로딩·오류(다시 시도) 공통 표시. 지도 위에 겹쳐 띄운다. */
export function LoadState({ loading, error, onRetry }: Props) {
  if (error) {
    return (
      <div className="load-state error" role="alert">
        <span>{error.message}</span>
        <button type="button" onClick={onRetry}>다시 시도</button>
      </div>
    )
  }
  if (loading) {
    return (
      <div className="load-state" aria-live="polite">
        불러오는 중…
      </div>
    )
  }
  return null
}
