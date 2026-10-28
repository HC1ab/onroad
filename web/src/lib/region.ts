import type { AreaItem, BoundariesResponse } from '../api/types'

/** 지역 필터. sigungu 가 없으면 시도 전체 */
export interface Region {
  sido: string
  sigungu: string | null
}

export interface RegionOptions {
  sidos: string[]
  /** 시도 → 시군구 목록 */
  sigungus: Record<string, string[]>
}

const ko = (a: string, b: string) => a.localeCompare(b, 'ko')

/** 경계 데이터에서 시도·시군구 선택지를 만든다(가나다순). */
export function regionOptions(b: BoundariesResponse): RegionOptions {
  const map = new Map<string, Set<string>>()
  for (const f of b.features) {
    const { sido, sigungu } = f.properties
    if (!map.has(sido)) map.set(sido, new Set())
    map.get(sido)!.add(sigungu)
  }
  const sidos = [...map.keys()].sort(ko)
  const sigungus: Record<string, string[]> = {}
  for (const s of sidos) sigungus[s] = [...map.get(s)!].sort(ko)
  return { sidos, sigungus }
}

export function inRegion(p: { sido: string; sigungu: string }, r: Region | null): boolean {
  if (!r) return true
  return p.sido === r.sido && (r.sigungu === null || p.sigungu === r.sigungu)
}

/** 목록·사분면용: 지역 안의 읍면동만 */
export function filterAreas(items: AreaItem[], r: Region | null): AreaItem[] {
  return r ? items.filter((a) => inRegion(a, r)) : items
}

export function regionLabel(r: Region | null): string {
  if (!r) return '전국'
  return r.sigungu ? `${r.sido} ${r.sigungu}` : r.sido
}

export type Bounds = [[number, number], [number, number]]

/** 지역에 속한 경계 전체를 감싸는 범위. 해당 경계가 없으면 null */
export function regionBounds(b: BoundariesResponse, r: Region | null): Bounds | null {
  let [minX, minY, maxX, maxY] = [180, 90, -180, -90]
  let found = false
  const visit = (c: unknown): void => {
    if (Array.isArray(c) && typeof c[0] === 'number') {
      const [x, y] = c as number[]
      minX = Math.min(minX, x); minY = Math.min(minY, y); maxX = Math.max(maxX, x); maxY = Math.max(maxY, y)
      found = true
    } else if (Array.isArray(c)) c.forEach(visit)
  }
  for (const f of b.features) if (inRegion(f.properties, r)) visit(f.geometry.coordinates)
  return found ? [[minX, minY], [maxX, maxY]] : null
}
