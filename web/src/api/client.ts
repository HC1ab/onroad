import type {
  AreaCrosswalksResponse,
  Radius,
  AreasResponse,
  BoundariesResponse,
  CandidatesResponse,
  MetaResponse,
  Speed,
  ValidationResponse,
} from './types'
import { ApiError, getJson } from './http'
import { staticApi } from './static'

export { ApiError }

/**
 * real: 서버 API(/api)와 정적 경계 파일(/data)을 읽는다.
 * mock: contracts/samples 의 가상 데이터를 읽는다(서버 없이 화면 개발용, PRD F17).
 * static: 서버가 내보낸 정적 묶음을 읽는다(서버 없이 데모, F18). `vite build --mode static`.
 * 값이 없으면 mock 으로 시작한다.
 */
export type ApiMode = 'real' | 'mock' | 'static'
export const API_MODE: ApiMode =
  import.meta.env.MODE === 'static' || import.meta.env.VITE_API_MODE === 'static'
    ? 'static'
    : import.meta.env.VITE_API_MODE === 'real'
      ? 'real'
      : 'mock'

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

// mock 전용: 기준식의 진입 시간(초). 실제 값은 파이프라인이 config.yaml 에서 읽어 계산한 결과로 온다.
const MOCK_ENTRY_S = 7

// 샘플은 0.8 m/s 하나뿐이라, 속도를 바꿔도 화면이 변하는지 보이도록 비율만 흉내 낸다.
const MOCK_SPEED_FACTOR: Record<Speed, number> = { 0.7: 1.3, 0.8: 1, 1.0: 0.55 }

// 샘플은 반경 300m 하나뿐이라, 반경을 바꾸면 후보 수만 흉내 낸다(반경이 넓을수록 노출이 많다).
const MOCK_RADIUS_FACTOR: Record<Radius, number> = { 200: 0.6, 300: 1, 500: 1.5 }

async function mockAreas(speed: Speed, radius: Radius, signal?: AbortSignal): Promise<AreasResponse> {
  const sample = (await import('@contracts/samples/areas.json')).default as AreasResponse
  const f = MOCK_SPEED_FACTOR[speed]
  const items = sample.items.map((it) => {
    if (it.short_ratio === null) return it
    const short_ratio = Math.min(1, Math.round(it.short_ratio * f * 1000) / 1000)
    const n_short = Math.round(it.n_analyzed * short_ratio)
    const n_candidate = Math.min(n_short, Math.round(it.n_candidate * MOCK_RADIUS_FACTOR[radius]))
    return { ...it, short_ratio, n_short, n_candidate }
  })
  // 실제 API 는 속도마다 중앙값을 다시 계산하므로 mock 도 경계값을 같은 비율로 맞춘다.
  const thresholds = {
    ...sample.thresholds,
    short_ratio_median: Math.min(1, Math.round(sample.thresholds.short_ratio_median * f * 1000) / 1000),
  }
  return delay({ ...sample, speed, radius_m: radius, thresholds, items }, signal)
}

// 횡단보도 샘플은 한 읍면동 것뿐이라, 다른 동을 고르면 점이 엉뚱한 곳에 찍힌다.
// mock 에서는 샘플 점들을 고른 동의 중심으로 옮겨 보여준다(모양은 그대로).
async function mockRecenter(items: AreaCrosswalksResponse['items'], admCd: string) {
  const b = (await import('@contracts/samples/boundaries.json')).default as unknown as BoundariesResponse
  const f = b.features.find((x) => x.properties.adm_cd === admCd)
  if (!f || items.length === 0) return items
  const ring = f.geometry.type === 'Polygon' ? f.geometry.coordinates[0] : f.geometry.coordinates[0][0]
  const cx = ring.reduce((s, p) => s + p[0], 0) / ring.length
  const cy = ring.reduce((s, p) => s + p[1], 0) / ring.length
  const mx = items.reduce((s, c) => s + c.lon, 0) / items.length
  const my = items.reduce((s, c) => s + c.lat, 0) / items.length
  return items.map((c) => ({ ...c, lon: c.lon - mx + cx, lat: c.lat - my + cy }))
}

