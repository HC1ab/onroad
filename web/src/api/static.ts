import { getJson, notLoaded } from './http'
import type {
  AreaCrosswalksResponse,
  AreasResponse,
  CandidatesResponse,
  MetaResponse,
  Radius,
  Speed,
  ValidationResponse,
} from './types'

/**
 * static 모드: 서버가 내보낸 정적 묶음(contracts/README.md "정적 묶음")을 읽는다(F18, 서버 없이 데모).
 * 묶음은 web/public/static/ 에 두고 빌드하면 dist/static/ 으로 들어간다.
 * manifest 에 없는 조합·상세는 API 의 미적재와 같은 오류로 보여준다.
 */
export const STATIC_BASE = `${import.meta.env.BASE_URL}static/`

export interface StaticManifest {
  _sample?: boolean
  built_at: string
  results: { speed: Speed; radius_m: Radius; details: string[] }[]
}

/** 파일 이름의 속도·반경. 속도는 소수 한 자리(String(1.0) 은 "1" 이라 쓰지 않는다). */
export const comboKey = (speed: Speed, radius: Radius) => `${speed.toFixed(1)}_${radius}`

let manifestCache: Promise<StaticManifest> | null = null
const candidatesCache = new Map<string, Promise<CandidatesResponse>>()

/** 여러 요청이 함께 쓰므로 취소 신호를 넘기지 않는다. 실패하면 다음 요청에서 다시 받는다. */
export function staticManifest(): Promise<StaticManifest> {
  if (!manifestCache) {
    manifestCache = getJson<StaticManifest>(`${STATIC_BASE}manifest.json`).catch((e) => {
      manifestCache = null
      throw e
    })
  }
  return manifestCache
}

/** 테스트용: 캐시 비우기 */
export function resetStaticCache() {
  manifestCache = null
  candidatesCache.clear()
}

async function combo(speed: Speed, radius: Radius) {
  const found = (await staticManifest()).results.find((r) => r.speed === speed && r.radius_m === radius)
  if (!found) throw notLoaded()
  return found
}

function inBbox([x, y]: number[], [x1, y1, x2, y2]: [number, number, number, number]) {
  return x >= x1 && x <= x2 && y >= y1 && y <= y2
}

export type CsvKind = 'areas' | 'crosswalks'

export const staticApi = {
  async areas(speed: Speed, radius: Radius, signal?: AbortSignal): Promise<AreasResponse> {
    await combo(speed, radius)
    return getJson(`${STATIC_BASE}areas/${comboKey(speed, radius)}.json`, signal)
  },

  async areaCrosswalks(admCd: string, speed: Speed, radius: Radius, signal?: AbortSignal): Promise<AreaCrosswalksResponse> {
    const found = await combo(speed, radius)
    if (!found.details.includes(admCd)) throw notLoaded()
    return getJson(`${STATIC_BASE}crosswalks/${comboKey(speed, radius)}/${encodeURIComponent(admCd)}.json`, signal)
  },

  /** 전국 후보 점을 한 번 받아 두고 지도 범위(bbox)는 화면에서 거른다. */
  async candidates(speed: Speed, radius: Radius, bbox?: [number, number, number, number]): Promise<CandidatesResponse> {
    await combo(speed, radius)
    const key = comboKey(speed, radius)
    let all = candidatesCache.get(key)
    if (!all) {
      all = getJson<CandidatesResponse>(`${STATIC_BASE}candidates/${key}.json`)
      all.catch(() => candidatesCache.delete(key))
      candidatesCache.set(key, all)
    }
    const data = await all
    return bbox ? { ...data, features: data.features.filter((f) => inBbox(f.geometry.coordinates, bbox)) } : data
  },

  validation(signal?: AbortSignal): Promise<ValidationResponse> {
    return getJson(`${STATIC_BASE}validation.json`, signal)
  },

  meta(signal?: AbortSignal): Promise<MetaResponse> {
    return getJson(`${STATIC_BASE}meta.json`, signal)
  },

  /** 묶음 안의 CSV. 후보 횡단보도 CSV 는 상세가 있는 조합에만 있다. */
  async csv(kind: CsvKind, speed: Speed, radius: Radius): Promise<{ url: string; filename: string }> {
    const found = await combo(speed, radius)
    if (kind === 'crosswalks' && found.details.length === 0) throw notLoaded()
    const name = `${kind}_${comboKey(speed, radius)}`
    const sample = (await staticManifest())._sample ? '_sample' : ''
    return { url: `${STATIC_BASE}export/${name}.csv`, filename: `${name}${sample}.csv` }
  },
}
