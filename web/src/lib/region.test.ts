import { describe, expect, it } from 'vitest'
import type { AreaItem, BoundariesResponse } from '../api/types'
import { filterAreas, regionBounds, regionLabel, regionOptions } from './region'

const feat = (adm_cd: string, sido: string, sigungu: string, x: number, y: number) => ({
  type: 'Feature' as const,
  properties: { adm_cd, adm_name: adm_cd, sido, sigungu },
  geometry: { type: 'Polygon' as const, coordinates: [[[x, y], [x + 1, y], [x + 1, y + 1], [x, y]]] },
})

const b: BoundariesResponse = {
  type: 'FeatureCollection',
  features: [
    feat('1', '부산광역시', '해운대구', 129, 35),
    feat('2', '부산광역시', '수영구', 128, 34),
    feat('3', '부산광역시', '해운대구', 130, 36),
    feat('4', '서울특별시', '종로구', 126, 37),
  ],
}

const area = (adm_cd: string, sido: string, sigungu: string): AreaItem => ({
  adm_cd, adm_name: adm_cd, sido, sigungu, n_analyzed: 10, n_short: 1, short_ratio: 0.1,
  mean_gap_s: 1, ratio_65plus: 0.2, quadrant: null, n_candidate: 1, low_sample: false,
})

describe('regionOptions', () => {
  it('시도와 시도별 시군구를 중복 없이 가나다순으로 만든다', () => {
    const o = regionOptions(b)
    expect(o.sidos).toEqual(['부산광역시', '서울특별시'])
    expect(o.sigungus['부산광역시']).toEqual(['수영구', '해운대구'])
  })
})

describe('filterAreas', () => {
  const items = [area('1', '부산광역시', '해운대구'), area('2', '부산광역시', '수영구'), area('4', '서울특별시', '종로구')]
  it('지역이 없으면 전체', () => {
    expect(filterAreas(items, null)).toHaveLength(3)
  })
  it('시도만 고르면 시도 전체', () => {
    expect(filterAreas(items, { sido: '부산광역시', sigungu: null }).map((a) => a.adm_cd)).toEqual(['1', '2'])
  })
  it('시군구까지 고르면 그 시군구만', () => {
    expect(filterAreas(items, { sido: '부산광역시', sigungu: '해운대구' }).map((a) => a.adm_cd)).toEqual(['1'])
  })
})

describe('regionBounds', () => {
  it('지역에 속한 경계를 모두 감싼다', () => {
    expect(regionBounds(b, { sido: '부산광역시', sigungu: '해운대구' })).toEqual([[129, 35], [131, 37]])
  })
  it('해당 경계가 없으면 null', () => {
    expect(regionBounds(b, { sido: '없는시', sigungu: null })).toBeNull()
  })
})

describe('regionLabel', () => {
  it('표시 이름', () => {
    expect(regionLabel(null)).toBe('전국')
    expect(regionLabel({ sido: '부산광역시', sigungu: null })).toBe('부산광역시')
    expect(regionLabel({ sido: '부산광역시', sigungu: '해운대구' })).toBe('부산광역시 해운대구')
  })
})
