import { useEffect, useState } from 'react'
import { API_MODE } from '../api/client'
import { fetchCsv, MOCK_DOWNLOAD_MESSAGE, saveBlob, type CsvKind } from '../api/download'
import { useAppState } from '../state/AppState'

const LABEL: Record<CsvKind, string> = {
  areas: '읍면동 집계',
  crosswalks: '후보 횡단보도',
}

/** 결과 CSV 내려받기 (F12). 현재 속도·반경 기준. */
export function DownloadMenu() {
  const { speed, radius } = useAppState()
  const [busy, setBusy] = useState<CsvKind | null>(null)
  const [error, setError] = useState<string | null>(null)

  // 속도·반경을 바꾸면 이전 조건의 오류 문구는 지운다.
  useEffect(() => setError(null), [speed, radius])

  if (API_MODE === 'mock') {
    return (
      <button type="button" className="download-btn" disabled title={MOCK_DOWNLOAD_MESSAGE}>
        CSV
      </button>
    )
  }

  const download = async (kind: CsvKind) => {
    setBusy(kind)
    setError(null)
    try {
      const { blob, filename } = await fetchCsv(kind, speed, radius)
      saveBlob(blob, filename)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="download">
      <details>
        <summary className="download-btn">CSV</summary>
        <div className="download-menu">
          <p className="muted">속도 {speed.toFixed(1)} m/s · 반경 {radius}m 기준</p>
          {(Object.keys(LABEL) as CsvKind[]).map((kind) => (
            <button key={kind} type="button" disabled={busy !== null} onClick={() => download(kind)}>
              {busy === kind ? '받는 중…' : LABEL[kind]}
            </button>
          ))}
        </div>
      </details>
      {error && <p className="download-error" role="alert">{error}</p>}
    </div>
  )
}
