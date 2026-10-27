import type {
  AreaCrosswalksResponse,
  AreasResponse,
  BoundariesResponse,
  CandidatesResponse,
  MetaResponse,
  Speed,
  ValidationResponse,
} from './types'

/**
 * real: 서버 API(/api)와 정적 경계 파일(/data)을 읽는다.
 * mock: contracts/samples 의 가상 데이터를 읽는다(서버 없이 화면 개발용, PRD F17).
 * 값이 없으면 mock 으로 시작한다.
 */
export type ApiMode = 'real' | 'mock'
export const API_MODE: ApiMode = import.meta.env.VITE_API_MODE === 'real' ? 'real' : 'mock'

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function getJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(url, { signal, headers: { Accept: 'application/json' } })
  if (!res.ok) {
    let message = `요청에 실패했습니다 (${res.status}).`
    try {
      const body = await res.json()
      if (body?.error?.message) message = body.error.message
    } catch {
      // 오류 본문이 JSON이 아니면 기본 문구를 쓴다.
    }
    throw new ApiError(message, res.status)
  }
  return res.json() as Promise<T>
}

// ---- mock ----

const MOCK_DELAY_MS = 200

function delay<T>(value: T, signal?: AbortSignal): Promise<T> {
  return new Promise((resolve, reject) => {
    const t = setTimeout(() => resolve(value), MOCK_DELAY_MS)
    signal?.addEventListener('abort', () => {
      clearTimeout(t)
      reject(new DOMException('aborted', 'AbortError'))
    })
  })
}

// 샘플은 0.8 m/s 하나뿐이라, 속도를 바꿔도 화면이 변하는지 보이도록 비율만 흉내 낸다.
const MOCK_SPEED_FACTOR: Record<Speed, number> = { 0.7: 1.3, 0.8: 1, 1.0: 0.55 }

async function mockAreas(speed: Speed, signal?: AbortSignal): Promise<AreasResponse> {
  const sample = (await import('@contracts/samples/areas.json')).default as AreasResponse
  const f = MOCK_SPEED_FACTOR[speed]
  const items = sample.items.map((it) => {
    if (it.short_ratio === null) return it
    const short_ratio = Math.min(1, Math.round(it.short_ratio * f * 1000) / 1000)
    return { ...it, short_ratio, n_short: Math.round(it.n_analyzed * short_ratio) }
  })
  // 실제 API 는 속도마다 중앙값을 다시 계산하므로 mock 도 경계값을 같은 비율로 맞춘다.
  const thresholds = {
    ...sample.thresholds,
    short_ratio_median: Math.min(1, Math.round(sample.thresholds.short_ratio_median * f * 1000) / 1000),
  }
  return delay({ ...sample, speed, thresholds, items }, signal)
}

// ---- 공개 API ----

export const api = {
  areas(speed: Speed, signal?: AbortSignal): Promise<AreasResponse> {
    if (API_MODE === 'mock') return mockAreas(speed, signal)
    return getJson(`/api/areas?speed=${speed}`, signal)
  },

  async areaCrosswalks(admCd: string, speed: Speed, signal?: AbortSignal): Promise<AreaCrosswalksResponse> {
    if (API_MODE === 'mock') {
      const sample = (await import('@contracts/samples/area_crosswalks.json')).default as AreaCrosswalksResponse
      return delay({ ...sample, adm_cd: admCd, speed }, signal)
    }
    return getJson(`/api/areas/${encodeURIComponent(admCd)}/crosswalks?speed=${speed}`, signal)
  },

  async candidates(speed: Speed, bbox?: [number, number, number, number], signal?: AbortSignal): Promise<CandidatesResponse> {
    if (API_MODE === 'mock') {
      const sample = (await import('@contracts/samples/candidates.json')).default as unknown as CandidatesResponse
      return delay(sample, signal)
    }
    const q = new URLSearchParams({ speed: String(speed) })
    if (bbox) q.set('bbox', bbox.join(','))
    return getJson(`/api/crosswalks/candidates?${q}`, signal)
  },

  async validation(signal?: AbortSignal): Promise<ValidationResponse> {
    if (API_MODE === 'mock') return delay((await import('@contracts/samples/validation.json')).default as ValidationResponse, signal)
    return getJson('/api/validation', signal)
  },

  async meta(signal?: AbortSignal): Promise<MetaResponse> {
    if (API_MODE === 'mock') return delay((await import('@contracts/samples/meta.json')).default as MetaResponse, signal)
    return getJson('/api/meta', signal)
  },

  /** 읍면동 경계. 값은 담지 않고 areas 의 adm_cd 로 붙인다. 실서비스는 nginx 정적 파일(/data). */
  async boundaries(signal?: AbortSignal): Promise<BoundariesResponse> {
    if (API_MODE === 'mock') return (await import('@contracts/samples/boundaries.json')).default as unknown as BoundariesResponse
    return getJson('/data/boundaries.json', signal)
  },
}
