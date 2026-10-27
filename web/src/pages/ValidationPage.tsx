import { api } from '../api/client'
import type { MetaResponse } from '../api/types'
import { V1Card } from '../components/validation/V1Card'
import { V2Card } from '../components/validation/V2Card'
import { V3Card } from '../components/validation/V3Card'
import { V4Card } from '../components/validation/V4Card'
import { V5Card } from '../components/validation/V5Card'
import { useApi } from '../hooks/useApi'

const DEF_LABEL: Record<MetaResponse['green_def_status'], string> = {
  unconfirmed: '녹색신호시간 정의(점멸 포함 여부) 확정 전',
  includes_flash: '녹색신호시간: 점멸 포함으로 확인',
  excludes_flash: '녹색신호시간: 점멸 제외로 확인',
}

/** 검증 화면 (F8). V1~V4 결과를 수치와 함께 한 페이지에 보여준다. */
export function ValidationPage({ meta }: { meta: MetaResponse | null }) {
  const v = useApi((s) => api.validation(s), [])

  return (
    <div className="v-page">
      <div className="v-head">
        <div>
          <h2>검증 결과</h2>
          <p className="muted">결과가 기대와 다르게 나와도 그대로 표시합니다 · 모든 검증은 연관성이며 인과가 아닙니다</p>
        </div>
        {meta && (
          <span className={meta.green_def_status === 'unconfirmed' ? 'v-status warn' : 'v-status'}>
            {DEF_LABEL[meta.green_def_status]}
          </span>
        )}
      </div>

      {v.error ? (
        <div className="load-inline error" role="alert">
          {v.error.message}
          <button type="button" onClick={v.reload}>다시 시도</button>
        </div>
      ) : !v.data ? (
        <p className="muted">불러오는 중…</p>
      ) : (
        <div className="v-grid">
          <V1Card v1={v.data.v1} />
          <V2Card v2={v.data.v2} />
          <V3Card v3={v.data.v3} />
          <V4Card v4={v.data.v4} />
          <div className="v-wide"><V5Card v5={v.data.v5} /></div>
        </div>
      )}
    </div>
  )
}
