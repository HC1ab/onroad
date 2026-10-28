/** fetch 공통 처리. 오류 응답(contracts/error.schema.json)의 문구를 그대로 보여준다. */

// 서버 errors.py 와 같은 문구. 정적 묶음에 없는 조합도 같은 안내로 보여준다(빈 결과로 보이지 않게).
export const NOT_LOADED_MESSAGE = '요청한 속도·반경·지역의 결과가 아직 적재되지 않았습니다.'

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export const notLoaded = () => new ApiError(NOT_LOADED_MESSAGE, 500)

/** 실패 응답을 ApiError 로 바꾼다. 본문이 계약 형식이면 그 문구를 쓴다. */
export async function errorFrom(res: Response): Promise<ApiError> {
  let message = `요청에 실패했습니다 (${res.status}).`
  try {
    const body = await res.json()
    if (body?.error?.message) message = body.error.message
  } catch {
    // 오류 본문이 JSON이 아니면 기본 문구를 쓴다.
  }
  return new ApiError(message, res.status)
}

export async function getJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(url, { signal, headers: { Accept: 'application/json' } })
  if (!res.ok) throw await errorFrom(res)
  return res.json() as Promise<T>
}
