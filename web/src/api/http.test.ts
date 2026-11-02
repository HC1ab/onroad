import { describe, expect, it } from 'vitest'
import { ApiError, isNotAvailable, NOT_LOADED_MESSAGE } from './http'

describe('결과 없음 판단', () => {
  it('미적재 안내와 404 는 대신할 데이터로 보여준다', () => {
    expect(isNotAvailable(new ApiError(NOT_LOADED_MESSAGE, 500))).toBe(true)
    expect(isNotAvailable(new ApiError('요청한 대상을 찾을 수 없습니다.', 404))).toBe(true)
  })

  it('그 밖의 오류는 그대로 알린다', () => {
    expect(isNotAvailable(new ApiError('요청에 실패했습니다 (500).', 500))).toBe(false)
    expect(isNotAvailable(new ApiError('잘못된 요청', 400))).toBe(false)
    expect(isNotAvailable(new Error('network'))).toBe(false)
  })
})