// ---- 공개 API ----

export const api = {
  /** 전국 읍면동 값. 지역 거르기는 화면에서 한다(지도 색은 전국 유지). */
  areas(speed: Speed, radius: Radius, signal?: AbortSignal): Promise<AreasResponse> {
    if (API_MODE === 'mock') return mockAreas(speed, radius, signal)
    if (API_MODE === 'static') return staticApi.areas(speed, radius, signal)
    return getJson(`/api/areas?speed=${speed}&radius=${radius}`, signal)
  },

  async areaCrosswalks(admCd: string, speed: Speed, radius: Radius, signal?: AbortSignal): Promise<AreaCrosswalksResponse> {
    if (API_MODE === 'mock') {
      const sample = (await import('@contracts/samples/area_crosswalks.json')).default as AreaCrosswalksResponse
      // 샘플은 0.8 m/s 값이라 속도에 맞게 필요시간·짧은 초를 기준식으로 다시 계산한다.
      const r1 = (v: number) => Math.round(v * 10) / 10
      const items = (await mockRecenter(sample.items, admCd)).map((c) => {
        const t_need_s = r1(MOCK_ENTRY_S + c.length_m / speed)
        const gap_s = r1(t_need_s - c.green_s)
        return { ...c, t_need_s, gap_s, is_candidate: gap_s > 0 && c.exposure_cnt >= 1 }
      })
      return delay({ ...sample, adm_cd: admCd, speed, radius_m: radius, items }, signal)
    }
    if (API_MODE === 'static') return staticApi.areaCrosswalks(admCd, speed, radius, signal)
    return getJson(`/api/areas/${encodeURIComponent(admCd)}/crosswalks?speed=${speed}&radius=${radius}`, signal)
  },

  async candidates(speed: Speed, radius: Radius, bbox?: [number, number, number, number], signal?: AbortSignal): Promise<CandidatesResponse> {
    if (API_MODE === 'mock') {
      const sample = (await import('@contracts/samples/candidates.json')).default as unknown as CandidatesResponse
      // 반경이 좁으면 노출이 적은 점부터 빠지는 것처럼 흉내 낸다. 500m 는 샘플(300m)과 같다.
      const features = radius === 200 ? sample.features.filter((f) => f.properties.exposure_cnt >= 2) : sample.features
      return delay({ ...sample, radius_m: radius, features }, signal)
    }
    if (API_MODE === 'static') return staticApi.candidates(speed, radius, bbox)
    const q = new URLSearchParams({ speed: String(speed), radius: String(radius) })
    if (bbox) q.set('bbox', bbox.join(','))
    return getJson(`/api/crosswalks/candidates?${q}`, signal)
  },

  async validation(signal?: AbortSignal): Promise<ValidationResponse> {
    if (API_MODE === 'mock') return delay((await import('@contracts/samples/validation.json')).default as ValidationResponse, signal)
    if (API_MODE === 'static') return staticApi.validation(signal)
    return getJson('/api/validation', signal)
  },

  async meta(signal?: AbortSignal): Promise<MetaResponse> {
    if (API_MODE === 'mock') return delay((await import('@contracts/samples/meta.json')).default as MetaResponse, signal)
    if (API_MODE === 'static') return staticApi.meta(signal)
    return getJson('/api/meta', signal)
  },

  /** 읍면동 경계. 값은 담지 않고 areas 의 adm_cd 로 붙인다. 실서비스·static 모두 정적 파일(/data). */
  async boundaries(signal?: AbortSignal): Promise<BoundariesResponse> {
    if (API_MODE === 'mock') return (await import('@contracts/samples/boundaries.json')).default as unknown as BoundariesResponse
    return getJson('/data/boundaries.json', signal)
  },
}
