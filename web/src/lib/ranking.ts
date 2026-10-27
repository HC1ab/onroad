import type { AreaItem, CrosswalkItem } from '../api/types'

export type SortKey = 'short_ratio' | 'n_candidate' | 'ratio_65plus'

export const SORT_LABEL: Record<SortKey, string> = {
  short_ratio: '짧음 비율',
  n_candidate: '점검 우선순위 후보 수',
  ratio_65plus: '65세 이상 비율',
}

export const TOP_N_OPTIONS = [10, 20, 50] as const

export interface RankResult {
  rows: AreaItem[]
  /** 표본 부족이라 순위에서 뺀 수 */
  excludedLowSample: number
  /** 정렬 기준 값이 없어 뺀 수 */
  excludedNoValue: number
}

const sortValue = (a: AreaItem, key: SortKey): number | null => a[key]

/**
 * 상위 N 지역. 표본 부족과 정렬 기준 값이 없는 곳은 순위에서 뺀다.
 * 같은 값이면 짧음 비율 → 짧음 건수 → 이름 순으로 정해 순서가 매번 같게 한다.
 */
export function rankAreas(items: AreaItem[], key: SortKey, n: number): RankResult {
  let excludedLowSample = 0
  let excludedNoValue = 0
  const eligible: AreaItem[] = []
  for (const a of items) {
    if (a.low_sample) excludedLowSample++
    else if (sortValue(a, key) === null || a.short_ratio === null) excludedNoValue++
    else eligible.push(a)
  }
  eligible.sort(
    (a, b) =>
      (sortValue(b, key) as number) - (sortValue(a, key) as number) ||
      (b.short_ratio as number) - (a.short_ratio as number) ||
      b.n_short - a.n_short ||
      a.adm_name.localeCompare(b.adm_name, 'ko'),
  )
  return { rows: eligible.slice(0, n), excludedLowSample, excludedNoValue }
}

/** 지역 상세의 횡단보도 목록. 짧은 초 큰 순, onlyShort 면 기준식보다 짧은 곳(gap > 0)만 */
export function sortCrosswalks(items: CrosswalkItem[], onlyShort: boolean): CrosswalkItem[] {
  return items.filter((c) => !onlyShort || c.gap_s > 0).sort((a, b) => b.gap_s - a.gap_s)
}
