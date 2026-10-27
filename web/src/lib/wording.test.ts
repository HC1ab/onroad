import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { describe, expect, it } from 'vitest'

// PRD 3장 표현 원칙: 화면 문구에 단정 표현을 쓰지 않는다.
// 허용 문구는 "~이 아님"처럼 부정하는 한계 고지뿐이다.
const FORBIDDEN = ['위험', '위반', '불법', '늘려야']
const ALLOWED_PHRASES = ['위험·위반 판정이 아님']

const SRC = join(__dirname, '..')

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) return sourceFiles(p)
    return /\.(tsx?|css|html)$/.test(name) && !/\.test\.tsx?$/.test(name) ? [p] : []
  })
}

describe('표현 원칙', () => {
  it('화면 코드에 금지 표현이 없다 (허용된 부정 문구 제외)', () => {
    const hits: string[] = []
    for (const file of sourceFiles(SRC)) {
      readFileSync(file, 'utf8').split('\n').forEach((line, i) => {
        let text = line
        for (const ok of ALLOWED_PHRASES) text = text.split(ok).join('')
        for (const w of FORBIDDEN) if (text.includes(w)) hits.push(`${relative(SRC, file)}:${i + 1} "${w}"`)
      })
    }
    expect(hits).toEqual([])
  })
})
