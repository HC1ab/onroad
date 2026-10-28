import { API_MODE } from './client'
import { ApiError, errorFrom } from './http'
import { comboKey, staticApi, type CsvKind } from './static'
import type { Radius, Speed } from './types'

export type { CsvKind }

export const MOCK_DOWNLOAD_MESSAGE = '샘플(mock) 모드에서는 내려받기를 제공하지 않습니다.'

/** 현재 모드에서 CSV 를 받을 주소와 기본 파일 이름 (F12). */
export async function csvRequest(kind: CsvKind, speed: Speed, radius: Radius): Promise<{ url: string; filename: string }> {
  if (API_MODE === 'mock') throw new ApiError(MOCK_DOWNLOAD_MESSAGE, 0)
  if (API_MODE === 'static') return staticApi.csv(kind, speed, radius)
  return {
    url: `/api/export/${kind}.csv?speed=${speed}&radius=${radius}`,
    filename: `${kind}_${comboKey(speed, radius)}.csv`,
  }
}

function filenameFrom(res: Response, fallback: string) {
  const m = res.headers.get('Content-Disposition')?.match(/filename="([^"]+)"/)
  return m?.[1] ?? fallback
}

/**
 * 받은 뒤 저장한다. 링크로 바로 열면 실패 응답(미적재 500)이 파일로 저장되므로,
 * 먼저 받아 실패면 오류 문구를 화면에 보여준다.
 */
export async function fetchCsv(kind: CsvKind, speed: Speed, radius: Radius): Promise<{ blob: Blob; filename: string }> {
  const { url, filename } = await csvRequest(kind, speed, radius)
  const res = await fetch(url, { headers: { Accept: 'text/csv' } })
  if (!res.ok) throw await errorFrom(res)
  // 정적 미리보기 서버는 없는 파일에 index.html 을 200으로 줄 수 있다.
  if (res.headers.get('Content-Type')?.includes('text/html')) throw new ApiError(`요청에 실패했습니다 (${res.status}).`, res.status)
  return { blob: await res.blob(), filename: filenameFrom(res, filename) }
}

export function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}
