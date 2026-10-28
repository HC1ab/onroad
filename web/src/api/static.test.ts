import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import areas from '@contracts/samples/areas.json'
import candidates from '@contracts/samples/candidates.json'
import manifest from '@contracts/samples/static_manifest.json'
import { NOT_LOADED_MESSAGE } from './http'
import { comboKey, resetStaticCache, staticApi } from './static'

// 정적 묶음 파일을 흉내 낸다. 없는 파일은 404.
const FILES: Record<string, unknown> = {
  '/static/manifest.json': manifest,
  '/static/areas/0.8_300.json': areas,
  '/static/candidates/0.8_300.json': candidates,
  '/static/crosswalks/0.8_300/21090730.json': { adm_cd: '21090730', speed: 0.8, radius_m: 300, items: [] },
}

const fetchMock = vi.fn(async (url: string) =>
  url in FILES ? new Response(JSON.stringify(FILES[url]), { status: 200 }) : new Response('', { status: 404 }),
)

beforeEach(() => {
  resetStaticCache()
  fetchMock.mockClear()
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => vi.unstubAllGlobals())

describe('정적 묶음 (static 모드)', () => {
  it('파일 이름의 속도는 소수 한 자리다', () => {
    expect(comboKey(1.0, 300)).toBe('1.0_300')
    expect(comboKey(0.7, 200)).toBe('0.7_200')
  })

  it('manifest 에 있는 조합은 그 파일을 읽는다', async () => {
    const data = await staticApi.areas(0.8, 300)
    expect(data.items.length).toBe(areas.items.length)
    expect(fetchMock).toHaveBeenCalledWith('/static/areas/0.8_300.json', expect.anything())
  })

  it('manifest 에 없는 조합·상세는 빈 결과가 아니라 미적재 오류다', async () => {
    await expect(staticApi.areas(1.0, 300)).rejects.toMatchObject({ status: 500, message: NOT_LOADED_MESSAGE })
    await expect(staticApi.candidates(0.8, 500)).rejects.toMatchObject({ message: NOT_LOADED_MESSAGE })
    await expect(staticApi.areaCrosswalks('21090740', 0.8, 300)).rejects.toMatchObject({ message: NOT_LOADED_MESSAGE })
    // 없는 조합의 파일은 요청하지 않는다(미리보기 서버가 index.html 을 200으로 줄 수 있어서).
    expect(fetchMock.mock.calls.map((c) => c[0])).toEqual(['/static/manifest.json'])
  })

  it('후보 점은 한 번 받아 두고 지도 범위로 거른다', async () => {
    const bbox: [number, number, number, number] = [129.13, 35.17, 129.16, 35.19]
    const inView = await staticApi.candidates(0.8, 300, bbox)
    const all = await staticApi.candidates(0.8, 300)
    expect(inView.features.length).toBeGreaterThan(0)
    expect(inView.features.length).toBeLessThan(all.features.length)
    for (const f of inView.features) {
      const [x, y] = f.geometry.coordinates
      expect(x >= 129.13 && x <= 129.16 && y >= 35.17 && y <= 35.19).toBe(true)
    }
    expect(fetchMock.mock.calls.filter((c) => String(c[0]).includes('candidates'))).toHaveLength(1)
  })

  it('CSV 는 묶음 안의 파일이고, 샘플이면 이름에 _sample 이 붙는다', async () => {
    expect(await staticApi.csv('areas', 0.8, 300)).toEqual({
      url: '/static/export/areas_0.8_300.csv',
      filename: 'areas_0.8_300_sample.csv',
    })
    await expect(staticApi.csv('crosswalks', 1.0, 300)).rejects.toMatchObject({ message: NOT_LOADED_MESSAGE })
  })
})
