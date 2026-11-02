import { afterEach, describe, expect, it, vi } from 'vitest'

// API_MODE 는 모듈을 읽을 때 정해지므로, 모드마다 모듈을 새로 읽는다.
async function load(mode: 'real' | 'mock') {
  vi.resetModules()
  vi.stubEnv('VITE_API_MODE', mode)
  return import('./download')
}

afterEach(() => {
  vi.unstubAllEnvs()
  vi.unstubAllGlobals()
})

describe('CSV 내려받기 (F12)', () => {
  it('real: 현재 속도·반경으로 요청하고 서버가 준 파일 이름을 쓴다', async () => {
    const fetchMock = vi.fn(async () => new Response('﻿adm_cd\n', {
      status: 200,
      headers: { 'Content-Type': 'text/csv', 'Content-Disposition': 'attachment; filename="areas_1.0_500_sample.csv"' },
    }))
    vi.stubGlobal('fetch', fetchMock)
    const { fetchCsv } = await load('real')
    const { filename } = await fetchCsv('areas', 1.0, 500)
    expect(fetchMock).toHaveBeenCalledWith('/api/export/areas.csv?speed=1&radius=500', expect.anything())
    expect(filename).toBe('areas_1.0_500_sample.csv')
  })

  it('real: 실패하면 파일을 저장하지 않고 서버 문구로 오류를 낸다', async () => {
    const body = { error: { code: 'internal_error', message: '요청한 속도·반경·지역의 결과가 아직 적재되지 않았습니다.' } }
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(body), { status: 500 })))
    const { fetchCsv } = await load('real')
    await expect(fetchCsv('crosswalks', 0.7, 300)).rejects.toMatchObject({ status: 500, message: body.error.message })
  })

  it('mock: 내려받기를 제공하지 않는다', async () => {
    const { fetchCsv, MOCK_DOWNLOAD_MESSAGE } = await load('mock')
    await expect(fetchCsv('areas', 0.8, 300)).rejects.toMatchObject({ message: MOCK_DOWNLOAD_MESSAGE })
  })
})
