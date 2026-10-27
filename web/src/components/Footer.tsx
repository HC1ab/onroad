import type { MetaResponse } from '../api/types'

// meta 를 못 받아도 한계 고지는 항상 보이게 한다(F9).
const FALLBACK_LIMITS =
  '한계: 녹색신호시간 정의(점멸 포함 여부) 확정 전 · 읍면동 평균은 개별 이용자 구성이 아님 · 인과 미검증 · "점검 우선순위 후보"이며 위험·위반 판정이 아님'

export function Footer({ meta }: { meta: MetaResponse | null }) {
  return (
    <footer className="footer">
      <div>{meta?.limits_text ?? FALLBACK_LIMITS}</div>
      <div className="muted">
        출처:{' '}
        {meta
          ? meta.sources.map((s, i) => (
              <span key={s.url}>
                {i > 0 && ', '}
                <a href={s.url} target="_blank" rel="noreferrer">{s.name}</a>
                {s.license && s.license !== '확인 필요' ? ` (${s.license})` : ''}
              </span>
            ))
          : '전국횡단보도표준데이터, admdongkor(CC BY 4.0), 행정안전부 등'}
      </div>
    </footer>
  )
}
